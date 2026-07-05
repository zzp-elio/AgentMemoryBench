# 2026-06-20 Retrieve-First 设计文档交接

## 背景

用户提出将当前 method 主协议从 `add + get_answer` 重构为：

```text
add(conversation)
retrieve(question) -> formatted_context
framework reader(answer_llm + prompt) -> answer
```

经核对当前四个 method：

- Mem0、A-Mem、LightMem 当前 `get_answer()` 本质都是 adapter 内部 `retrieve + prompt + LLM`。
- MemoryOS 也可以拆为 `retrieval_system.retrieve()` 与 answer prompt/LLM。

因此用户和 Codex 已对齐：后续主线只保留 memory-module evaluation，不再要求新 method 实现
`get_answer()`。

## 本次新增文档

- `docs/superpowers/specs/2026-06-20-retrieve-first-memory-module-design.md`

该 spec 明确：

- 新主接口：`add(conversation)` + `retrieve(question)`。
- `retrieve()` 核心输出：可直接注入 prompt 的 `formatted_context`。
- framework reader 统一负责 answer prompt、answer LLM 和最终 answer。
- 内置 method 保留深度插桩。
- 用户自定义 method 不强制内部 LLM/embedding 观测。
- 当前阶段仍统一默认 OpenAI-compatible `gpt-4o-mini`。
- Future 可以修改第三方 method 的 provider/client 适配层以支持更多 internal LLM provider，
  但不能改核心算法流程。

## 本次同步更新

- `AGENTS.md`
  - 当前主线改为 retrieve-first 架构重构。
  - 核心协议从旧 `add(list) + get_answer` 改为目标 `add(conversation) + retrieve`。
  - 恢复读取顺序加入 retrieve-first spec。
- `README.md`
  - 项目描述改为 method 写入/检索记忆、framework reader 生成回答。
  - 运转逻辑改为 `add -> retrieve -> framework reader -> evaluate`。
  - Method 接口示例改为 retrieve-first，并标注当前代码尚未迁移。
- `docs/current-roadmap.md`
  - 新增 Phase K：Retrieve-First Memory Module 协议重构。
  - 把正式实验矩阵标注为需等待 retrieve-first 迁移方案确认。
- `docs/task-ledger.md`
  - 新增 closed 项：retrieve-first 架构设计。
  - 新增 open 项：retrieve-first 主协议实现。
- `docs/method-interface-inventory.md`
  - 更新强规则和四个 method 的迁移说明。
  - 修正 Mem0 resume 状态为 conversation-level。

## 下一步

1. 用户审阅 retrieve-first spec。
2. 若用户确认，使用 writing-plans 流程写实施计划。
3. 实现前不得删除旧 `get_answer()` 主路径；先做兼容迁移。
4. 实现阶段需要新增 retrieve artifact、framework reader、prompt 校验和 retrieve/answer
   分阶段 resume。

## 验证

本次只做文档更新，未改代码逻辑，未执行真实 API。

需运行：

```bash
uv run pytest tests/test_documentation_standards.py -q
git diff --check
```
