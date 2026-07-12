"""准备 Hugging Face Dataset 仓库上传包。

脚本从本地 `data/` 目录生成一个可上传到 Hugging Face 的 bundle：

- 复制或硬链接 dataset 文件；
- 跳过 `.DS_Store` 等系统噪声；
- 生成根目录 dataset card；
- 为每个顶层 dataset 生成 README；
- 生成 `manifest.json` 和 `checksums.sha256`。

默认输出到 `tmp/hf_dataset_bundle/`，该目录已被 `.gitignore` 忽略。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


LinkMode = Literal["copy", "hardlink"]

SKIPPED_FILE_NAMES = {".DS_Store"}
SKIPPED_DIR_NAMES = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


@dataclass(frozen=True)
class BundleFile:
    """记录 bundle 中一个数据文件的校验信息。

    字段:
        path: 文件在 Hugging Face dataset repo 内的相对路径。
        dataset: 顶层 dataset 名称，例如 `locomo`。
        size_bytes: 文件字节数。
        sha256: 文件内容的 SHA256。
    """

    path: str
    dataset: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class BundleDatasetSummary:
    """记录一个顶层 dataset 的聚合信息。

    字段:
        name: 顶层 dataset 名称。
        file_count: 数据文件数量，不包含自动生成的 README/manifest/checksum。
        size_bytes: 数据文件总字节数。
    """

    name: str
    file_count: int
    size_bytes: int


@dataclass(frozen=True)
class BundleManifest:
    """记录 Hugging Face 上传包的整体清单。

    字段:
        repo_id: 目标 Hugging Face dataset repo id。
        generated_at_utc: 生成时间，UTC ISO 格式。
        source_root_name: 本地源目录名称，不写入绝对路径，避免泄漏本机路径。
        total_files: 数据文件总数。
        total_bytes: 数据文件总字节数。
        datasets: 顶层 dataset 聚合信息。
        files: 每个数据文件的校验信息。
    """

    repo_id: str
    generated_at_utc: str
    source_root_name: str
    total_files: int
    total_bytes: int
    datasets: dict[str, BundleDatasetSummary]
    files: list[BundleFile]


def should_skip_path(path: Path) -> bool:
    """判断源数据路径是否应从 Hugging Face bundle 中排除。

    参数:
        path: 源数据中的文件或目录路径。

    返回:
        bool: 命中系统噪声文件、缓存目录或 Git 元数据时返回 True。
    """

    if path.name in SKIPPED_FILE_NAMES:
        return True
    return any(part in SKIPPED_DIR_NAMES for part in path.parts)


def compute_sha256(path: Path) -> str:
    """计算文件 SHA256。

    参数:
        path: 待计算的文件路径。

    返回:
        str: 十六进制 SHA256 字符串。
    """

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_or_link_file(source: Path, destination: Path, link_mode: LinkMode) -> None:
    """把单个文件复制或硬链接到输出目录。

    参数:
        source: 源文件路径。
        destination: 目标文件路径。
        link_mode: `copy` 表示复制；`hardlink` 表示优先硬链接，失败后回退复制。

    返回:
        None。目标文件会被创建。
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    if link_mode == "copy":
        shutil.copy2(source, destination)
        return

    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def dataset_description(dataset_name: str) -> str:
    """返回顶层 dataset README 的说明正文。

    参数:
        dataset_name: 顶层 dataset 目录名。

    返回:
        str: Markdown 正文，用于写入 `<dataset>/README.md`。
    """

    descriptions = {
        "locomo": """\
# LoCoMo

## 用途

LoCoMo 是当前 Phase 1 主线 benchmark。它可以归一化为 conversation + QA：
每个 conversation 包含多个 session，每个 session 包含按顺序排列的 turn，QA 基于
对应 conversation 进行回答。

## 当前文件

- `locomo10.json`: 本项目当前运行时使用的 LoCoMo 数据文件。

## 结构要点

- 历史对话会被 adapter 转为 `Conversation -> Session -> Turn`。
- 问题会被 adapter 转为 `Question`。
- 标准答案和 evidence 只进入 `GoldAnswerInfo`，不能传给 method。
- 当前质量指标为 LoCoMo token F1，可选 LLM judge accuracy。
""",
        "longmemeval": """\
# LongMemEval

## 用途

LongMemEval 是 Phase 1 主线 benchmark。它按 evaluation instance 组织长对话历史和问题，
本项目将其归一化为 conversation + QA。

## 当前文件

- `longmemeval_s_cleaned.json`: 标准/较小版本，默认优先用于 smoke 和早期实验。
- `longmemeval_m_cleaned.json`: 更大版本，正式实验时作为独立 variant 运行。

## 结构要点

- S/M 必须作为独立 variant 运行，不能合并成一个混合 dataset。
- 问题时间等字段如果存在会进入公开 `Question`。
- 标准答案、answer session id 等只给 evaluator 使用。
- 当前主指标为 LLM judge accuracy。
""",
        "halumem": """\
# HaluMem

## 用途

HaluMem 当前不进入 Phase 1 主线。后续如果只取 QA-only 或 conversation + QA 可自然适配的
切片，可以再接入当前 task family。

## 当前文件

- `HaluMem-Medium.jsonl`
- `HaluMem-Long.jsonl`

## 结构要点

原始 HaluMem 更偏记忆写入和幻觉检测评测。接入前需要确认公开输入、标准标签和当前
answer-level 指标边界，不能把 evaluator-only 标签传给 method。
""",
        "mem_gallery": """\
# Mem-Gallery

## 用途

Mem-Gallery 当前不进入 Phase 1 主线。它包含多模态材料，本项目 core 已保留 `ImageRef`
等字段，但 Phase 1 先不运行多模态实验。

## 当前目录

- `dialog/`: 对话数据。
- `image/`: 图片资源。
- `prompts/`: 官方或参考 prompt。

## 结构要点

后续接入前需要确认是否能自然表达为 conversation + QA；如果不能，需要等真实需求出现后
再设计新的 task family。
""",
        "membench": """\
# MemBench

## 用途

MemBench 当前不进入 Phase 1 主线。后续如果存在 QA-only 或 conversation + QA 可自然适配
的切片，可以再作为独立工作接入。

## 结构要点

接入前需要从官方数据和评测流程重新确认公开输入、私有标签和 answer-level metric。
""",
        "BEAM": """\
# BEAM

## 用途

BEAM 当前作为本地参考数据保留，不进入 Phase 1 主线。是否属于 conversation + QA task
family 需要在正式接入前重新核验。

## 结构要点

目录内可能包含 Hugging Face datasets 格式的子目录和 metadata。上传时保留原始文件，
但本项目当前 runner 不默认读取 BEAM。
""",
    }
    return descriptions.get(
        dataset_name,
        f"""\
# {dataset_name}

## 用途

该目录由本地 `data/{dataset_name}/` 复制而来。当前 README 是自动生成的通用说明。

## 结构要点

正式接入本项目 runner 前，需要补充原始来源、数据结构、公开输入、私有标签和评测指标。
""",
    )


