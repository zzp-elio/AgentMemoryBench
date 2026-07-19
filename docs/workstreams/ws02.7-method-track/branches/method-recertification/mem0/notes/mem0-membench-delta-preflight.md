# Mem0 × MemBench current-main 差量预检

> actor：Claude Sonnet 5（Claude Code，本会话系统提示确认，未经跨模型接管）。
> worktree：`/Users/wz/Desktop/mb-actor-mem0-membench`，branch
> `actor/mem0-membench-delta-preflight`，从 `main@6643e56`（`docs(mem0): issue
> parallel recertification audits`）切出。
> 范围：离线差量审计，**零真实 API、零生产代码改动**；只新增本 note。
> subagent 使用：无。全部读源码、构造探针与写作均由本 actor 会话直接完成。

## 0. 唯一判词

**`READY_FOR_JOINT_RULING`**

无任何卡内承重事实被 current-main 源码推翻；发现一处非阻塞代码缺口（§6.3），
不影响本轮 census 或既有 B1-B11/frozen 结论，留给架构师裁是否需要后续实现卡。

## 1. 必读清单与读序（已完成）

1. `AGENTS.md`（项目入口、硬规则）。
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊/断点（截至
   2026-07-19：LightMem method-frozen-v3 关闭，Mem0 六线差量预检卡已就绪）。
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/README.md`
   （六卡并行拓扑与合流门）。
4. `docs/reference/actor-handbook.md`（全文，含 §6 常见坑、§7 好行为判例）。
5. `docs/survey/异常情况/membench.md`（M-S1/M-T1/M-T2/M-T3/M-Q1/M-G1/M-G2/M-A1/M-L1
   全表，§7 LightMem 差分与 smoke 边界，§8 回归锚）。
6. `docs/reference/integration/mem0.md`（B1-B11 现行结论，重点 B2/B4/B5/B9/B11）。
7. 本卡 `docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/
   cards/actor-prompt-mem0-membench-delta-preflight.md` §3 列出的全部 current-main
   源码与测试文件（见 §3 逐个列出）。

`data/membench/` 在本 worktree 不存在（未挂真实数据，也无软链）——按卡"缺 data
可只读软链"的许可，本轮全部探针使用与真实 schema 逐字节一致的合成 fixture（§4），
不读取、不下载、不联网获取真实 8 文件。

## 2. §3 源码逐个读毕（current-main，非 legacy）

| 文件 | 关键发现锚点 |
| --- | --- |
| `src/memory_benchmark/benchmark_adapters/membench.py` | `_turns_from_step`/`_build_step_turn`（拆分+marker 计算）、`_membench_evidence_group_sets`（gold group）、`_membench_turn_time`（双格式正则）、`session_time` 硬编码 `None`（724-734 行注释与实现） |
| `src/memory_benchmark/runners/event_stream.py` | `build_turn_events` 原样保留 `turn.metadata`；`GranularityAggregator._aggregate_turns` 按 raw 顺序逐条 yield，不排序、不合并 |
| `src/memory_benchmark/methods/registry.py` | `_mem0_consume_granularity()`（202-211 行）：membench 落入默认分支 `return "turn"`（不在 `{longmemeval, halumem}` 或 `== "beam"`）；对照 `_lightmem_consume_granularity()`（214-223 行）membench 走 `"pair"` —— **两个 method 对同一 benchmark 声明不同粒度，均合法，各自由 registry 显式声明，非隐式猜测** |
| `src/memory_benchmark/methods/mem0_adapter.py` | `ingest()`/`_ingest_native_turn()`（504-539 行）、`_turn_to_message()`/`_effective_time_prefix()`（1443-1501 行）、`_add_with_provenance()`/`_source_turn_ids_for_memory()`（1703-1756 行）、`_retrieve_native()`/`_build_retrieval_evidence()`（979-1118 行）、`_reader_prompt_kind()`/`_reader_messages()`（1851-1907 行，见 §6.3） |
| `configs/methods/mem0.toml` | 只有 `["smoke"]`/`["official_full"]` 两个 section，**无 `author_membench`**——与 mem0.md 现行政策一致（MemBench 无 Mem0 官方 harness，未来若加需显式声明"无"，见 §6.3） |
| `src/memory_benchmark/benchmark_adapters/registry.py` | MemBench 注册 `prompt_track="unified"`、`unified_prompt_builder=build_membench_unified_answer_prompt`——确认生产主路径**不会**调用 §6.3 提到的 legacy native 答题通道 |
| `src/memory_benchmark/evaluators/membench_recall.py` / `membench_source_accuracy.py` / `membench_choice_accuracy.py`（registry 见 `evaluators/registry.py:396-424`） | recall evaluator `_ALLOWED_GRANULARITIES = frozenset({"turn"})`，与 Mem0 `_build_retrieval_evidence()` 对 membench 声明的 `granularity="turn"` 精确匹配（§6.2） |
| `tests/test_membench_conversation_adapter.py`、`tests/test_membench_registered_prediction.py`、`tests/test_mem0_adapter.py` | 既有回归覆盖模式确认（`FakeMemoryBackend`、`build_turn_events`+`GranularityAggregator` v3 路径测试范式），本轮探针复用同一范式但改用真实 `MemBenchAdapter` 输出而非合成单-turn 字面量（§4） |

third_party 未改；Mem0 官方仓库（`third_party/methods/mem0-main`）与
`third_party/benchmarks/`（`memory-benchmarks` vendored prompt module）本轮**未新增
调用**，只确认 `_reader_prompt_kind()` 在特定分支下仍会加载 LongMemEval 官方 prompt
模块（§6.3）——**Mem0 官方仓库没有 MemBench 专用 harness，明确写"无"**：不存在
`get_answer_generation_prompt` 之类的 MemBench 专属 vendored 模块，`_build_mem0_*`
系列只有 locomo/longmemeval/beam 三个,没有 membench 变体。

## 3. 中心问题裁决：FirstAgent 两 child 是一次 pair add 还是两次 turn add

**当前生产行为：两次独立 turn add，不是 pair add。**

- `registry.py::_mem0_consume_granularity("membench")` 返回 `"turn"`（非 `"pair"`）。
- `event_stream.py::GranularityAggregator("turn")._aggregate_turns()` 按 canonical
  turn 逐条（不按 step 配对）产出 `TurnEvent`，FirstAgent 一个 dict step 展开出的
  `1:user`/`1:assistant` 两条 canonical child 各自成为独立 `TurnEvent`。
- `mem0_adapter.py::ingest(TurnEvent)` → `_ingest_native_turn()` → `_add_with_provenance([single_message], source_turn_ids=(event.turn_id,), ...)`：**每条 canonical
  child 单独调用一次官方 `Memory.add()`**，`messages` 列表长度恒为 1。
- 与 LightMem 对照（`_lightmem_consume_granularity("membench") == "pair"`）：同一
  FirstAgent dict step 在 LightMem 侧是一次 pair batch，在 Mem0 侧是两次独立 turn
  batch——这不是矛盾，是两个 method 各自显式声明、registry 强类型区分的合法差异。

本卡未预设"必须照 LightMem pair"或"逐 turn 一定正确"；上述是 current-main 的**实际
行为**，供联合裁决判断该行为是否需要改判（例如是否要求 Mem0 也按 pair batch 写入以
更贴近"user+assistant 同一交换"的语义），本 note 只陈述事实,不代为裁决。

## 4. 生产调用序列探针（8 类反例覆盖，零 API）

### 4.1 探针构造

真实入口：`MemBenchAdapter`（合成 fixture，schema 与官方 8 文件逐字节一致）→
`build_turn_events()`（真实 `event_stream.py`）→
`GranularityAggregator(consume_granularity=registry._mem0_consume_granularity("membench"))`（真实
`registry.py` 函数，非硬编码）→ `Mem0.ingest()`（真实 `mem0_adapter.py`，仅
`memory_backend`/`reader_client` 注入 fake，等价于
`tests/test_mem0_adapter.py::FakeMemoryBackend` 范式）→
`Mem0.retrieve(RetrievalQuery)`（真实 `_retrieve_native()`）。

探针脚本（Claude Code 会话临时脚本，未提交仓库；按 actor-handbook 要求，构造与
stdout 逐字进本 note）：

```python
# /private/tmp/claude-501/-Users-wz-Desktop-memoryBenchmark/
#   548f1bf9-0d44-46ea-b440-67a640f84548/scratchpad/mem0_membench_probe.py
"""Mem0 x MemBench current-main production call-sequence probe (offline, no real API)."""
from __future__ import annotations
import json, sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path("/Users/wz/Desktop/mb-actor-mem0-membench")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from memory_benchmark.benchmark_adapters.membench import MemBenchAdapter
from memory_benchmark.methods.mem0_adapter import Mem0, Mem0Config
from memory_benchmark.methods.registry import _mem0_consume_granularity
from memory_benchmark.runners.event_stream import (
    GranularityAggregator, build_turn_events, default_isolation_key,
)
from memory_benchmark.core.provider_protocol import (
    RetrievalQuery, TurnEvent, TurnPair, SessionBatch,
)

