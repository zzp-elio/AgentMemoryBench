# 2026-06-17 README GitHub 入口化交接

## 本次任务

用户要求更新根目录 `README.md` 并推送到 GitHub。目标是让 README 从内部开发说明转为
GitHub 项目入口，同时保留当前核心架构、接口、运行命令和安全边界。

## 已完成

- README 标题更新为 `AgentMemoryBench`。
- 增加 GitHub 仓库链接 `buctzzp/AgentMemoryBench`。
- 明确当前范围：conversation + QA、LoCoMo / LongMemEval、Mem0 / MemoryOS / A-Mem /
  LightMem、PrefEval 已移除。
- 明确 `data/`、`models/`、`outputs/`、`third_party/benchmarks/`、`paper-make/` 和
  `.env` 不进入 Git。
- 把本地绝对路径链接改为 GitHub 可用的相对链接。
- 压缩历史 MemoryOS smoke 细节，保留统一 CLI、配置、实验输出、日志和验证命令。
- 明确真实 API prediction / judge / full profile 必须显式确认。

## 验证

已运行：

```bash
uv run pytest tests/test_documentation_standards.py tests/test_method_official_smoke_profiles.py -q
uv run python -m compileall -q src/memory_benchmark tests
uv run python - <<'PY'
from pathlib import Path
text = Path("README.md").read_text(encoding="utf-8")
for required in ["项目层次", "运转逻辑", "日志结构", "验证命令"]:
    print(required, required in text)
PY
rg -n "/Users/wz|Agent Memory Benchmark Framework" README.md || true
```

结果：

- focused 文档/profile 测试：`6 passed`
- `compileall`：exit 0
- README 必需关键词：全部存在
- README 无 `/Users/wz` 本地绝对路径，无旧标题

## 后续

本次只更新 README 和短交接，不改运行代码、不启动真实 API 实验。后续若继续做项目文档一致性，
建议单独审查 `docs/architecture.md` 等历史文档中与最新 AGENTS 状态不一致的旧断言。
