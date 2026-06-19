# Agent Memory Benchmark — 新 Method 接入协议

本文档定义一个新的记忆方法（memory method）接入本框架进行 LoCoMo / LongMemEval
benchmark 测评的完整协议。只要按要求实现本协议，即可自动获得 conversation 级
resume、conversation 级并行和标准实验产物。

---

## 目录

1. [核心概念](#1-核心概念)
2. [必须实现的接口](#2-必须实现的接口)
3. [实体定义](#3-实体定义)
4. [Adapter 编写规范](#4-adapter-编写规范)
5. [TOML 配置文件](#5-toml-配置文件)
6. [注册到 Registry](#6-注册到-registry)
7. [Resume（断点续跑）](#7-resume断点续跑)
8. [Conversation 级并行](#8-conversation-级并行)
9. [效率观测（Efficiency Observability）](#9-效率观测efficiency-observability)
10. [测试要求](#10-测试要求)
11. [约束 & 红线](#11-约束--红线)
12. [完整接入 Checklist](#12-完整接入-checklist)

---

## 1. 核心概念

```
Benchmark Dataset (locomo / longmemeval)
  └── adapter: Converation[], Question[], GoldAnswerInfo[]
        │
        ▼
Method Adapter (你写的)
  ├── add(conversations: list[Conversation]) → AddResult
  └── get_answer(question: Question)           → AnswerResult
        │
        ▼
Runner (框架已有，不改)
  ├── 串/并行调度 conversation
  ├── 写 method_predictions.jsonl / evaluator_private_labels.jsonl
  ├── 检查点 / resume
  └── 效率观测 artifact
        │
        ▼
Evaluator (框架已有，不改)
  └── F1 / LLM Judge / 各类别聚合
```

### 框架不关心的事情

- 你的 method 内部用什么存储（SQLite / Qdrant / pickle / 内存 dict）
- 你的 method 内部用什么 LLM（OpenAI / Ollama / 本地模型）
- 你的 method 内部如何管理 conversation 间隔离

### 框架只关心的事情

1. `add()` 能不能把一组 Conversation 正确写进去
2. `get_answer()` 能不能根据 question.conversation_id 找到正确的记忆并回答
3. 返回的 `AnswerResult` 是否只含公开数据（不含 gold answer）

---

## 2. 必须实现的接口

### 2.1 基础接口

```python
from memory_benchmark.core.interfaces import BaseMemorySystem

class MyMethodAdapter(BaseMemorySystem):

    def add(self, conversations: list[Conversation]) -> AddResult:
        """写入一个或多个 conversation 到记忆系统。

        输入:
            conversations: Conversation 对象列表。每个 Conversation 包含:
                - conversation_id: str       # 唯一标识
                - sessions: list[Session]    # 按时间排序的 session 列表
                - questions: list[Question]  # 该 conversation 的所有 question
                - metadata: dict             # benchmark 元信息

        输出:
            AddResult:
                - conversation_ids: list[str]  # 成功写入的 conversation id
                - metadata: dict               # 公开元信息（如 method 名、配置）
        """

    def get_answer(self, question: Question) -> AnswerResult:
        """根据已写入的记忆回答一个公开问题。

        输入:
            question: Question 对象。关键字段:
                - question_id: str         # 问题唯一标识
                - conversation_id: str     # ← 必须用这个定位到正确的记忆
                - text: str                # 问题文本
                - question_time: str|None  # 问题发生时间（可选）
                - category: str|None       # 问题类别（可选，不用于回答）
                - metadata: dict           # benchmark 元信息（可选）

        输出:
            AnswerResult:
                - question_id: str      # 必须与输入一致
                - conversation_id: str  # 必须与输入一致
                - answer: str           # 你的 method 生成的答案文本
                - metadata: dict        # 可选元信息（method、检索信息等）
        """
```

### 2.2 add() 的行为要求

1. **幂等性**：同一 `conversation_id` 不能重复 `add()`。如果调用方重复传入同一个
   conversation，adapter 应抛出 `ConfigurationError`。

2. **隔离性**：不同 `conversation_id` 的记忆必须严格隔离。一个 conversation 的
   `get_answer()` 不能看到其他 conversation 的记忆。

3. **公开数据**：`Conversation` 对象可能包含 `gold_answers` 字典（如图中 `gold_answers`），
   但 adapter **绝不能**在写入记忆时使用 gold 信息。框架会在传入前通过
   `_make_public_conversation()` 清洗，但 adapter 自身也不应假设 gold 存在。

4. **Session → Turn 遍历**：Conversation 的 sessions 按时间排序，每个 session 含多个
   Turn。每个 Turn 有：
   ```python
   turn.turn_id     # str
   turn.speaker     # str  发言者标识
   turn.content     # str  发言内容
   turn.turn_time   # str  发言时间（格式因 benchmark 而异）
   turn.metadata    # dict 可选元信息
   ```

### 2.3 get_answer() 的行为要求

1. **conversation_id 路由**：使用 `question.conversation_id` 定位正确的记忆库。

2. **不能使用 gold**：`question` 对象不包含 gold answer、evidence、judge label。

3. **answer 字段**：返回纯文本答案，由 evaluator 做后处理（normalize → tokenize → F1）。

4. **metadata 字段**：可写 method 名、检索信息、prompt 等。注意：
   - **不要**在 metadata 中放超大文本（如完整 system prompt），会导致
     `method_predictions.jsonl` 膨胀（已知问题，见 11.5）。

---

## 3. 实体定义

以下为 adapter 会用到的关键实体（完整定义见
`src/memory_benchmark/core/entities.py`）：

### Conversation

```python
@dataclass
class Conversation:
    conversation_id: str             # 唯一标识（如 "conv-30"）
    sessions: list[Session]          # 按时间排序的 session 列表
    questions: list[Question]        # 该 conversation 的所有 question
    gold_answers: dict[str, GoldAnswerInfo]  # 私有，不能传给 method
    metadata: dict[str, Any]         # benchmark 元信息
```

### Session

```python
@dataclass
class Session:
    session_id: str                  # 唯一标识
    turns: list[Turn]                # 对话轮次
    session_time: str | None         # session 发生时间
    metadata: dict[str, Any]
```

### Turn

```python
@dataclass
class Turn:
    turn_id: str                     # 唯一标识
    speaker: str                     # 发言者（如 "user" / "speaker_a"）
    content: str                     # 发言内容
    turn_time: str | None            # 发言时间
    metadata: dict[str, Any]
```

### Question

```python
@dataclass
class Question:
    question_id: str                 # 唯一标识
    conversation_id: str             # ← 所属 conversation
    text: str                        # 问题文本
    question_time: str | None        # 问题时间
    category: str | None             # 类别编号字符串
    options: dict[str, str] | None   # 多选选项
    metadata: dict[str, Any]
```

### GoldAnswerInfo（私有，绝不能传给 method）

```python
@dataclass
class GoldAnswerInfo:
    question_id: str
    answer: str                      # gold answer 文本
    evidence: list[str]              # 证据
    metadata: dict[str, Any]
```

---

## 4. Adapter 编写规范

### 4.1 文件位置

```
src/memory_benchmark/methods/<your_method>_adapter.py
```

### 4.2 基本结构

```python
"""<MethodName> 的 conversation-QA 适配器。

本模块把 <MethodName> 包装成 BaseMemorySystem。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from memory_benchmark.config.settings import PathSettings, OpenAISettings
from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    ConfigurationError,
    Conversation,
    Question,
)
from memory_benchmark.core.interfaces import BaseMemorySystem
from memory_benchmark.core.validators import validate_no_private_keys


@dataclass(frozen=True)
class MyMethodConfig:
    """强类型配置类，字段与 configs/methods/my_method.toml 的 profile section 一一对应。

    必须包含:
        profile_name: str          # 自动填充，不要手动设
        llm_model: str             # reader LLM 模型名
        max_workers: int           # conversation 并行数
        suppress_official_stdout: bool  # 是否压制第三方 stdout
    """

    profile_name: str = ""
    llm_model: str = "gpt-4o-mini"
    max_workers: int = 1
    suppress_official_stdout: bool = False

    def to_manifest(self) -> dict[str, object]:
        """返回不含 secret 的公开配置字典。"""
        return {
            "llm_model": self.llm_model,
            "max_workers": self.max_workers,
        }


class MyMethodAdapter(BaseMemorySystem):
    """<MethodName> 的 conversation-QA 适配器。"""

    def __init__(
        self,
        config: MyMethodConfig,
        path_settings: PathSettings,
        storage_root: Path,
        openai_settings: OpenAISettings | None = None,
        completed_conversations: tuple[Conversation, ...] = (),
        efficiency_collector: Any = None,
    ):
        """初始化适配器。

        输入:
            config: 从 TOML profile 加载的强类型配置。
            path_settings: 项目路径配置。
            storage_root: 当前 run 独占的 method 状态目录。
            openai_settings: OpenAI API 连接的私有配置。
            completed_conversations: resume 时已完成的 conversation。
            efficiency_collector: 框架注入的 efficiency 收集器。
        """

        self._config = config
        self._storage_root = storage_root
        self._states: dict[str, Any] = {}
        # ... 初始化你的 method 后端

    def add(self, conversations: list[Conversation]) -> AddResult:
        conversation_ids = []
        for conv in conversations:
            if conv.conversation_id in self._states:
                raise ConfigurationError(
                    f"Conversation already added: {conv.conversation_id}"
                )
            # ... 把 conv.sessions/turns 写入你的 method 后端
            self._states[conv.conversation_id] = ...
            conversation_ids.append(conv.conversation_id)
        return AddResult(conversation_ids=conversation_ids, metadata={})

    def get_answer(self, question: Question) -> AnswerResult:
        state = self._states.get(question.conversation_id)
        if state is None:
            raise ConfigurationError(
                f"No conversation state: {question.conversation_id}"
            )
        # ... 用 state 检索 + 生成答案
        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer="your answer text",
            metadata={"method": "MyMethod"},
        )
```

### 4.3 Conversation 级隔离

你的 adapter 必须在内部维护 `conversation_id → method_state` 的映射。
框架 runner 会按 conversation_id 调 `add()` 和 `get_answer()`，adapter
负责路由到正确的内部状态。

```python
# 典型做法：内部字典
self._states: dict[str, InternalState] = {}

# add()
state = create_state_for(conversation)
self._states[conversation.conversation_id] = state

# get_answer()
state = self._states[question.conversation_id]
return state.retrieve_and_answer(question)
```

### 4.4 第三方代码管理

- 第三方 method 源码放在 `third_party/methods/<MethodName>/` 下
- **不要修改第三方核心算法代码**（只做调用和配置注入）
- 如果必须修改（如加 observer hook），改动必须：
  1. 可被开关控制（不改变默认行为）
  2. 写入 `docs/method-source-modifications.md` 登记

### 4.5 模块保护

如果你的 method 的 import 涉及操作 `sys.path`（如导入 vendored 目录中的模块），
且支持 `max_workers > 1` 并行，**必须**使用 `threading.Lock` 保护 import 过程，
避免多线程 `sys.path` / `sys.modules` 竞态。参考：
- `memoryos_adapter.py:61` `_MEMORYOS_EVAL_IMPORT_LOCK`
- `lightmem_adapter.py:51` `_LIGHTMEM_IMPORT_LOCK`

---

## 5. TOML 配置文件

### 5.1 文件位置

```
configs/methods/<your_method>.toml
```

### 5.2 格式

```toml
# <MethodName> conversation-QA 的 method profile。

[smoke]
llm_model = "gpt-4o-mini"
max_workers = 1
# ... 你的 method 专属参数

[official_full]
llm_model = "gpt-4o-mini"
max_workers = 1                  # 如需并行，设 > 1
# ... 参数与 smoke 保持一致，仅规模不同
```

### 5.3 规则

1. **必须**有 `[smoke]` 和 `[official_full]` 两个 section。
2. 两个 section 的算法参数**必须完全一致**（仅 `max_workers` 可以不同）。
3. `max_workers` 控制 conversation 级并行度。
4. **不得**在 TOML 中写入真实 API key / token / secret。
5. 配置类必须实现 `to_manifest()` 方法，返回**不含 secret** 的公开字典。

### 5.4 max_workers 规则

| 你的 method 线程安全？ | supports_shared_instance_parallelism | max_workers | 行为 |
|:---:|:---:|:---:|------|
| 是（多线程共享一个实例安全） | `True` | 1 ~ N | 一个实例, N 个线程并行 |
| 否（你的 method 不是线程安全的） | `False`（默认） | 1 | 串行 |
| 否 | `False`（默认） | > 1 | 框架自动创建 N 个独立实例 |

大多数 method 不是线程安全的，设 `False` 即可，框架会自动用独立实例模式并行。

---

## 6. 注册到 Registry

### 6.1 文件位置

```
src/memory_benchmark/methods/registry.py
```

### 6.2 注册示例

```python
# 在 _REGISTRY dict 中添加：
"my_method": MethodRegistration(
    name="my_method",                              # CLI 使用的短名
    display_name="MyMethod",                       # 报告/日志中的显示名
    task_families=frozenset({TaskFamily.CONVERSATION_QA}),
    provided_capabilities=frozenset({
        MethodCapability.CONVERSATION_ADD,
        MethodCapability.ANSWER_GENERATION,
    }),
    profile_sections=(
        ("smoke", "smoke"),
        ("official-full", "official_full"),
    ),
    profile_relative_path=Path("configs/methods/my_method.toml"),
    config_type=MyMethodConfig,                    # 你的配置类
    requires_api=True,                             # 是否需要 API key
    system_factory=_build_my_method_system,        # 工厂函数
    source_identity_factory=build_my_source_identity, # 源码身份
    model_name_getter=_my_method_model_name,       # 从 config 取模型名
    max_workers_getter=_my_method_max_workers,     # 从 config 取 max_workers
    display_name="MyMethod",

    # 以下为可选：
    workload_estimator=None,                       # 预估算量
    allow_smoke_worker_override=False,             # 是否允许 smoke override
    supports_shared_instance_parallelism=False,    # 是否线程安全（默认否）

    # 效率观测（如需）：
    efficiency_model_inventory_getter=_my_efficiency_models,
    efficiency_instrumentation_identity_getter=_my_instrumentation_id,
    retrieval_observation_contract_getter=_separable_retrieval_contract,
),
```

### 6.3 工厂函数

```python
def _build_my_method_system(context: MethodBuildContext) -> BaseMemorySystem:
    """根据运行上下文构造 MyMethod adapter 实例。

    MethodBuildContext 字段:
        config: MyMethodConfig               # 你的强类型配置
        openai_settings: OpenAISettings|None # API key/base_url
        path_settings: PathSettings          # 项目路径
        storage_root: Path                   # 独占的 method 状态目录
        completed_conversations: tuple[Conversation, ...]  # resume 用
        efficiency_collector: EfficiencyCollector | None     # 效率观测
    """

    return MyMethodAdapter(
        config=context.config,
        path_settings=context.path_settings,
        storage_root=context.storage_root,
        openai_settings=context.openai_settings,
        completed_conversations=context.completed_conversations,
        efficiency_collector=context.efficiency_collector,
    )
```

### 6.4 supports_shared_instance_parallelism 详解

| 值 | 含义 | 何时用 |
|:---:|------|------|
| `False`（默认） | method 不是线程安全的 | **几乎所有新 method** — 框架自动创建独立实例来并行 |
| `True` | 多个线程同时调同一个实例的 `add()`/`get_answer()` 安全 | 仅当你的 method 认真做了线程安全（如 Mem0） |

**关键**：设为 `False` 不代表不能并行。框架会为每个 worker 创建独立的
adapter 实例（不同 `storage_root`），每个实例只处理分配到的 conversation
子集。这就是"独立实例模式"——**不需要你的 method 自己处理线程安全**。

---

## 7. Resume（断点续跑）

### 7.1 自动获得的 resume 能力

如果你的 adapter 满足以下条件，框架自动提供 conversation 级 resume：

1. ✅ `add()` 后状态被持久化到 `storage_root` 下（写文件/数据库/等）
2. ✅ 能从 `storage_root` 重新加载已完成 conversation 的状态
3. ✅ 工厂函数接收 `completed_conversations` 参数并在构造时加载这些
   conversation 的状态

### 7.2 resume 时工厂函数的行为

resume 时，`context.completed_conversations` 包含上次 run 已完成的
conversation 对象（不含 gold）。你的工厂函数应该：

```python
def _build_my_method_system(context):
    adapter = MyMethodAdapter(...)
    for conv in context.completed_conversations:
        adapter.load_conversation_state(conv)
    return adapter
```

加载状态后，回答剩余 question 时框架会跳过已完成的 conversation。

### 7.3 不需要实现 turn-level resume

conversation 级 resume 已经足够。turn 级 resume（每 turn 后断点）是可选高级
功能，只有 Mem0 支持，其他 method 不需要。

---

## 8. Conversation 级并行

### 8.1 自动获得的条件

只要满足以下条件，并行**自动生效**，无需额外代码：

1. ✅ 实现了 `add()` 和 `get_answer()`
2. ✅ 在 registry 中注册了 `system_factory`（工厂函数）
3. ✅ TOML 的 `official_full.max_workers > 1`

### 8.2 并行模式

框架根据 `supports_shared_instance_parallelism` 自动选择：

| 模式 | 行为 | 适用 |
|------|------|------|
| 共享实例 | 1 个 adapter 实例，N 个线程共享 | `supports_shared=True` |
| 独立实例 | N 个 adapter 实例，各管 `worker_{idx}/` 子目录 | 默认（推荐） |

### 8.3 实施细节（不用你管）

- conversation 按轮转法分配到 worker（10 conversation × 4 worker =
  worker 0 得 3 个、worker 1 得 3 个、worker 2 得 2 个、worker 3 得 2 个）
- 每个 worker 创建独立 adapter 实例，`storage_root` 后缀 `worker_{idx}/`
- worker 内部串行 add + answer
- 主线程串行写 `method_predictions.jsonl`
- `as_completed` 语义保证先完成的 worker 先返回，不阻塞其他

### 8.4 注意事项

1. **并发 API 调用**：N 个 worker = N 倍并发 API 调用，确保 API key 的 rate limit 允许
2. **本地模型**：如果 method 加载本地 embedding 模型（如 sentence-transformers），
   独立实例模式下每个 worker 加载一份 → N× 模型内存。可以用 `threading.Lock` 保护
   import（如 4.5），但模型本身仍会复制 N 份。建议 `max_workers <= 10`

---

## 9. 效率观测（Efficiency Observability）

### 9.1 基础要求

至少实现 question 级效率观测：在 `get_answer()` 中记录 LLM token 用量。

```python
from memory_benchmark.observability.efficiency.token_counting import (
    resolve_token_usage,
)

class MyMethodAdapter:

    def _record_llm_call(self, prompt_text, output_text, *, api_usage=None):
        collector = self._efficiency_collector
        if collector is None or not collector.enabled:
            return
        usage = resolve_token_usage(
            api_input_tokens=api_usage.prompt_tokens if api_usage else None,
            api_output_tokens=api_usage.completion_tokens if api_usage else None,
            prompt_text=prompt_text,
            output_text=output_text,
            tokenizer=MyTokenizer(self._config.llm_model),
        )
        collector.record_llm_call(
            model_id="my-method-answer-llm",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            token_measurement_source=usage.source,
        )
```

### 9.2 真-API usage vs tokenizer 估算

- **api_usage**：从 OpenAI response 的 `usage.prompt_tokens` / `usage.completion_tokens`
  读取的真实 token 数。只有你能拿到原始 response object 时才可用。

- **tokenizer_estimate**：用本地 tokenizer（如 tiktoken）估算。当你的 method 只有
  文本输出、没有原始 API response 时，用这个。标注为 `tokenizer_estimate`，
  不要冒充 `api_usage`。

### 9.3 model inventory & instrumentation identity

完整的效率观测还需要在 registry 中注册：

- `efficiency_model_inventory_getter`：返回 run 中使用到的所有模型
- `efficiency_instrumentation_identity_getter`：记录观测插桩代码版本

参考 `mem0_adapter.py` 和 `memoryos_adapter.py` 的实现。

---

## 10. 测试要求

### 10.1 最低测试集

| # | 测试内容 | 要求 |
|---|---------|------|
| 1 | adapter `add()` 能正确写入 conversation | 写入后 state 存在 |
| 2 | adapter `get_answer()` 能返回答案 | 答案非空 |
| 3 | 重复 `add()` 同一 conversation 报错 | ConfigurationError |
| 4 | 对未 add 的 conversation 调 `get_answer()` 报错 | ConfigurationError |
| 5 | 并行：`max_workers=2` 下 2 个 conversation 都能完成 | 2/2 completed |
| 6 | 并行不出现竞态（`suppress_official_stdout` 生效） | 无 crash |
| 7 | config 加载：smoke 和 official_full 两个 profile 都能从 TOML 正确解析 | 字段值正确 |
| 8 | resume（如果支持）：先跑 1 个 conversation，resume 模式补跑第 2 个 | 2/2 completed |
| 9 | 中文 docstring：所有类和函数有中文 docstring | 文档规范通过 |
| 10 | source identity：wrapper 源码变化导致 source fingerprint 变化 | 新旧 hash 不同 |

### 10.2 测试文件位置

```
tests/test_<your_method>_adapter.py
tests/test_<your_method>_registered_prediction.py  # 端到端集成测试
```

### 10.3 测试工具

- 使用 `pytest` + `tmp_path` 做文件隔离
- 使用 fake system / fake LLM 避免真实 API 调用
- 参考 `tests/test_memoryos_adapter.py`、`tests/test_mem0_adapter.py`

### 10.4 运行测试

```bash
# adapter 单元测试
uv run pytest tests/test_<your_method>_adapter.py -q

# 端到端集成测试
uv run pytest tests/test_<your_method>_registered_prediction.py -q

# 文档规范
uv run pytest tests/test_documentation_standards.py -q

# compileall
uv run python -m compileall -q src/memory_benchmark tests
```

---

## 11. 约束 & 红线

### 11.1 绝对不能做的事情

1. **不能**把 gold answer / evidence / judge label 传入 method 的 `add()` 或 `get_answer()`
2. **不能**在 TOML 配置或 manifest 中写入真实 API key / token / secret
3. **不能**修改第三方 vendor 的核心算法代码
4. **不能**把 `Conversation.gold_answers` 的内容写入记忆库
5. **不能**伪造 `api_usage`（把 `tokenizer_estimate` 标成 `api_usage`）
6. **不能**为 method × benchmark 笛卡尔积创建专门的 runner 文件

### 11.2 必须做的事情

1. **必须**实现 `add()` 和 `get_answer()` 两个接口
2. **必须**在内部维护 `conversation_id → state` 的映射
3. **必须**把所有类和函数写中文 docstring
4. **必须**把 adapter 写入 `src/memory_benchmark/methods/`
5. **必须**在 `configs/methods/` 下提供 TOML 配置
6. **必须**在 `registry.py` 中注册
7. **必须**先更新 `docs/method-interface-inventory.md` 记录原生接口信息

### 11.3 并行模式下的存储隔离

当 `max_workers > 1` 且 `supports_shared_instance_parallelism=False`（默认）时，
框架会给每个 worker 不同的 `storage_root`（自动追加 `worker_{idx}/` 子目录）。
你的 adapter 不需要为此做任何特殊处理——直接用 `storage_root` 即可。

### 11.4 Benchmark 无关性

你的 adapter 不应依赖特定 benchmark 的数据结构。框架传入的 `Conversation`、
`Session`、`Turn`、`Question` 是统一抽象，所有 conversation-QA benchmark
（LoCoMo、LongMemEval、未来新 benchmark）用同一套接口。你的 adapter 只需
读取这些标准字段即可。

### 11.5 已知问题（你的 adapter 不需要关心，框架后续修复）

1. **method_predictions.jsonl 冗余**：不要在 `AnswerResult.metadata` 里放
   大段重复文本（如完整 system prompt），会导致文件膨胀。建议只放简短标识和
   检索信息。
2. **isolated 模式进度条冻结**：并行模式下终端进度条可能长时间不动，但不影响
   实验结果。
3. **各类别 F1 聚合**：`evaluate` 命令目前只输出总 F1，各类别细分需要手动计算
   （框架后续会自动输出）。

---

## 12. 完整接入 Checklist

按顺序逐项完成：

- [ ] 1. 阅读 `docs/method-interface-inventory.md`，理解现有 method 的接口模式
- [ ] 2. 把第三方源码放到 `third_party/methods/<MethodName>/` 下
- [ ] 3. 在 `docs/method-interface-inventory.md` 中记录原生接口信息：
  - method 原生如何写入记忆
  - method 原生如何检索/回答
  - 原生 LLM/embedding 模型是什么
  - API key/base URL 在哪里配置
  - 哪些字段不能进入 method
- [ ] 4. 编写 adapter：`src/memory_benchmark/methods/<method>_adapter.py`
  - [ ] 强类型配置类（`@dataclass(frozen=True)` + `to_manifest()`）
  - [ ] `__init__()`：接收 config / storage_root / openai_settings 等
  - [ ] `add()`：conversation → 写入记忆
  - [ ] `get_answer()`：question → 检索 + 生成答案
  - [ ] 内部 `conversation_id → state` 映射
  - [ ] 如有 `sys.path` 操作，加 `threading.Lock`
- [ ] 5. TOML 配置：`configs/methods/<method>.toml`
  - [ ] `[smoke]` section（max_workers=1）
  - [ ] `[official_full]` section（算法参数与 smoke 一致）
  - [ ] 无 secret / API key
- [ ] 6. 在 `src/memory_benchmark/methods/registry.py` 注册
  - [ ] `MethodRegistration`（含 factory、source_identity、max_workers_getter 等）
  - [ ] `supports_shared_instance_parallelism=False`（默认）
  - [ ] 工厂函数 `_build_<method>_system(context)`
- [ ] 7. 效率观测（推荐）
  - [ ] question 级 LLM token 记录（至少 tokenizer_estimate）
  - [ ] model_inventory_getter
  - [ ] instrumentation_identity_getter
  - [ ] retrieval_observation_contract_getter
- [ ] 8. 测试
  - [ ] adapter 单元测试（`tests/test_<method>_adapter.py`）
  - [ ] 端到端集成测试（`tests/test_<method>_registered_prediction.py`）
  - [ ] config 加载测试（smoke + official_full）
  - [ ] 并行 smoke 测试（max_workers=2）
- [ ] 9. 验证
  - [ ] `uv run pytest tests/test_<method>_adapter.py -q` 全通过
  - [ ] `uv run pytest tests/test_documentation_standards.py -q` 全通过
  - [ ] `uv run python -m compileall -q src/memory_benchmark tests` exit 0
- [ ] 10. 真实 API smoke（需要用户确认）
  - [ ] `memory-benchmark calibrate-smoke --method <method> --benchmark locomo --confirm-api --max-parallel-runs 1`
  - [ ] 检查 `outputs/<run_id>/artifacts/method_predictions.jsonl` 有合理答案
  - [ ] 检查 `outputs/<run_id>/artifacts/efficiency_observations.prediction.jsonl` 有 token 记录
- [ ] 11. 文档
  - [ ] 更新 `AGENTS.md` 断点
  - [ ] 更新 `docs/current-roadmap.md`
  - [ ] 更新 `docs/handoffs/` 交接记录

---

## 附录：参考文件

| 用途 | 文件 |
|------|------|
| 基础接口 | `src/memory_benchmark/core/interfaces.py` |
| 实体定义 | `src/memory_benchmark/core/entities.py` |
| 已有 adapter 参考 | `src/memory_benchmark/methods/mem0_adapter.py` |
| | `src/memory_benchmark/methods/memoryos_adapter.py` |
| | `src/memory_benchmark/methods/amem_adapter.py` |
| | `src/memory_benchmark/methods/lightmem_adapter.py` |
| Registry 参考 | `src/memory_benchmark/methods/registry.py` |
| TOML 参考 | `configs/methods/mem0.toml` |
| | `configs/methods/memoryos.toml` |
| Runner 实现 | `src/memory_benchmark/runners/prediction.py` |
| 私有数据边界 | 本文档 11.1 节 + `src/memory_benchmark/core/validators.py` |
| 测试参考 | `tests/test_memoryos_adapter.py` |
| | `tests/test_mem0_adapter.py` |