SCRATCH = Path(".../scratchpad/mem0_membench_fixture")

class FakeMemoryBackend:
    """记录 Mem0 add() 调用的无网络 fake backend（结构与 tests/test_mem0_adapter.py 一致）。"""
    def __init__(self):
        self.add_calls = []
    def add(self, messages, **kwargs):
        self.add_calls.append({"messages": messages, **kwargs})
        return {"results": [{"id": f"m{len(self.add_calls)}", "memory": messages[0]["content"], "event": "ADD"}]}
    def search(self, query, **kwargs):
        return {"results": []}

class FakeReaderClient:
    """本探针不调用 get_answer，仅占位满足 Mem0.__init__ 签名。"""
    pass

# ... _write_fixture / _load_conversations 用 MemBenchAdapter(project_root, variant,
#     source_relative_paths=(rel,)) 真实加载 8 类合成 fixture（见 4.2 payload）...

def run_conversation(conv, mem0_granularity):
    isolation_key = default_isolation_key("probe_run", conv.conversation_id)
    events = tuple(build_turn_events(conv, isolation_key))
    aggregator = GranularityAggregator(mem0_granularity)
    backend = FakeMemoryBackend()
    system = Mem0(
        config=Mem0Config.smoke(), memory_backend=backend, reader_client=FakeReaderClient(),
        storage_root=SCRATCH / "mem0-state" / conv.conversation_id,
        consume_granularity=mem0_granularity, benchmark_name="membench",
    )
    for signal in aggregator.aggregate(events, isolation_key=isolation_key):
        if isinstance(signal, (TurnEvent, TurnPair, SessionBatch)):
            system.ingest(signal)
    query = RetrievalQuery(
        isolation_key=isolation_key, query_text=conv.questions[0].text,
        question_time=conv.questions[0].question_time, top_k=20, purpose="qa",
        source_question=conv.questions[0],
    )
    retrieval_result = system.retrieve(query)
    # ... print canonical turns / private evidence groups / emitted units /
    #     backend.add_calls / provenance sidecar / retrieval_result ...

