# 项目结构与数据入口迁移设计

日期：2026-06-14

## 目标

把运行时数据、第三方官方仓库和研究参考文档分成三个职责明确的层次：

```text
data/                    # adapter 运行时唯一 dataset 入口
third_party/benchmarks/  # 官方 benchmark 仓库，保持完整、只读
docs/                    # 数据结构和测评流程参考
```

迁移完成后，框架代码不得再从第三方 benchmark 仓库内部读取 dataset。

## 目标目录

```text
data/
  halumem/
    HaluMem-Medium.jsonl
    HaluMem-Long.jsonl
  locomo/
    locomo10.json
  longmemeval/
    longmemeval_s_cleaned.json
    longmemeval_m_cleaned.json
  mem_gallery/
    dialog/
    image/
    prompts/
  membench/

third_party/
  benchmarks/
    HaluMem-main/
    LongMemEval-main/
    Mem-Gallery-main/
    Membench-main/
    locomo-main/
  methods/

docs/
  dataset_structures/
  evaluation_workflows/
```

目录名统一使用小写 snake_case；官方仓库内部结构和文件名保持不变。

## 数据真实性

- `data/locomo/locomo10.json` 已与官方仓库文件进行 SHA-256 比较，内容一致。
- `data/longmemeval/` 的 S/M 两个 cleaned 文件已比较，内容一致。
- `data/halumem/` 的 Medium/Long 两个 JSONL 已比较，内容一致。
- `data/mem_gallery/dialog/` 和 `data/mem_gallery/image/` 的 1511 个文件与官方
  `benchmark/data/` 内容一致；`data/mem_gallery/prompts/` 的 4 个 prompt 与官方
  `benchmark/prompt/` 内容一致。
- `data/membench/` 当前为空；本次只保留目录语义，不伪造或猜测核心文件集合。

迁移时先规范目录层级，再执行文件数、相对路径和 SHA-256 清单比较。第三方仓库仍保留
其自带 dataset，作为事实核验和版本审计来源。

## 路径配置

`PathSettings` 增加：

```python
data_root: Path
third_party_benchmarks_root: Path
```

保留：

```python
third_party_methods_root: Path
```

删除运行时对旧 `benchmarks_root` 的依赖。若为了短期兼容保留该属性，它只能作为明确标记
为 deprecated 的 alias，并在本阶段结束前删除。

adapter 只能通过 `data_root` 或 registry 声明的 canonical dataset 相对路径读取数据。
第三方源码身份和论文/代码核验通过 `third_party_benchmarks_root` 定位。

## Adapter 与 Registry

LoCoMo canonical source：

```text
data/locomo/locomo10.json
```

LongMemEval canonical sources：

```text
data/longmemeval/longmemeval_s_cleaned.json
data/longmemeval/longmemeval_m_cleaned.json
```

本阶段只改变路径，不在同一提交中开放 LongMemEval-M 或 prediction。多 variant 能力属于
后续 Phase F，避免把 6GB 目录迁移与行为变化混在一起。

registry 的 `source_relative_paths`、dataset metadata `source_path` 和 fingerprint 都使用
canonical `data/` 路径。

## 迁移安全

执行顺序：

1. 记录受保护实验目录聚合哈希和完整离线测试基线。
2. 写路径契约测试，使旧路径预期先失败。
3. 移动参考文档和第三方仓库。
4. 规范 `data/` 目录名和 Mem-Gallery 层级。
5. 更新第一方路径配置、adapter、registry、runner 和测试。
6. 检查第一方代码不存在旧路径引用。
7. 比较 canonical dataset 与第三方仓库内官方副本。
8. 运行完整离线回归。
9. 再次验证受保护实验目录哈希。

第三方仓库整体移动，不修改其内部文件。历史 handoff 中的旧路径只作为历史记录保留，
但 `AGENTS.md`、README 和当前架构文档必须更新。

## 不在本阶段实施

- LongMemEval 多 variant 行为。
- HaluMem adapter。
- MemoryOS 并发改造。
- MemoryOS PyPI backend。
- tests 目录分组。
- 删除第三方仓库自带 dataset。
- 全量 API 实验。

这些内容保留在 `docs/current-roadmap.md`，分别进入后续独立计划。
