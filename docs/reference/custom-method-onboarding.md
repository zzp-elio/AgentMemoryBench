⚠ **2026-07-07 核查：本文全文仍描述 v2 协议（`BaseMemoryProvider` + `add()/retrieve()` 返回 `AnswerPromptResult`），当前主协议已升级为 v3（`MemoryProvider` + `ingest()/retrieve()` 返回 `RetrievalResult`，见 [spec-protocol-v3.md](../workstreams/ws02-phase1-matrix/spec-protocol-v3.md)），待 ws03 重写或随 M-C 阶段同步更新。**

# Custom Method Onboarding

本指南面向普通用户：你已经有自己的 memory method，希望在 AgentMemoryBench 已集成的
conversation + QA benchmark 上跑实验，并和内置 method 对比。

## 最小接入面

用户自定义 method 第一版只需要实现 `BaseMemoryProvider`：

```python
from memory_benchmark.core import (
    AddResult,
    AnswerPromptResult,
    Conversation,
    PromptMessage,
    Question,
)
from memory_benchmark.core.interfaces import BaseMemoryProvider


class MyMemory(BaseMemoryProvider):
    def __init__(self) -> None:
        # 第一版要求无参数构造。
        # 你的 API key、数据库地址、模型参数可以由你自己的代码读取。
        self.memory_by_conversation: dict[str, str] = {}

    def add(self, conversation: Conversation) -> AddResult:
        snippets: list[str] = []
        for session in conversation.sessions:
            for turn in session.turns:
                snippets.append(f"{turn.speaker}: {turn.content}")
        self.memory_by_conversation[conversation.conversation_id] = "\n".join(snippets)
        return AddResult(conversation_ids=[conversation.conversation_id])

    def retrieve(self, question: Question) -> AnswerPromptResult:
        memory = self.memory_by_conversation.get(question.conversation_id, "")
        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            prompt_messages=[
                PromptMessage(role="system", content="Answer using the memory."),
                PromptMessage(
                    role="user",
                    content=f"Memory:\n{memory}\n\nQuestion: {question.text}",
                ),
            ],
            metadata={"answer_context": memory},
        )
```

`retrieve()` 返回的 `prompt_messages` 是最终交给 answer LLM 的完整 role messages。
如果你的算法需要 query rewrite、检索、rerank、压缩、格式化 prompt，这些都应该在
`retrieve()` 内部完成。框架只负责把这些 messages 发给统一 answer LLM 并保存 artifact。

## 运行方式

假设你的类路径是：

```text
my_project.my_adapter:MyMemory
```

可以运行 smoke：

```bash
uv run memory-benchmark predict smoke \
  --root . \
  --method-class my_project.my_adapter:MyMemory \
  --benchmark locomo \
  --run-id my-memory-locomo-smoke \
  --allow-api \
  --conversations 1 \
  --rounds 20 \
  --questions-per-conversation 1 \
  --workers 1
```

自定义 method 不需要写 AgentMemoryBench 的 TOML profile，也不需要注册 source identity。
内置 method 的 `configs/` 只服务我们维护的 Mem0、MemoryOS、A-Mem、LightMem 等白盒
深度集成。

## 并行契约

自定义 method 默认只允许 `workers=1`。如果你确认自己的 method 支持多个实例并行运行，
可以显式传：

```bash
--workers 4 --allow-unsafe-custom-parallel
```

这不是框架证明你的后端安全，而是你确认自己已经处理好以下问题：

- `retrieve(question)` 只读取 `question.conversation_id` 对应的记忆。
- 不同 `run_id` 不共用未隔离的数据库、文件、collection、namespace 或 graph。
- 不同 benchmark 不共用未隔离的状态。
- 多个 worker 如果写同一个外部后端，该后端必须支持并发写，且你必须做 namespace/filter
  隔离。
- 如果多个 worker 写普通文件，你必须自己加锁或拆分到不同文件。

## Resume 与失败重试

框架会记录 prediction artifact、question status 和 conversation status。对于自定义
method，第一版只做轻量契约：

- `failed_answer`：表示记忆已经写入，只是回答阶段失败；`--retry-failed` 可以只补未完成
  question，不重新 `add()`。
- `failed_ingest`：表示 `add()` 阶段可能已经写入了部分脏状态；默认跳过，显式
  `--retry-failed` 也会 fail closed，避免重复写入污染记忆。

如果你希望未来支持安全重跑 `failed_ingest`，需要提供干净重试策略，例如
`reset_conversation(conversation_id)`、attempt namespace 或等价清理机制。当前版本不会
自动清理用户黑盒后端。

## 框架会记录什么

框架保证记录自己能看到的内容：

- 输入的公开 questions。
- method 返回的 `answer_prompts.prediction.jsonl`。
- answer LLM 生成的 `method_predictions.jsonl`。
- framework 层可观测的 memory build 总耗时、retrieval 耗时、answer 耗时和 answer LLM
  token usage。

框架不会强制观测用户黑盒 method 内部的 LLM、embedding、rerank 或数据库调用。内置 method
有更细的 observer，是因为它们属于项目维护的白盒 adapter。