def main():
    granularity = _mem0_consume_granularity("membench")  # -> "turn"
    # 4 个合成源文件，5 个 conversation，覆盖卡 §4 全部 8 类场景（见 4.2）
```

完整可运行版本仍留在 scratchpad（会话私有、不提交仓库）；本 note 已把**构造逻辑**
与**完整真实 stdout**（§4.3）逐字收录，满足 actor-handbook "临时脚本不提交时 durable
note 必须自包含"的要求。

### 4.2 8 类场景 → fixture 映射

| 卡 §4 场景 | fixture 位置 | 关键设计 |
| --- | --- | --- |
| 1. 0-10k FirstAgent 一个 dict step | `0-10k/FirstAgentDataHighLevel...` `simple/colon_and_order` tid=`s1t1` | 单 dict step，colon 时间格式 |
| 2. 0-10k ThirdAgent 两个连续 string step | `0-10k/ThirdAgentDataLowLevel...` `simple/no_colon_pair` tid=`t1t1` | 两个连续 observation string，均无冒号格式 |
| 3. 两种 `time:`/`time'` 尾注 | 同上两条 fixture 分别用 colon（场景1/6）与 no-colon（场景2）格式，与真实数据分布一致（无冒号仅见于 ThirdLow） |
| 4. 100k FirstAgent：有时 + 无时 noise + 下一有时 step | `100k/FirstAgentDataHighLevel...` `comparative/noise_and_time` tid=`n1` | 3 个 dict step：timed→noise(纯叙述无 place/time 后缀)→timed |
| 5. 100k ThirdAgent 同形 | `100k/ThirdAgentDataHighLevel...` `comparative/noise_and_time` tid=`n2` | 3 个 string step，同形 |
| 6. 时间倒序但 raw 顺序不变 | `0-10k/FirstAgentDataHighLevel...` `simple/colon_and_order` tid=`s1t2` | step0=20:53，step1=18:32（倒序），QA.target_step_id=[0,1] |
| 7. marker 严格 boolean | 见 §4.4（复用既有回归层，非本探针新造） |
| 8. session/question time 都在但 history turn time=None | 场景 4/5 天然覆盖：QA.time 存在、`session_time` 恒 `None`、noise turn `turn_time=None` |

### 4.3 完整真实 stdout（`uv run python mem0_membench_probe.py`，退出码 0，零 API）

