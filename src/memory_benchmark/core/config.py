"""仿 Spring Boot (`@ConfigurationProperties` + Profile Override + DI) 的配置注入引擎。

设计特点：
1. 自动加载 `.env` 环境变量，并支持 YAML 中嵌套的 `${ENV_VAR:default}` 占位符递归解析；
2. 支持 **层级继承与细粒度覆盖 (`deep_merge`)**：
   `全局默认 (llm / prompts)` -> `数据集专属覆盖 (benchmarks.<name>.llm / prompts)` -> `运行时覆盖 (overrides)`；
3. 利用 `dataclasses.fields()` 反射将合并后的字典自动绑定为不可变强类型 Dataclass (`LLMProperties` / `PromptProperties` / `BenchmarkProfile`)，通过构造器显式依赖注入 (DI) 传递给业务组件。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, TypeVar

import yaml
from dotenv import load_dotenv

from .exceptions import ConfigurationError

T = TypeVar("T")

_INNER_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^{}]*)|:([^{}]*))?\}")


def resolve_placeholders(value: Any, env: dict[str, str] | None = None) -> Any:
    """递归解析字符串、字典或列表中的 `${ENV_VAR:default}` 占位符。"""
    env_map = env if env is not None else os.environ
    if isinstance(value, dict):
        return {k: resolve_placeholders(v, env_map) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_placeholders(v, env_map) for v in value]
    if not isinstance(value, str):
        return value

    result = value
    for _ in range(5):
        if "${" not in result:
            break

        def _repl(match: re.Match[str]) -> str:
            var_name = match.group(1)
            fallback = match.group(2) if match.group(2) is not None else (match.group(3) or "")
            raw = env_map.get(var_name)
            return raw.strip() if (raw is not None and raw.strip() != "") else fallback

        updated = _INNER_PLACEHOLDER_RE.sub(_repl, result)
        if updated == result:
            break
        result = updated
    return result


def deep_merge(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    """递归深度合并两个配置字典（`override` 中非空键值覆盖 `base` 同名键）。"""
    merged = dict(base)
    if not override:
        return merged
    for k, v in override.items():
        if v is None:
            continue
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def bind_dataclass(cls: type[T], data: dict[str, Any] | None) -> T:
    """仿 Spring Boot `@ConfigurationProperties`，将字典键值自动反射注入到目标 Dataclass。"""
    source = data or {}
    kwargs: dict[str, Any] = {}
    for f in fields(cls):  # type: ignore[arg-type]
        if f.name in source and source[f.name] is not None:
            val = source[f.name]
            if f.type in ("float", float) and not isinstance(val, float):
                val = float(val)
            elif f.type in ("int", int) and not isinstance(val, int):
                val = int(val)
            elif f.type in ("str", str) and not isinstance(val, str):
                val = str(val)
            kwargs[f.name] = val
    return cls(**kwargs)


@dataclass(frozen=True)
class LLMProperties:
    """单角色 LLM 客户端配置属性（支持全局默认 + Benchmark 级细粒度覆盖，如 `temperature` / `max_tokens`）。"""

    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout_seconds: float = 60.0
    max_retries: int = 2

    def require_api_key(self) -> str:
        """在实际发起网络请求前校验 API Key 是否已配置。"""
        if not self.api_key.strip():
            raise ConfigurationError(
                "Missing LLM API key. Set API_KEY in .env."
            )
        return self.api_key


@dataclass(frozen=True)
class PromptProperties:
    """回答生成与裁判评分的 Prompt 模板数据属性（支持按 Benchmark 或题型动态覆盖任意字段）。"""

    answer_system: str = "You are a helpful question-answering assistant."
    answer_user: str = (
        "[Retrieved Memory Context]\n{memory_context}\n\n"
        "[Question Time]: {question_time}\n[Question]: {question}\n\nAnswer:"
    )
    judge_system: str = (
        'You are an impartial judge. Return JSON: '
        '{"reason": "step-by-step reasoning", "verdict": "CORRECT"|"WRONG"|"UNDECIDABLE"}'
    )
    judge_user: str = (
        "[Question]: {question}\n[Question Time]: {question_time}\n"
        "[Gold Answer]: {gold_answer}\n[Predicted Answer]: {predicted_answer}"
    )
    task_answer_prompts: dict[str, str] = field(default_factory=dict)
    task_judge_prompts: dict[str, str] = field(default_factory=dict)

    def get_answer_user(self, category: str | None = None) -> str:
        """根据题型获取针对性 Answer User 提示词模板，未匹配则优雅降级为默认 `answer_user`。"""
        if category:
            cat_key = str(category).strip()
            if cat_key in self.task_answer_prompts:
                return self.task_answer_prompts[cat_key]
            cat_norm = cat_key.lower().replace("_", "-")
            for k, v in self.task_answer_prompts.items():
                k_norm = k.lower().replace("_", "-")
                if k_norm == cat_norm:
                    return v
            for k, v in self.task_answer_prompts.items():
                k_norm = k.lower().replace("_", "-")
                if cat_norm in k_norm or k_norm in cat_norm:
                    return v
        return self.answer_user

    def get_judge_system(self, category: str | None = None) -> str:
        """根据题型获取针对性 Judge System 提示词模板，未匹配则优雅降级为默认 `judge_system`。"""
        if category:
            cat_key = str(category).strip()
            if cat_key in self.task_judge_prompts:
                return self.task_judge_prompts[cat_key]
            cat_norm = cat_key.lower().replace("_", "-")
            for k, v in self.task_judge_prompts.items():
                k_norm = k.lower().replace("_", "-")
                if k_norm == cat_norm:
                    return v
            for k, v in self.task_judge_prompts.items():
                k_norm = k.lower().replace("_", "-")
                if cat_norm in k_norm or k_norm in cat_norm:
                    return v
        return self.judge_system


@dataclass(frozen=True)
class BenchmarkProfile:
    """单个 Benchmark 经过层级继承与覆盖合并后的完整依赖注入配置包。"""

    benchmark_name: str
    answer_llm: LLMProperties
    judge_llm: LLMProperties
    prompts: PromptProperties


@dataclass(frozen=True)
class AppConfig:
    """仿 Spring `ApplicationContext` 的配置容器：负责解析层级覆盖并向外提供强类型配置 Bean。"""

    project_root: Path
    raw: dict[str, Any]

    @property
    def data_root(self) -> Path:
        return self.project_root / "data"

    @property
    def outputs_root(self) -> Path:
        return self.project_root / "outputs"

    def profile(
        self,
        benchmark_name: str = "default",
        *,
        overrides: dict[str, Any] | None = None,
    ) -> BenchmarkProfile:
        """合成指定 Benchmark 的完整配置（全局默认 -> `benchmarks.<name>` 覆盖 -> `overrides` 覆盖）。"""
        key = benchmark_name.strip().lower()
        base_llm = self.raw.get("llm") or {}
        base_prompts = dict(self.raw.get("prompts") or {})
        if isinstance(base_prompts.get("default"), dict):
            base_prompts = dict(base_prompts["default"])

        bench_section = (self.raw.get("benchmarks") or {}).get(key) or {}
        merged_llm = deep_merge(base_llm, bench_section.get("llm"))
        merged_prompts = deep_merge(base_prompts, bench_section.get("prompts"))

        # 兼容直接在 prompts.<benchmark> 下定义模板的简写形式
        raw_prompts_root = self.raw.get("prompts") or {}
        if key in raw_prompts_root and isinstance(raw_prompts_root[key], dict):
            merged_prompts = deep_merge(merged_prompts, raw_prompts_root[key])

        if overrides:
            if "llm" in overrides:
                merged_llm = deep_merge(merged_llm, overrides["llm"])
            if "prompts" in overrides:
                merged_prompts = deep_merge(merged_prompts, overrides["prompts"])

        return BenchmarkProfile(
            benchmark_name=key,
            answer_llm=bind_dataclass(LLMProperties, merged_llm.get("answer")),
            judge_llm=bind_dataclass(LLMProperties, merged_llm.get("judge")),
            prompts=bind_dataclass(PromptProperties, merged_prompts),
        )

    def llm(
        self,
        role: str = "answer",
        benchmark_name: str = "default",
        *,
        overrides: dict[str, Any] | None = None,
    ) -> LLMProperties:
        """获取经 Benchmark 覆盖合并后的 `answer` 或 `judge` LLM 配置。"""
        clean_role = role.removesuffix("_llm").strip().lower()
        prof = self.profile(benchmark_name, overrides={"llm": {clean_role: overrides}} if overrides else None)
        return prof.judge_llm if clean_role == "judge" else prof.answer_llm

    def prompts(
        self,
        benchmark_name: str = "default",
        *,
        overrides: dict[str, Any] | None = None,
    ) -> PromptProperties:
        """获取经 Benchmark 覆盖合并后的 `PromptProperties`。"""
        return self.profile(
            benchmark_name,
            overrides={"prompts": overrides} if overrides else None,
        ).prompts


def load_app_config(
    project_root: str | Path = ".",
    config_path: str | Path | None = None,
) -> AppConfig:
    """加载 `.env` 与 `configs/application.yaml`，完成占位符展开并返回 `AppConfig`。"""
    root = Path(project_root).expanduser().resolve()
    dotenv_file = root / ".env"
    if dotenv_file.is_file():
        load_dotenv(dotenv_file, override=False)

    yaml_file = Path(config_path) if config_path else root / "configs" / "application.yaml"
    if yaml_file.is_file():
        raw_loaded = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
    else:
        raw_loaded = {}

    resolved = resolve_placeholders(raw_loaded)
    return AppConfig(project_root=root, raw=resolved if isinstance(resolved, dict) else {})