def build_root_readme(repo_id: str, manifest: BundleManifest) -> str:
    """生成 Hugging Face dataset repo 根 README。

    参数:
        repo_id: 目标 Hugging Face dataset repo id。
        manifest: 已生成的数据清单。

    返回:
        str: Hugging Face dataset card Markdown。
    """

    dataset_rows = "\n".join(
        f"| `{name}` | {summary.file_count} | {summary.size_bytes} |"
        for name, summary in sorted(manifest.datasets.items())
    )
    return f"""\
---
pretty_name: AgentMemoryBench Data
language:
- en
- zh
task_categories:
- question-answering
license: other
---

# AgentMemoryBench Data

This dataset repository stores runtime benchmark data used by
[AgentMemoryBench](https://github.com/zzp-elio/AgentMemoryBench).

This repository is intended for public download by AgentMemoryBench users. Please keep upstream
benchmark licenses, citations, and redistribution notes up to date before broad distribution.

## Repository

- Dataset repo: `{repo_id}`
- Generated at: `{manifest.generated_at_utc}`
- Source root name: `{manifest.source_root_name}`
- Total data files: `{manifest.total_files}`
- Total data bytes: `{manifest.total_bytes}`

## Included datasets

| Dataset | Data files | Bytes |
| --- | ---: | ---: |
{dataset_rows}

## File integrity

- `manifest.json` records file sizes and SHA256 hashes.
- `checksums.sha256` can be verified with `sha256sum -c checksums.sha256` on Linux.

## Usage in AgentMemoryBench

Download the repository into the project root as `data/`, or download selected subdirectories:

```bash
hf download {repo_id} --type dataset --local-dir data
hf download {repo_id} --type dataset --include "locomo/**" --local-dir data
```

AgentMemoryBench adapters expect the same relative layout as this repository.
"""


def write_dataset_readmes(output_dir: Path, dataset_names: set[str]) -> None:
    """为每个顶层 dataset 写入 README。

    参数:
        output_dir: Hugging Face bundle 输出目录。
        dataset_names: 顶层 dataset 名称集合。

    返回:
        None。函数会写入 `<dataset>/README.md`。
    """

    for dataset_name in sorted(dataset_names):
        dataset_dir = output_dir / dataset_name
        dataset_dir.mkdir(parents=True, exist_ok=True)
        (dataset_dir / "README.md").write_text(dataset_description(dataset_name), encoding="utf-8")