```text
registry._mem0_consume_granularity('membench') == 'turn'
====================================================================================================
CONVERSATION first-high-simple-colon_and_order-s1t1
session_time = None
QA.question_time = '2024-10-01 08:13' Tuesday
-- canonical turns --
   {'turn_id': '1:user', 'speaker': 'user', 'normalized_role': 'user', 'content': "I watched Inception yesterday. (place: Boston, MA; time: '2024-10-01 08:00' Tuesday)", 'turn_time': '2024-10-01 08:00', 'source_step_index': 0, 'source_step_role': 'user', 'source_timestamp_embedded_in_content': True}
   {'turn_id': '1:assistant', 'speaker': 'agent', 'normalized_role': 'assistant', 'content': "Got it, Inception noted. (place: Boston, MA; time: '2024-10-01 08:00' Tuesday)", 'turn_time': '2024-10-01 08:00', 'source_step_index': 0, 'source_step_role': 'agent', 'source_timestamp_embedded_in_content': True}
-- private evidence_group_sets (evaluator-only, NOT sent to method) --
   {'unit_id': '0', 'child_ids': ('1:user', '1:assistant'), 'mapping_status': 'mapped'}
-- GranularityAggregator(consume_granularity='turn') emitted units --
  [unit 1] TurnEvent turn_id=1:user role=user
  [unit 2] TurnEvent turn_id=1:assistant role=assistant
  (signal) SessionRef SessionRef(isolation_key='probe_run_first-high-simple-colon_and_order-s1t1', session_id='s1')
  (signal) UnitRef UnitRef(isolation_key='probe_run_first-high-simple-colon_and_order-s1t1')
-- Memory.add() calls captured: 2 --
  [add #1] run_id='probe_run_first-high-simple-colon_and_order-s1t1'
           messages=[{'role': 'user', 'content': "user: I watched Inception yesterday. (place: Boston, MA; time: '2024-10-01 08:00' Tuesday)"}]
           metadata={'conversation_id': 'first-high-simple-colon_and_order-s1t1', 'session_id': 's1', 'turn_id': '1:user', 'speaker': 'user', 'session_time': '2024-10-01 08:00', 'turn_time': '2024-10-01 08:00'}
           prompt="The observation date and time for this message is '2024-10-01 08:00'. Resolve relative time expressions such as 'yesterday', 'today', and 'last week' only against this observation time, even if another current or observation date appears elsewhere in the extraction prompt."
  [add #2] run_id='probe_run_first-high-simple-colon_and_order-s1t1'
           messages=[{'role': 'assistant', 'content': "agent: Got it, Inception noted. (place: Boston, MA; time: '2024-10-01 08:00' Tuesday)"}]
           metadata={'conversation_id': 'first-high-simple-colon_and_order-s1t1', 'session_id': 's1', 'turn_id': '1:assistant', 'speaker': 'agent', 'session_time': '2024-10-01 08:00', 'turn_time': '2024-10-01 08:00'}
           prompt="The observation date and time for this message is '2024-10-01 08:00'. Resolve relative time expressions such as 'yesterday', 'today', and 'last week' only against this observation time, even if another current or observation date appears elsewhere in the extraction prompt."
-- provenance sidecar (memory_id -> source_turn_ids) -- {'m1': {'isolation_key': 'probe_run_first-high-simple-colon_and_order-s1t1', 'source_turn_ids': ['1:user']}, 'm2': {'isolation_key': 'probe_run_first-high-simple-colon_and_order-s1t1', 'source_turn_ids': ['1:assistant']}}
-- retrieve(RetrievalQuery) RetrievalResult --
   formatted_memory = (No relevant memories found)
   evidence = RetrievalEvidence(semantic_provenance=EvidenceAssertion(status='valid', reason_code=None, reason=None), provenance_granularity='turn', stable_ranking=EvidenceAssertion(status='pending', reason_code='ranking_fidelity_not_audited', reason='provider result order has not passed the method-specific ranking audit'))
   metadata.answer_prompt_profile = longmemeval
====================================================================================================
CONVERSATION first-high-simple-colon_and_order-s1t2
session_time = None
QA.question_time = '2024-10-01 21:00' Tuesday
-- canonical turns --
   {'turn_id': '1:user', ..., 'content': "I went to the gym. (place: Boston, MA; time: '2024-10-01 20:53' Tuesday)", 'turn_time': '2024-10-01 20:53', 'source_step_index': 0, ...}
   {'turn_id': '1:assistant', ..., 'content': "Noted gym visit. (place: Boston, MA; time: '2024-10-01 20:53' Tuesday)", 'turn_time': '2024-10-01 20:53', 'source_step_index': 0, ...}
   {'turn_id': '2:user', ..., 'content': "I had lunch earlier. (place: Boston, MA; time: '2024-10-01 18:32' Tuesday)", 'turn_time': '2024-10-01 18:32', 'source_step_index': 1, ...}
   {'turn_id': '2:assistant', ..., 'content': "Noted lunch. (place: Boston, MA; time: '2024-10-01 18:32' Tuesday)", 'turn_time': '2024-10-01 18:32', 'source_step_index': 1, ...}
-- private evidence_group_sets (evaluator-only, NOT sent to method) --
   {'unit_id': '0', 'child_ids': ('1:user', '1:assistant'), 'mapping_status': 'mapped'}
   {'unit_id': '1', 'child_ids': ('2:user', '2:assistant'), 'mapping_status': 'mapped'}
-- GranularityAggregator(consume_granularity='turn') emitted units --
  [unit 1] TurnEvent turn_id=1:user role=user
  [unit 2] TurnEvent turn_id=1:assistant role=assistant
  [unit 3] TurnEvent turn_id=2:user role=user
  [unit 4] TurnEvent turn_id=2:assistant role=assistant
-- Memory.add() calls captured: 4 --
  [add #1] ... turn_id='1:user'  time=20:53 (raw order position 0, later clock)
  [add #2] ... turn_id='1:assistant' time=20:53
  [add #3] ... turn_id='2:user'  time=18:32 (raw order position 1, earlier clock — NOT re-sorted)
  [add #4] ... turn_id='2:assistant' time=18:32
-- provenance sidecar -- {'m1': {..., 'source_turn_ids': ['1:user']}, 'm2': {..., 'source_turn_ids': ['1:assistant']}, 'm3': {..., 'source_turn_ids': ['2:user']}, 'm4': {..., 'source_turn_ids': ['2:assistant']}}
-- retrieve(RetrievalQuery) RetrievalResult --
   evidence = RetrievalEvidence(semantic_provenance=EvidenceAssertion(status='valid', ...), provenance_granularity='turn', stable_ranking=EvidenceAssertion(status='pending', ...))
   metadata.answer_prompt_profile = longmemeval
====================================================================================================
CONVERSATION third-low-simple-no_colon_pair-t1t1
session_time = None
QA.question_time = '2024-10-02 09:10' Wednesday
-- canonical turns --
   {'turn_id': '1', 'speaker': 'user', 'normalized_role': 'user', 'content': "My favorite cafe is Blue Bottle. (place: SF, CA; time'2024-10-02 09:00' Wednesday)", 'turn_time': '2024-10-02 09:00', 'source_step_index': 0, 'source_step_role': 'observation', 'source_timestamp_embedded_in_content': True}
   {'turn_id': '2', 'speaker': 'user', 'normalized_role': 'user', 'content': "I usually go there on Fridays. (place: SF, CA; time'2024-10-02 09:05' Wednesday)", 'turn_time': '2024-10-02 09:05', 'source_step_index': 1, 'source_step_role': 'observation', 'source_timestamp_embedded_in_content': True}
-- private evidence_group_sets --
   {'unit_id': '0', 'child_ids': ('1',), 'mapping_status': 'mapped'}
   {'unit_id': '1', 'child_ids': ('2',), 'mapping_status': 'mapped'}
-- GranularityAggregator(consume_granularity='turn') emitted units --
  [unit 1] TurnEvent turn_id=1 role=user
  [unit 2] TurnEvent turn_id=2 role=user
-- Memory.add() calls captured: 2 --
  [add #1] messages=[{'role': 'user', 'content': "user: My favorite cafe is Blue Bottle. (place: SF, CA; time'2024-10-02 09:00' Wednesday)"}]
  [add #2] messages=[{'role': 'user', 'content': "user: I usually go there on Fridays. (place: SF, CA; time'2024-10-02 09:05' Wednesday)"}]
   (无冒号原文字面值原样保留，未插入 [Turn time:] 前缀——marker=True 生效)
-- retrieve(RetrievalQuery) RetrievalResult --
   evidence = RetrievalEvidence(..., provenance_granularity='turn', ...)
   metadata.answer_prompt_profile = longmemeval
====================================================================================================
CONVERSATION first-high-comparative-noise_and_time-n1
session_time = None
QA.question_time = '2024-11-06 08:00' Wednesday
-- canonical turns --
   {'turn_id': '1:user', ..., 'content': "I bought a bike. (place: NYC, NY; time: '2024-11-01 09:00' Friday)", 'turn_time': '2024-11-01 09:00', 'source_step_index': 0, 'source_timestamp_embedded_in_content': True}
   {'turn_id': '1:assistant', ..., 'turn_time': '2024-11-01 09:00', 'source_step_index': 0, 'source_timestamp_embedded_in_content': True}
   {'turn_id': '2:user', ..., 'content': 'The weather was nice that day and I felt like taking a long walk around downtown discussing random things.', 'turn_time': None, 'source_step_index': 1, 'source_timestamp_embedded_in_content': False}
   {'turn_id': '2:assistant', ..., 'content': "That's a pleasant afternoon indeed, thanks for sharing.", 'turn_time': None, 'source_step_index': 1, 'source_timestamp_embedded_in_content': False}
   {'turn_id': '3:user', ..., 'content': "I sold the bike later. (place: NYC, NY; time: '2024-11-05 09:00' Tuesday)", 'turn_time': '2024-11-05 09:00', 'source_step_index': 2, 'source_timestamp_embedded_in_content': True}
   {'turn_id': '3:assistant', ..., 'turn_time': '2024-11-05 09:00', 'source_step_index': 2, 'source_timestamp_embedded_in_content': True}
-- private evidence_group_sets --
   {'unit_id': '0', 'child_ids': ('1:user', '1:assistant'), 'mapping_status': 'mapped'}
   {'unit_id': '2', 'child_ids': ('3:user', '3:assistant'), 'mapping_status': 'mapped'}
   （unit_id='1'/noise step 未出现在 target_step_id，故不入 gold group——设计符合预期）
-- Memory.add() calls captured: 6 --
  [add #1] turn_id='1:user'  metadata 含 session_time/turn_time='2024-11-01 09:00'  prompt="The observation date and time...'2024-11-01 09:00'..."
  [add #2] turn_id='1:assistant' 同上
  [add #3] turn_id='2:user'  messages=[{'role':'user','content':'user: The weather was nice that day and I felt like taking a long walk around downtown discussing random things.'}]
           metadata={'conversation_id': ..., 'session_id': 's1', 'turn_id': '2:user', 'speaker': 'user'}   # 无 session_time/turn_time 键
           prompt=None    # 无 observation time prompt —— noise 完全不获得合成时间
  [add #4] turn_id='2:assistant' 同上（无时间）
  [add #5] turn_id='3:user'  turn_time='2024-11-05 09:00'（未继承/未污染 noise 的 None，也未回填 step1）
  [add #6] turn_id='3:assistant' 同上
-- retrieve(RetrievalQuery) RetrievalResult --
   evidence = RetrievalEvidence(..., provenance_granularity='turn', ...)
   metadata.answer_prompt_profile = longmemeval
====================================================================================================
CONVERSATION third-high-comparative-noise_and_time-n2
session_time = None
QA.question_time = '2024-11-09 08:00' Saturday
-- canonical turns --
   {'turn_id': '1', ..., 'content': "I visited the museum. (place: Chicago, IL; time: '2024-11-02 10:00' Saturday)", 'turn_time': '2024-11-02 10:00', 'source_step_index': 0, 'source_timestamp_embedded_in_content': True}
   {'turn_id': '2', ..., 'content': 'It was a long day full of errands and small talks with friends about nothing memorable.', 'turn_time': None, 'source_step_index': 1, 'source_timestamp_embedded_in_content': False}
   {'turn_id': '3', ..., 'content': "I went back to the museum again. (place: Chicago, IL; time: '2024-11-08 10:00' Friday)", 'turn_time': '2024-11-08 10:00', 'source_step_index': 2, 'source_timestamp_embedded_in_content': True}
-- private evidence_group_sets --
   {'unit_id': '0', 'child_ids': ('1',), 'mapping_status': 'mapped'}
   {'unit_id': '2', 'child_ids': ('3',), 'mapping_status': 'mapped'}
-- Memory.add() calls captured: 3 --
  [add #1] turn_id='1' 有时间；[add #2] turn_id='2' messages=[{'role':'user','content':'user: It was a long day full of errands and small talks with friends about nothing memorable.'}] metadata 无 session_time/turn_time 键，prompt=None；[add #3] turn_id='3' 有时间，未继承 noise 的 None
-- retrieve(RetrievalQuery) RetrievalResult --
   evidence = RetrievalEvidence(..., provenance_granularity='turn', ...)
   metadata.answer_prompt_profile = longmemeval
```

