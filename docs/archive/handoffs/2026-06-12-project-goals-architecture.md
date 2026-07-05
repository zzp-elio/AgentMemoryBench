# 项目目标与长期架构对齐交接

日期：2026-06-12

## 状态

用户已经确认新的长期项目目标和架构方向。本轮只更新文档，没有修改 Python 代码、第三方
源码、benchmark 数据或实验产物。

主设计：

- `docs/superpowers/specs/2026-06-12-project-goals-architecture-design.md`

同步更新：

- `AGENTS.md`
- `README.md`
- `docs/architecture.md`
- `docs/benchmark-scope.md`
- `docs/method-interface.md`
- `docs/superpowers/specs/2026-06-02-conversation-qa-refactor-design.md`

补充整理：

- 压缩了 `AGENTS.md` 中已完成阶段的实现细节，使其继续作为入口和导航，而不是历史报告。
- 明确 HaluMem、MemBench、Mem-Gallery 不能适配 conversation + QA 时，应等待新的真实
  task family 需求，不能硬塞进当前实体。
- 标记旧设计中的“不做并发”“不记录效率观测”为已被后续设计取代的阶段性约束。

## 已锁定方向

- 长期支持多个 task family，当前只实现 `conversation_qa`。
- Phase 1 先用 LoCoMo 打通各个 method，再接 LongMemEval。
- `predict` 与 `evaluate` 独立恢复，`run` 只是便利组合。
- 官方 method 通过 CLI 和 Python API；自定义 method 当前通过 Python API 传入实例。
- method 分为 `end_to_end` 和 `memory_module`；后者由框架 fixed-reader wrapper 生成答案。
- 兼容性使用 task family + required/provided capabilities，不维护笛卡尔积白名单。
- 配置分为 `official`、`smoke`、`custom`，使用分层 TOML，不创建 method × benchmark
  配置文件矩阵。
- 一个 `run_id` 对应不可变实验，resume 只能继续完全兼容的运行。
- 效率评测只规划 Retrieval Latency、Memory Context Tokens、Memory Update Cost。
- update tokens 分别记录 LLM input/output tokens 和 embedding input tokens。
- 效率指标基于 prediction 阶段逐操作原始 observation 离线聚合。
- benchmark 自动下载、排行榜、第二种 task family、插件发现和完整效率系统暂不实施。
- 官方 method 源码固定版本、手动升级，并遵守第三方许可证。

## 目录方向

长期目标：

```text
third_party/
  benchmarks/
  methods/
```

当前 `benchmarks/` 约 6GB，且存在大量路径引用。本轮没有移动；必须在单独迁移计划中完成
路径契约、数据指纹和回归验证。

`dataset数据结构/` 与 `benchmark测评流程参考/` 后续迁入 `docs/references/`，tests
后续按 unit/integration/api/contract 分类。这些均未在本轮执行。

## 下一步

先让用户审阅主设计文档。确认后使用 writing-plans 制定分阶段实施计划，建议顺序：

1. MemoryOS 迁入 TOML、method registry 和通用 runner。
2. 清理明确生成物和无效空壳。
3. tests 分类与超大测试文件拆分。
4. 参考资料迁入 `docs/references/`。
5. benchmark 外部资产目录迁移。
6. LoCoMo 多 method 闭环稳定后迁移 LongMemEval。
7. 最后单独设计 efficiency observation schema。

API 尚未充值，不启动 Mem0 official-full。

## 本轮验证

2026-06-12 已执行：

```bash
uv run pytest tests/test_documentation_standards.py -q
```

结果：`5 passed`。

同时检查了本轮 8 个关键文档及其相对 Markdown 链接，全部路径存在；主设计、`AGENTS.md`
和 `README.md` 中未发现 `TBD`、`TODO`、`待定` 或 `placeholder` 占位内容。本轮未执行
付费 API、benchmark 实验或 Python 业务代码回归。
