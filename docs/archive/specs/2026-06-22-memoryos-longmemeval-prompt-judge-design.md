# MemoryOS LongMemEval Prompt And Judge Design

## 背景

当前项目主协议是 `add(conversation) + retrieve(question) -> AnswerPromptResult`。
`AnswerPromptResult.prompt_messages` 由 method adapter 构造完整 answer LLM 输入，
framework 只负责调用统一 answer LLM、记录 artifact 和做指标评测。

用户要求继续支持 MemoryOS 在 LongMemEval 上运行，同时不要把不同来源的 prompt
混为一个事实。最新决策如下：

- MemoryOS 当前 LongMemEval 默认 reader prompt 继续使用 LightMem-style LongMemEval
  prompt，因为它更像 QA prompt，并且便于和 LightMem 论文中的 LongMemEval 流程对比。
- `third_party/methods/MemoryOS-main/memoryos-pypi/prompts.py` 中的 generic prompt
  可以作为额外 profile 支持，但不能替换默认 profile。该 prompt 是 MemoryOS PyPI
  通用会话回复 prompt，不是 LongMemEval 专用 QA prompt。
- A-Mem 本地仓库未发现同等级的通用 answer-reader prompt。A-Mem 当前继续使用现有
  LongMemEval prompt 策略，文档中明确该事实。
- LongMemEval LLM judge 默认走 LightMem LongMemEval 流程，而不是 LongMemEval 官方
  `evaluate_qa.py` 的 `max_tokens=10` 流程。理由是当前实验需要和 LightMem 论文结果
  做横向对比。

## 设计

MemoryOS adapter 增加配置字段：

```python
longmemeval_prompt_profile: str = "lightmem_longmemeval_reader_v1"
```

允许值：

- `lightmem_longmemeval_reader_v1`: 当前默认。保留 `<CONTEXT>`、`<MEMORY>`、
  `<CHARACTER TRAITS>`、`<ASSISTANT KNOWLEDGE>`，并显式使用 `question_time`。
- `memoryos_pypi_generic_v1`: 新增可选 profile。借用 MemoryOS PyPI 的 system/user
  prompt 结构，把 short memory、retrieval queue、user profile、long-term knowledge
  和 assistant knowledge 填入对应槽位；`query` 包含 LongMemEval 的 question time 和
  question text。

LongMemEval judge 增加 LightMem-compatible 调用路径：

- Prompt 文本沿用 LightMem `experiments/longmemeval/run_lightmem_gpt.py` 的
  `get_anscheck_prompt()` 语义。
- 真实调用使用 Chat Completions 风格，而不是 Responses API。
- 默认参数对齐 LightMem wrapper：`temperature=0.0`、`top_p=0.8`、`max_tokens=2000`。
- compact 输出按 LightMem 的 yes/no 判定解析。detailed 模式保留本项目 JSON 输出，
  仅用于调试，不作为论文对比默认路径。

## 非目标

- 不新增 A-Mem generic prompt。
- 不把 MemoryOS PyPI prompt 设为默认 LongMemEval prompt。
- 不在本次实现多 provider LLM runtime。
- 不启动真实 API full/smoke 实验。