> 注：为控制 note 篇幅，2/4/5 号 conversation 的部分重复字段（与场景 1 结构相同的
> `metadata`/`prompt` 逐字文本）在誊抄时做了同类项省略（`...`），但**所有承重断言
> （add 调用数、messages 内容、turn_time/session_time 键是否存在、prompt 是否为
> None、evidence 字段）均为脚本真实 stdout 逐字保留，无删减、无编造**；完整未省略
> 版本仍在会话 scratchpad（`mem0_membench_probe.out`，187 行）可核对。

### 4.4 场景 7（marker 严格 boolean）：既有回归层已覆盖，本轮不重复造轮子

- **MemBench 侧**：`membench.py::_build_step_turn()` 第 879 行
  `"source_timestamp_embedded_in_content": bool(turn_time)`——canonical adapter
  对该字段**恒定产出 Python `bool`**（`True`/`False` 二值），不可能产出缺键、`1`
  或字符串 `"true"`。§4.1-4.3 探针的 6 条 timed turn 全部 marker=`True`、4 条 noise
  turn 全部 marker=`False`，与源码保证一致。
- **Mem0 渲染器侧**：`mem0_adapter.py::_effective_time_prefix()`（1485-1501 行）对
  非 `True` 的 marker（缺键/`False`/字符串 `"true"`）一律不跳过前缀——该防御性分支
  已由 `tests/test_mem0_adapter.py::test_mem0_renderer_session_only_and_no_time_byte_stable`
  锁定（docstring 原文："marker 必须严格为 True 才跳过（字符串 "true" / 1 / 缺键都
  不触发 dedup）"）。这是 Mem0 renderer 对**任意上游 Turn**（不只 MemBench）的防御
  性契约，MemBench 现实数据只会触达 `True`/`False` 两个分支，本轮探针未重复构造该
  边界，直接引用既有测试作为 layer-2（deterministic contract test）证据。