def write_manifest_files(output_dir: Path, manifest: BundleManifest) -> None:
    """写入 `manifest.json`、`checksums.sha256` 和根 README。

    参数:
        output_dir: Hugging Face bundle 输出目录。
        manifest: 待写入的清单对象。

    返回:
        None。函数会创建或覆盖三个生成文件。
    """

    payload = asdict(manifest)
    (output_dir / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    checksum_lines = [f"{file.sha256}  {file.path}" for file in sorted(manifest.files, key=lambda item: item.path)]
    (output_dir / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    (output_dir / "README.md").write_text(build_root_readme(manifest.repo_id, manifest), encoding="utf-8")


def ensure_safe_output(source_dir: Path, output_dir: Path) -> None:
    """确认输出目录不会覆盖源数据。

    参数:
        source_dir: 源数据目录。
        output_dir: 输出目录。

    返回:
        None。路径危险时抛出 `ValueError`。
    """

    resolved_source = source_dir.resolve()
    resolved_output = output_dir.resolve()
    if resolved_output == resolved_source:
        raise ValueError("输出目录不能等于源数据目录")
    if resolved_source in resolved_output.parents:
        raise ValueError("输出目录不能位于源数据目录内部")
    if resolved_output in resolved_source.parents:
        raise ValueError("输出目录不能是源数据目录的上级目录")


def build_hf_dataset_bundle(
    source_dir: Path,
    output_dir: Path,
    repo_id: str,
    link_mode: LinkMode = "hardlink",
    clean_output: bool = True,
) -> BundleManifest:
    """构建 Hugging Face dataset 上传包。

    参数:
        source_dir: 本地 runtime dataset 根目录，通常是 `data/`。
        output_dir: 输出 bundle 目录，建议使用 `tmp/hf_dataset_bundle/`。
        repo_id: 目标 Hugging Face dataset repo id，例如 `BuptZZP/agentmemorybench-data`。
        link_mode: 文件进入 bundle 的方式；`hardlink` 节省空间，`copy` 更通用。
        clean_output: 是否在生成前清空已有输出目录。

    返回:
        BundleManifest: 本次生成的数据清单。
    """

    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    ensure_safe_output(source_dir, output_dir)
    if not source_dir.is_dir():
        raise FileNotFoundError(f"源数据目录不存在: {source_dir}")
    if clean_output and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bundle_files: list[BundleFile] = []
    dataset_names: set[str] = set()
    dataset_sizes: dict[str, int] = {}
    dataset_counts: dict[str, int] = {}

    for source_file in sorted(source_dir.rglob("*")):
        if not source_file.is_file() or should_skip_path(source_file.relative_to(source_dir)):
            continue
        relative_path = source_file.relative_to(source_dir)
        if len(relative_path.parts) == 0:
            continue
        dataset_name = relative_path.parts[0]
        dataset_names.add(dataset_name)
        destination_file = output_dir / relative_path
        copy_or_link_file(source_file, destination_file, link_mode)

        size_bytes = destination_file.stat().st_size
        sha256 = compute_sha256(destination_file)
        path_text = relative_path.as_posix()
        bundle_files.append(
            BundleFile(
                path=path_text,
                dataset=dataset_name,
                size_bytes=size_bytes,
                sha256=sha256,
            )
        )
        dataset_sizes[dataset_name] = dataset_sizes.get(dataset_name, 0) + size_bytes
        dataset_counts[dataset_name] = dataset_counts.get(dataset_name, 0) + 1

    for child in sorted(source_dir.iterdir()):
        if child.is_dir() and not should_skip_path(child.relative_to(source_dir)):
            dataset_names.add(child.name)

    datasets = {
        name: BundleDatasetSummary(
            name=name,
            file_count=dataset_counts.get(name, 0),
            size_bytes=dataset_sizes.get(name, 0),
        )
        for name in sorted(dataset_names)
    }
    manifest = BundleManifest(
        repo_id=repo_id,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        source_root_name=source_dir.name,
        total_files=len(bundle_files),
        total_bytes=sum(file.size_bytes for file in bundle_files),
        datasets=datasets,
        files=sorted(bundle_files, key=lambda file: file.path),
    )
    write_dataset_readmes(output_dir, dataset_names)
    write_manifest_files(output_dir, manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    参数:
        无。

    返回:
        argparse.Namespace: 解析后的命令行参数。
    """

    parser = argparse.ArgumentParser(description="准备 Hugging Face Dataset 上传包")
    parser.add_argument("--source", type=Path, default=Path("data"), help="源数据目录，默认 data/")
    parser.add_argument("--output", type=Path, default=Path("tmp/hf_dataset_bundle"), help="输出 bundle 目录")
    parser.add_argument(
        "--repo-id",
        default="BuptZZP/agentmemorybench-data",
        help="目标 Hugging Face dataset repo id",
    )
    parser.add_argument(
        "--link-mode",
        choices=("copy", "hardlink"),
        default="hardlink",
        help="文件进入 bundle 的方式，默认 hardlink，失败时会回退 copy",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="不清空已有输出目录；默认会先删除输出目录后重新生成",
    )
    return parser.parse_args()


def main() -> None:
    """命令行入口。

    参数:
        无，参数来自命令行。

    返回:
        None。执行成功时会打印 bundle 摘要。
    """

    args = parse_args()
    manifest = build_hf_dataset_bundle(
        source_dir=args.source,
        output_dir=args.output,
        repo_id=args.repo_id,
        link_mode=args.link_mode,
        clean_output=not args.no_clean,
    )
    print(f"HF dataset bundle written to: {args.output}")
    print(f"repo_id: {manifest.repo_id}")
    print(f"total_files: {manifest.total_files}")
    print(f"total_bytes: {manifest.total_bytes}")


if __name__ == "__main__":
    main()