## 5. 私有/时间/地点核对结论

- **无损**：§4.3 每条 canonical turn 的 `content` 原样进入 Mem0 message（`speaker:
  content` 拼接，speaker 前缀是既有 renderer 行为，不是本轮新发现）；FirstAgent 两
  child 的 `ps_user`/`ps_agent` 侧写 metadata 互不可见，Mem0 message 也未见对侧内容
  泄漏。
- **无重复**：`source_timestamp_embedded_in_content=True` 的 6 条 timed turn，Mem0
  message 中该时间字面值出现次数与原文一致（1 次），未见 `[Turn time:]` 重复前缀；
  §4.3 no-colon 场景确认无冒号原文格式同样触发 marker 跳过，不额外插入冒号版本。
- **无伪造**：4 条 noise turn（turn_time=None）在 `_native_turn_metadata()` 输出中
  完全不含 `session_time`/`turn_time` 键，`_observation_time_prompt()` 对应
  `prompt=None`——**没有从相邻 timed turn、QA.question_time 或 wall clock 回填**。
  MemBench 的 `session_time` 对全部 5 个 conversation 恒为 `None`（源码
  `membench.py:728-734` 显式设计），因此 Mem0 `[Session time: …]` fallback 分支
  对 MemBench 数据**结构性不可达**——这是 MemBench 与 LoCoMo/LongMemEval（有真实
  session_time）的一个关键差异，此前 mem0.md B4 描述的"turn→session→None" 三级
  fallback 对 MemBench 实际只有两级（turn→None）会生效。
- **QA.time 单向**：全部 5 条探针的 `retrieve(RetrievalQuery)` 调用与全部 add()
  调用的 metadata/messages 中均未出现 QA 侧的 question_time 文本；`question_time`
  只经由 `RetrievalQuery.question_time` 传给 `_retrieve_native()`，且该函数唯一用途
  是构造 `native_question`（供 legacy native prompt 通道，§6.3），不写回任何
  ingest 侧 payload。

## 6. Readout / metric / identity（卡 §5）

### 6.1 run_id 隔离与 formatted_memory

- `isolation_key = f"{run_id}_{conversation_id}"`（`default_isolation_key`），
  ingest 侧 `run_id=event.isolation_key`、retrieve 侧
  `filters={"run_id": query.isolation_key}`——两侧使用同一 key，命名空间一致；
  MemBench 每个 conversation = 1 trajectory = 1 question，不存在多 conversation
  共享 run_id 的风险。
- `formatted_memory` 在探针中恒为 `"(No relevant memories found)"`（fake backend
  `search()` 返回空列表，预期行为），字段本身非空、类型正确，满足 v3 协议
  "formatted_memory 必需非空"的要求。

### 6.2 choice/source/recall metric 与 identity

- `evaluators/membench_recall.py::_ALLOWED_GRANULARITIES = frozenset({"turn"})`
  与 `mem0_adapter.py::_build_retrieval_evidence()` 对 `benchmark_name in
  {"locomo", "membench"}` 声明的 `granularity="turn"`、`semantic.status="valid"`
  精确匹配——探针 §4.3 全部 5 条 `evidence` 输出与此一致，Mem0×MemBench 的
  recall/source-accuracy 应可判定 `valid` 而非 BEAM 式的 `n_a`。
- `stable_ranking` 恒为 `pending`（`_MEM0_UNAUDITED_STABLE_RANKING`），与
  `membench_recall.py` 的 `requires_stable_ranking=False` 一致，不阻塞 recall
  计分，但 rank-sensitive 指标（若未来引入）仍不可用。
- `choice-accuracy`/`source-accuracy` 两个 evaluator 消费的是
  `answer_prompts.prediction.jsonl`（unified builder 产出），与 Mem0 native
  reader_messages 无关（见 §6.3），本轮未见风险。
- manifest/resume：本轮未构造完整 registered-prediction 走查（该层已有
  `tests/test_membench_registered_prediction.py` 覆盖，未发现需要重跑的证据），
  `Mem0.consume_granularity`/`benchmark_name` 均作为构造参数显式传入且被
  `_build_retrieval_evidence()`/`ingest()` 直接读取，未见隐式默认值分支漏判
  MemBench 的风险。

### 6.3 非阻塞代码缺口：`_reader_prompt_kind()` 把 MemBench 误标成 "longmemeval"

**现象**（§4.3 全部 5 条探针均可复现）：`retrieve(RetrievalQuery)` 返回的
`RetrievalResult.metadata["answer_prompt_profile"]` 对 MemBench 问题恒为
`"longmemeval"`，而不是 `"membench"` 或表示"无官方 harness"的显式值。

**根因**（`mem0_adapter.py:1883-1907` `_reader_prompt_kind()`）：

```python
if self.benchmark_name in {"locomo", "longmemeval", "beam"}:
    return self.benchmark_name
...
if question.question_time:
    return "longmemeval"
return "generic"
```

`self.benchmark_name == "membench"` 不在第一个显式集合中，落入启发式 fallback；
MemBench 的 `conversation_metadata`/`category` 不含 `"longmemeval"`/`"locomo"`
关键词，但 **100% 的 MemBench 问题都有 `question_time`**（`docs/survey/异常情况/
membench.md` M-Q1：4,260/4,260）——因此该 fallback 对 MemBench **恒定**命中
`"longmemeval"` 分支，进而调用 `_build_mem0_longmemeval_prompt()`，真实加载
vendored `memory-benchmarks` 的 LongMemEval 官方 prompt 模块并构造一段
不会被使用的 native prompt。

**为什么当前不阻塞**：`benchmark_adapters/registry.py` 给 MemBench 注册
`prompt_track="unified"`，生产主路径调用的是
`build_membench_unified_answer_prompt(question, retrieval_result)`，只读取
`RetrievalResult.formatted_memory`；`retrieve_native()` 内部计算出的
`reader_messages`/`prompt_messages`/`answer_prompt_profile` 在这条主路径上
**不会被消费**（`prompt_messages` 会原样写入 artifact 作为 native 口径旁证，但
不驱动 unified 答案生成）。`configs/methods/mem0.toml` 也没有 `author_membench`
section 去选择"method 官方完整 answer builder"，所以不存在"暗中给 MemBench 主表
引入 LongMemEval 优势"的当前风险。

**为什么仍值得记录**：
1. artifact 里会持久化一个误导性的 `answer_prompt_profile: "longmemeval"`
   字段，任何日后审计 `answer_prompts.prediction.jsonl` 的人可能误以为 Mem0 对
   MemBench 采用了"LongMemEval 官方 parity"的答题构造。
2. 卡 §3 要求"Mem0 官方仓库没有 MemBench 专用 harness 时必须明确写'无'"——当前
   代码没有一个显式的 `"membench"`/`"none"` 返回值，而是静默借用另一个 benchmark
   的官方模块，这与"明确写无"的要求方向相反。
3. 若未来任何路径（`LegacyProviderBridge`、`native` answer_builder 迁移、
   `author_membench` section）开始消费这条 `reader_messages`/`prompt_messages`，
   会在没有新增代码的情况下静默生效，把 LongMemEval 官方 prompt 套到 MemBench
   问题上。

**建议**（非本卡授权范围，仅供联合裁决参考）：在 `_reader_prompt_kind()` 中为
`benchmark_name == "membench"` 增加显式分支返回 `"generic"`（或新增
`"membench_no_official_harness"` 之类的显式标签），使"无官方 harness"成为可读
声明而非启发式副作用。是否需要发共享实现卡由架构师联合裁决后决定。

## 7. B11 sentinel shape 建议（未经批准，不涉真实 API）

沿用 LightMem×MemBench 已验收的四层证据模型（`docs/survey/异常情况/membench.md`
§6）：census（本 note 引用既有 §2 全量数字，未重新扫描）、deterministic contract
test（既有 `tests/test_membench_conversation_adapter.py` + §4.4 既有 marker
测试）、registered production-path probe（本 note §4，新增）、真实 B11 smoke
（**未执行，待用户预算批准**）。

- **0-10k W1/W2 主烟**：复用现行 `MEMBENCH_SMOKE_POLICY`
  （`history_axis="rounds"`, `default_history_limit=1`,
  `default_isolation_limit=1`, `default_question_limit=1`），四源各取首条
  trajectory。天然覆盖：FirstAgent 单 dict step 展开（§4 场景1）、ThirdAgent
  string step（场景2）、两种时间尾注格式（各源分布见
  `docs/survey/异常情况/membench.md` M-T1，无冒号仅 ThirdLow）、question-time
  answer builder、真实 Mem0 backend 基本链路（add+search+manifest）。不覆盖
  100k noise、39 处倒序、OOB/空 gold——与 LightMem 现行 smoke 边界结论一致
  （membench.md §7 末段），Mem0 没有理由需要更宽的 0-10k 覆盖。
- **100k FirstHigh+ThirdHigh missing-time sentinel**：结构对齐本 note §4 场景
  4/5 的合成反例（timed→noise→timed 三步 pattern），但**具体 tid/step 定位需要
  真实数据**——本 worktree 未挂载 `data/membench/`（无软链），
  `docs/survey/异常情况/membench.md` 的 M-T2 表只给出 100k 各源的聚合计数
  （FirstHigh no-time=42,000/timed=3,133；ThirdHigh no-time=24,000/timed=1,049），
  未列出具体 tid/step 坐标（不同于 M-T3 倒序表已有具体位置）。**本节因此明确写
  "待真实数据挂载后由持有数据的 actor/架构师选定具体 tid/step，不在此假设或
  编造坐标"**。
  - 复用判断：LightMem 侧的 100k FirstHigh+ThirdHigh sentinel（README 断点提到
    "已用新 identity 补跑并验收"）验证的是 LightMem 的 pair-batch +
    zero-extraction 行为，**不能直接复用其结论到 Mem0**——Mem0 是逐 turn
    add（§3），noise turn 在 Mem0 侧的可观测形状是"该 turn 单独一次
    `Memory.add()` 调用、`prompt=None`、metadata 无时间键"（§4.3 已用合成数据
    证明），而不是 LightMem 的"zero-extraction"。若 Mem0 100k sentinel 要跑，
    需要新的真实 B11 run，不能挂靠 LightMem 已有 artifact。
  - 复用可行：0-10k 主烟的 registered-path 调用形状（isolation/manifest/
    granularity 声明）已被本 note §4 的合成探针在结构上验证过，无需在真实
    100k sentinel 之外再单独验证"registry 是否传对 granularity"这类结构问题。

## 8. 与既有稳定事实的一致性检查

本轮未发现任何卡内承重事实被 current-main 源码推翻：

- `docs/survey/异常情况/membench.md` 的 M-S1/M-T1/M-T2/M-T3/M-Q1 描述与
  `membench.py` 现行实现（§2 表）逐条对应，census 数字未复算（未改变、未失效）。
- `docs/reference/integration/mem0.md` B2（membench=turn）、B4（effective time
  单次渲染）、B5（membench=valid(turn)）均与本轮探针实测行为一致，无需改判。
- 唯一新增信息是 §3 的中心问题裁决（明确 current-main 是 turn 而非 pair，此前
  mem0.md B2 虽写了"MemBench=turn"，但未展示逐 child 调用序列的一手证据）与
  §6.3 的非阻塞代码缺口。

## 9. 定向自检

```text
$ uv run pytest -q tests/test_documentation_standards.py
```

（结果与 `git diff --check` 输出见完成报告；两者均只覆盖本 note 新增文件，未跑
全量回归、未跑 compileall、未调用真实 API。）
