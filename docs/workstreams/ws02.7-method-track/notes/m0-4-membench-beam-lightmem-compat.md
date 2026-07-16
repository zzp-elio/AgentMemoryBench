# M0-4 MemBench / BEAM x LightMem 离线兼容核查

> **⚠️ 2026-07-16 局部 superseded：**本文把 assistant content 被重包成 user role 视为
> 非 blocker 的裁决已经撤销；LightMem extraction 按 `role` 过滤，且 MemBench FirstAgent
> 更上游把 user/agent 合成了一个伪 user turn。历史取证保留，不得继续把 §6 的旧判词当现行
> 准入。现行证据与裁决见
> [role 一手审计](../branches/input-role-semantics/notes/lightmem-messages-membench-beam-role-audit.md)。

> 日期：2026-07-13。范围仅含 MemBench 0-10k 四源与 BEAM 100k/10m 两种
> frozen-v1 结构；全程未初始化真实 LightMemory backend、未调用 LLM/embedding API。
> 数据来自主树只读路径 `/Users/wz/Desktop/memoryBenchmark/data/`；Arrow 是二进制，
> 无可引用文本行号，因此数据结论同时给出文件路径、可复算脚本与实际输出。代码行为
> 均给出本 worktree 内现场核实的 `文件:行号`。

## 1. MemBench 四源文件 x ingest 路径

### 1.1 真实输入形态

MemBench adapter 把一个 trajectory 映射为一个 conversation、一个 `s1` session，
并从首个有时间的 turn 回填 `session_time`
（`src/memory_benchmark/benchmark_adapters/membench.py:624-653`）。四源的差异发生在
单个 `message_list` step：

| 真实源文件（0-10k） | 原始 step | 独立 role / speaker / timestamp 字段 | canonical turn |
|---|---|---|---|
| `FirstAgentDataHighLevel_multiple_0.json` | `dict{"user", "agent"}` | 无；时间戳嵌在 user/agent 文本尾部 | `content="'user': ...; 'agent': ..."`，`speaker=normalized_role="user"`，原文另存 `ps_user/ps_agent`（`membench.py:711-716,728-734`） |
| `FirstAgentDataLowLevel_multiple_0.json` | `dict{"user", "agent"}` | 同上 | 同上（`membench.py:711-716,728-734`） |
| `ThirdAgentDataHighLevel_multiple_0.json` | 第三人称 `str` | 无；时间戳嵌在字符串尾部 | 字符串原样作为 content，`speaker=normalized_role="user"`（`membench.py:717-719,728-734`） |
| `ThirdAgentDataLowLevel_multiple_0.json` | 第三人称 `str` | 同上 | 同上（`membench.py:717-719,728-734`） |

adapter 的时间正则同时接受 `time: '...'` 与真实 LowLevel 第三人称数据里的
`time'...'`，提取结果进入 `Turn.turn_time`（`membench.py:676-695,711-719`）。
真实四源首条样本分别为：First/High 13 steps、First/Low 164 steps、Third/High
11 steps、Third/Low 20 steps；First 样本键恒为 `user/agent`，Third 样本为字符串。
样本命令与输出见 §5.1。

四源 0-10k 全量扫描得到 3,400 trajectories、144,507 turns，全部 turn 均能从
真实文本提取时间戳；step 类型也恒定为 First=dict、Third=str。以 `cl100k_base`
作离线风险近似，四源最大单 turn 分别为 183/173/159/310 tokens，均低于 LightMem
sensory buffer 的 512-token 档（buffer 的真实 tokenizer 由 segmenter 提供，故此处
只作边界风险近似，不冒充官方精确 token 数；
`third_party/methods/LightMem/src/lightmem/factory/memory_buffer/sensory_memory.py:4-24`）。
可复算扫描与原始输出见 §5.2。

### 1.2 进入 LightMem 的实际 messages

registry 对除 LongMemEval 外的 LightMem grid 统一实例化为 turn 粒度，因此 MemBench
走 `consume_granularity="turn"`（`src/memory_benchmark/methods/registry.py:369-385`）。
事件流保留 canonical role/speaker/content，并以 `turn_time or session_time` 发出
timestamp（`src/memory_benchmark/runners/event_stream.py:29-58`）。每个 TurnEvent
再被 LightMem 包成固定两条 message：

```text
{role: user, content: 原 turn 全文, speaker_id/name: turn.speaker,
 time_stamp: turn.turn_time 或 session.session_time}
{role: assistant, content: "", speaker_id/name: 同上, time_stamp: 同上}
```

该结构由 `_native_turn_batch -> _conversation_to_locomo_batches` 生成
（`src/memory_benchmark/methods/lightmem_adapter.py:589-596,1126-1156`）。
MemBench 没有 speaker_a/b，speaker id 回退到 canonical `turn.speaker`，所以四源都
是 `user`，不是 `unknown`（`lightmem_adapter.py:1449-1458`）。官方
`MessageNormalizer` 要求每条 message 有 `time_stamp`，接受 ISO 或
`YYYY/MM/DD (weekday) HH:MM`
（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:28-57,79-100`）；真实
`2024-10-01 08:00` 可由 `datetime.fromisoformat` 解析。每次 `add_memory` 新建
500ms offset 的 normalizer，故一批内 user 为原时间，空 assistant 为 `+0.5s`
（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:264-276`）。

**硬结论：MemBench 四源均不会因输入结构、缺时间、speaker 缺省或单 turn 尺寸在
LightMem ingest 的离线前置层报错；不会丢 turn 文本。存在明确但非 unknown 的语义
压平：First 的 user/agent 成为同一条带文本标签的 user message，Third 本来就是
第三人称字符串；两者 speaker 均为 user，另附一个空 assistant。这个压平始于
MemBench canonical 契约并被 LightMem LoCoMo 包装延续，不是本次运行时偶发。**

## 2. BEAM 100k / 10m x ingest 路径

### 2.1 canonical 结构与真实规模

100k `chat` 是 `list[session]`，adapter 逐项建 `sN`
（`src/memory_benchmark/benchmark_adapters/beam.py:441-461`）。10m `chat` 是 10 个
plan-dict，严格按
`chat[i]["plan-{i+1}"]` 展开 batch，并把每个 batch 内的 turn groups 打平为
`pN:sM`（`src/memory_benchmark/benchmark_adapters/beam.py:464-509`）。真实 turn 是
dict，字段含 `role/content/id/index/question_type/time_anchor`；adapter 保留
role/content，裁掉末尾 `->-> a,b`，把
非空 time_anchor 作为 turn_time，并以 session 第一个非空 anchor 回填 session_time
（`beam.py:590-643`）。

真实全量扫描结果（脚本见 §5.3）：

| variant | conversations | plans | sessions | turns | session turns | conversation turns | 空 content（裁尾后） |
|---|---:|---:|---:|---:|---:|---:|---:|
| 100k | 20 | N/A | 90 | 5,732 | 46-132 | 188-392 | 0 |
| 10m | 10 | 100 | 1,000 | 208,696 | 130-470 | 18,760-23,716 | 0 |

两者 role 都基本严格 user/assistant 对称：100k 为 2,866/2,866；10m 为
104,349/104,347。10m 少 2 个 assistant 不影响 turn 粒度聚合，因为该粒度不要求
成对（turn 聚合逐 event 发出；`src/memory_benchmark/runners/event_stream.py:91-108`）。

### 2.2 LightMem role 与消息数行为

BEAM 也走 registry 的 turn 粒度（`src/memory_benchmark/methods/registry.py:382-384`），
所以每个原 turn 独立变成 `[user(content), assistant("")]`
（`src/memory_benchmark/methods/lightmem_adapter.py:589-596,1126-1156`）。原始
assistant 的 **message role 会变成 user**，但 speaker_name/id
仍是 `assistant`；官方 extraction 配置是 `messages_use="user_only"`
（`lightmem_adapter.py:417-422`），其实际 prompt 拼装会保留 user-role message，
并以 `speaker_name: content` 写入，故原始 user/assistant 文本和 speaker 标签都进入
抽取 prompt，空 assistant 被过滤
（`third_party/methods/LightMem/src/lightmem/factory/memory_manager/openai.py:281-313`）。
因此这里有 role 载体转换，但没有静默
丢掉 assistant 内容或把 speaker 变为 unknown。

adapter 同时只保留一个 pending batch：新 turn 到来时写出上一批，conversation 结束
再 force flush 最后一批（`lightmem_adapter.py:532-587`）。所以 10m 超长 conversation
不会形成 20k-message 的单次 `add_memory` 参数；每次恒为 2 messages，没有固定消息数
上限问题。但一条 10m conversation 会产生 18,760-23,716 次 `add_memory`，是成本与
耗时风险，不是 list-size 崩溃。

### 2.3 确定性时间阻断

真实 100k 共 5,732 turns，仅 90 个 turn 自带非空 time_anchor；每个 session 恰有
至少一个，因此 adapter 能给 session 其余 turn 回填。真实 10m 共 208,696 turns，
207,697 个 turn 无自身 time_anchor；其中 conversation `7` 的 `p1:s1`（244 turns）
整个 session 无 anchor。其余 session 可回填。数据路径与扫描见 §5.3。

但非空 BEAM anchor 是 `March-15-2024` / `July-01-2024` 一类 `%B-%d-%Y`。LightMem
adapter 只特化 LoCoMo 时间，否则把原值直接交官方 normalizer；完全无时间则先抛
`ConfigurationError`（`src/memory_benchmark/methods/lightmem_adapter.py:1410-1426`）。
官方 normalizer 的正则不接受该月名格式，ISO fallback 也失败
（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:28-57`）。§5.4 的真实
首行转换已现场得到两次 `ValueError`，因此
这不是推测：100k 与 10m 的认证 smoke 都会在第一批 `add_memory` 前置标准化阶段失败。

### 2.4 超长单 turn 与 buffer 边界

真实最大 raw content：100k 为 348,853 chars（conversation `4`/`s2`/turn 28），
10m 为 329,788 chars（conversation `5`/`p2:s9`/turn 114）；两者都是 assistant
turn，进入 LightMem 后会作为 user-role content 处理。100k 有 2,562 个 turn 的
`cl100k_base` 近似长度 >=512；10m 有 100,817 个 turn 长度 >=2,048 chars（10m 为
控制全量扫描成本采用字符阈值，不与 token 等同；§5.3）。

`pre_compress=true`，adapter 配置用 LLMLingua-2、rate 0.7
（`configs/methods/lightmem.toml:20-24`；`methods/lightmem_adapter.py:400-420`）。
官方 compressor 对每条非空 message 压缩，并在有 tokenizer 时循环压到 `<512`
tokens；压缩异常会保留当前内容并退出二次循环
（`third_party/methods/LightMem/src/lightmem/factory/pre_compressor/llmlingua_2.py:39-89`）。
之后 sensory buffer 遇到
`当前空 buffer + 单条 user > max_tokens` 时会先切空 buffer，却不把 oversized
message 从 big_buffer 移除，存在无进展循环风险
（`third_party/methods/LightMem/src/lightmem/factory/memory_buffer/sensory_memory.py:15-38,43-57`）。

**硬结论：BEAM 100k 与 10m 当前都会先被时间格式确定性阻断；10m formal 还会在
conversation 7/p1:s1 遇到完全无时间的第二种阻断。空 turn 与一次性消息数不是边界；
超长单 turn 依赖本地 LLMLingua 成功压到 512 以下，否则官方 sensory buffer 有潜在
无进展风险。本卡按要求只核代码路径与数量级，未运行本地压缩模型或任何 API。**

## 3. 时间戳覆盖与 B4 记法

| benchmark | 真实数据 | adapter / LightMem 后的时间 | B4 记法 |
|---|---|---|
| MemBench | 四源 144,507/144,507 turns 的文本都含可提取 `YYYY-MM-DD HH:MM`（§5.2） | adapter 结构化到 turn_time；官方 normalizer 转 ISO，并给同批空 assistant 加 500ms（`membench.py:686-719`；`lightmem.py:86-100,275-276`） | **有** |
| BEAM | time_anchor 稀疏：100k 90/5,732、10m 999/208,696 非空；另有 10m 一个 session 全空（§5.3） | adapter 把 session 首 anchor 扇出给多数无 anchor turn；当前 `%B-%d-%Y` 又无法被官方解析，所以尚无可产出的 memory（`beam.py:612-619`；`lightmem_adapter.py:1418-1426`） | **伪时间戳**（并附注 1 个 session 为“无”；当前实现先报错） |

若时间输入修复并成功形成 payload，reader formatter 会把 ISO timestamp 输出为
`[Memory recorded on: DD Month YYYY, weekday]\nmemory`；无法解析 ISO 时退化为原
timestamp/weekday 前缀（`lightmem_adapter.py:1532-1569`）。§5.4 的合成 payload
实测为 `'[Memory recorded on: 01 October 2024, Tue]\nsample fact'`。BEAM 当前在
ingest 阶段失败，因此不能声称它已经产生这种 formatted_memory。

## 4. retrieve / formatted_memory 与 question 形态

### 4.1 MemBench

真实 QA 含一个公开 question、A-D choices 和 question time；adapter 将 choices 放入
`Question.options`（`benchmark_adapters/membench.py:748-775`）。unified answer builder
只把 `retrieval_result.formatted_memory` 原样代入 `memory` 槽，choice A-D 独立代入
官方 prompt（`membench.py:388-430`）。答题后的 choice normalize 只解析 answer
文本为 A-D 或 `invalid_choice`，不检查也不改 formatted_memory
（`membench.py:433-488`）。

**硬结论：MemBench choice normalize 与 LightMem formatted_memory 无格式冲突；
memory 可以是任意非结构化字符串。**

### 4.2 BEAM

BEAM probing question 转成公开自由文本 `Question.text`，category 单独保存，choices
不存在（`benchmark_adapters/beam.py:372-423`）。unified builder 仅把
formatted_memory 与 question 文本替换进 `<context>/<question>` 槽
（`beam.py:301-320`），没有 prediction transform。LightMem 检索侧通过官方
`text_embedder.embed + embedding_retriever.search(return_full=True)` 取 payload，
再按 `_format_lightmem_memory` 用换行拼接
（`src/memory_benchmark/methods/lightmem_adapter.py:699-721,1019-1077,1532-1559`）；
v3 出口空结果才用固定 sentinel
（`src/memory_benchmark/methods/lightmem_adapter.py:755-782`）。

**硬结论：BEAM 自由文本 question 与 LightMem formatted_memory 无格式冲突；当前
问题发生在 retrieve 之前的 ingest 时间契约，不在 question/prompt 拼装。**

## 5. 零成本离线验证

### 5.1 真实数据首条抽样

执行命令（主树 data 只读）：

```bash
uv run python - <<'PY'
import json
from pathlib import Path
root = Path('/Users/wz/Desktop/memoryBenchmark/data/membench/Membenchdata/data2test/0-10k')
for path in sorted(root.glob('*.json')):
    data = json.loads(path.read_text())
    row = next(rows[0] for scenarios in data.values() for rows in scenarios.values() if rows)
    print(path.name, type(row['message_list'][0]).__name__, len(row['message_list']),
          repr(row['message_list'][0])[:220], repr(row['QA'])[:220])
PY
```

实际摘要输出：

```text
FirstAgentDataHighLevel_multiple_0.json dict 13 {'user': "I really love The Godfather... time: '2024-10-01 08:00' Tuesday)", 'agent': "I'm glad..."} QA choices/ground_truth/time
FirstAgentDataLowLevel_multiple_0.json dict 164 {'user': "I want to tell you about my uncle... time: '2024-10-01 08:00' Tuesday)", 'agent': "That's great!..."} QA choices/ground_truth/time
ThirdAgentDataHighLevel_multiple_0.json str 11 "I really love Casablanca... time: '2024-10-01 08:00' Tuesday)" QA choices/ground_truth/time
ThirdAgentDataLowLevel_multiple_0.json str 20 "My subordinate is Maya Carter... time'2024-10-01 08:00' Tuesday)" QA choices/ground_truth/time
```

BEAM Arrow 现场以 `pyarrow.ipc.RecordBatchStreamReader` 读取。100k 首 row 的 chat
为 `list[list[turn dict]]`，首 turn 为 user、`time_anchor='March-15-2024'`；10m
首 row 的 chat 为 10 个 `{plan-N: [...]}` dict，首 turn 为 user、
`time_anchor='July-01-2024'`。对应 adapter 一手映射见
`src/memory_benchmark/benchmark_adapters/beam.py:328-347,441-509,590-643`。

### 5.2 MemBench 全量形态扫描

核心复算脚本（完整遍历四个 0-10k JSON）：

```python
import json, re
from pathlib import Path
from collections import Counter
import tiktoken

enc = tiktoken.get_encoding("cl100k_base")
time_re = re.compile(r"time:?\s*'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})'")
root = Path("/Users/wz/Desktop/memoryBenchmark/data/membench/Membenchdata/data2test/0-10k")
for path in sorted(root.glob("*.json")):
    data = json.loads(path.read_text())
    rows = [row for scenarios in data.values() for group in scenarios.values() for row in group]
    stats, types, maximum = Counter(), Counter(), 0
    for row in rows:
        stats["trajectories"] += 1
        for step in row["message_list"]:
            stats["turns"] += 1
            types[type(step).__name__] += 1
            parts = [step["user"], step["agent"]] if isinstance(step, dict) else [step]
            content = f"'user': {parts[0]}; 'agent': {parts[1]}" if isinstance(step, dict) else step
            if not any(time_re.search(part) for part in parts): stats["missing_timestamp"] += 1
            maximum = max(maximum, len(enc.encode(content)))
    print(path.name, dict(stats), dict(types), "max_tokens", maximum)
```

实际输出：

```text
FirstAgentDataHighLevel_multiple_0.json trajectories=700 turns=15450 dict=15450 missing_timestamp=0 max_tokens=183
FirstAgentDataLowLevel_multiple_0.json trajectories=900 turns=104470 dict=104470 missing_timestamp=0 max_tokens=173
ThirdAgentDataHighLevel_multiple_0.json trajectories=400 turns=5302 str=5302 missing_timestamp=0 max_tokens=159
ThirdAgentDataLowLevel_multiple_0.json trajectories=1400 turns=19285 str=19285 missing_timestamp=0 max_tokens=310
```

### 5.3 BEAM 全量形态扫描

扫描对目录内全部 Arrow shard 逐 record batch / row 读取；10m 展开表达式与 adapter
同构：`for i, slot in enumerate(row['chat'])`，读取
`slot[f'plan-{i+1}']`，再打平每个 batch 的 `turns` groups（adapter 锚：
`beam.py:464-509`）。每 turn 统计 role、content 长度、time_anchor；每 session 统计
是否至少有一个 anchor。可复算脚本核心（`arrow_dirs` 分别传 100K/10M 目录）：

```python
from collections import Counter
from pathlib import Path
import pyarrow as pa
import pyarrow.ipc as ipc

def rows(arrow_dir):
    for path in sorted(Path(arrow_dir).glob("*.arrow")):
        reader = ipc.RecordBatchStreamReader(pa.memory_map(str(path), "r"))
        for batch in reader:
            for index in range(batch.num_rows):
                yield batch.slice(index, 1).to_pylist()[0]

def sessions(row, ten_million):
    if not ten_million:
        return [(f"s{i + 1}", turns) for i, turns in enumerate(row["chat"])]
    return [
        (f"p{plan_index + 1}:s{batch_index + 1}",
         [turn for group in batch["turns"] for turn in group])
        for plan_index, slot in enumerate(row["chat"])
        for batch_index, batch in enumerate(slot[f"plan-{plan_index + 1}"])
    ]

for variant, arrow_dir, ten_million in (
    ("100k", "/Users/wz/Desktop/memoryBenchmark/data/BEAM/beam_dataset/100K", False),
    ("10m", "/Users/wz/Desktop/memoryBenchmark/data/BEAM/beam_10M_dataset/10M", True),
):
    stats, roles, conversation_sizes, missing_sessions = Counter(), Counter(), [], []
    maximum = (0, None)
    for row in rows(arrow_dir):
        stats["conversations"] += 1
        stats["plans"] += len(row["chat"]) if ten_million else 0
        conversation_turns = 0
        for session_id, turns in sessions(row, ten_million):
            stats["sessions"] += 1
            conversation_turns += len(turns)
            if not any(turn.get("time_anchor") for turn in turns):
                missing_sessions.append((row["conversation_id"], session_id, len(turns)))
            for turn_index, turn in enumerate(turns, 1):
                stats["turns"] += 1
                roles[turn.get("role")] += 1
                if not turn.get("time_anchor"): stats["missing_turn_timestamp"] += 1
                content = turn.get("content") or ""
                if not content.strip(): stats["empty_raw"] += 1
                if ten_million and len(content) >= 2048: stats["ge2048_chars"] += 1
                maximum = max(maximum, (len(content),
                    (row["conversation_id"], session_id, turn_index)))
        conversation_sizes.append(conversation_turns)
    print(variant, stats, roles, conversation_sizes, missing_sessions, maximum)
```

100k 的 `cl100k_ge512` 另以 `tiktoken.get_encoding("cl100k_base").encode(content)`
逐 turn 复算；它只用于风险分层，不替代 LightMem 的真实 tokenizer。实际输出：

```text
100k: conversations=20 sessions=90 turns=5732 roles={user:2866, assistant:2866}
      missing_turn_timestamp=5642 sessions_without_timestamp=0
      session_len=46..132 conversation_turns=188..392 empty_after_strip=0
      cl100k_ge512=2562 max_content=348853 chars @ conv=4/s2/turn=28
10m: conversations=10 plans=100 sessions=1000 turns=208696
     roles={user:104349, assistant:104347}
     missing_turn_timestamp=207697 sessions_without_timestamp=1
     missing_session=[('7','p1:s1',244)] session_len=130..470
     conversation_turns=[19895,19057,20192,19202,18760,19958,22652,22560,22704,23716]
     empty_raw=0 content_ge2048_chars=100817
     max_content=329788 chars @ conv=5/p2:s9/turn=114
```

数据文件：`data/BEAM/beam_dataset/100K/data-00000-of-00001.arrow` 与
`data/BEAM/beam_10M_dataset/10M/data-00000-of-00002.arrow`、
`data-00001-of-00002.arrow`（主树只读）。

### 5.4 adapter -> event -> aggregator -> LightMem 前置层实测

最终最小验证脚本使用真实 adapter/真实 data、`build_turn_events`、
`GranularityAggregator('turn')`、LightMem 的真实 batch helper 和官方
`MessageNormalizer`；`object.__new__(LightMem)` 仅用于调用不依赖实例状态的转换
helper，未构造 backend、未触发模型或 API：

```python
from pathlib import Path
import pyarrow as pa
import pyarrow.ipc as ipc
from lightmem.memory.lightmem import MessageNormalizer
from memory_benchmark.benchmark_adapters.beam import _conversation_from_row
from memory_benchmark.benchmark_adapters.membench import MemBenchAdapter
from memory_benchmark.methods.lightmem_adapter import LightMem, _format_lightmem_memory
from memory_benchmark.runners.event_stream import GranularityAggregator, build_turn_events

MAIN = Path("/Users/wz/Desktop/memoryBenchmark")
probe = object.__new__(LightMem)
for path in sorted((MAIN / "data/membench/Membenchdata/data2test/0-10k").glob("*.json")):
    conv = MemBenchAdapter(MAIN, variant="0_10k",
        source_relative_paths=(path.relative_to(MAIN),)).load(limit=1).conversations[0]
    events = tuple(build_turn_events(conv, "offline"))
    signals = tuple(GranularityAggregator("turn").aggregate(events[:2], isolation_key="offline"))
    batch = LightMem._native_turn_batch(probe, events[0])
    normalized = MessageNormalizer(offset_ms=500).normalize_messages(batch)
    raw_shape = "dict[user,agent]" if "ps_user" in conv.sessions[0].turns[0].metadata else "str"
    print(f"MEMBENCH {path.name}: raw={raw_shape}; events={len(events)}; "
          f"signals2={len(signals)}; roles={[m['role'] for m in batch]}; "
          f"speakers={[m['speaker_id'] for m in batch]}; "
          f"raw_ts={batch[0]['time_stamp']}; "
          f"normalized_ts={[m['time_stamp'] for m in normalized]}")

for variant, arrow_path, ten in (
    ("100k", MAIN/"data/BEAM/beam_dataset/100K/data-00000-of-00001.arrow", False),
    ("10m", MAIN/"data/BEAM/beam_10M_dataset/10M/data-00000-of-00002.arrow", True),
):
    source = pa.memory_map(str(arrow_path), "r")
    row = ipc.RecordBatchStreamReader(source).read_next_batch().slice(0, 1).to_pylist()[0]
    conv = _conversation_from_row(row, row_idx=0, ten_million=ten)
    events = tuple(build_turn_events(conv, "offline"))
    signals = tuple(GranularityAggregator("turn").aggregate(events[:2], isolation_key="offline"))
    batches = [LightMem._native_turn_batch(probe, event) for event in events[:2]]
    try:
        MessageNormalizer(offset_ms=500).normalize_messages(batches[0])
        result = "ok"
    except Exception as exc:
        result = f"{type(exc).__name__}: {exc}"
    print(f"BEAM {variant}: sessions={len(conv.sessions)}; turns={len(events)}; "
          f"first_session_turns={len(conv.sessions[0].turns)}; signals2={len(signals)}; "
          f"source_roles={[event.role for event in events[:2]]}; "
          f"produced_roles={[[m['role'] for m in batch] for batch in batches]}; "
          f"produced_speakers={[[m['speaker_id'] for m in batch] for batch in batches]}; "
          f"raw_ts={batches[0][0]['time_stamp']}; normalizer={result}")

print("FORMAT", repr(_format_lightmem_memory({"payload": {
    "time_stamp": "2024-10-01T08:00:00.000", "weekday": "Tue", "memory": "sample fact"}})))
```

实际输出（尾部错误文本原样）：

```text
MEMBENCH FirstAgentDataHighLevel_multiple_0.json: raw=dict[user,agent]; events=13; signals2=4; roles=['user', 'assistant']; speakers=['user', 'user']; raw_ts=2024-10-01 08:00; normalized_ts=['2024-10-01T08:00:00.000', '2024-10-01T08:00:00.500']
MEMBENCH FirstAgentDataLowLevel_multiple_0.json: raw=dict[user,agent]; events=164; signals2=4; roles=['user', 'assistant']; speakers=['user', 'user']; raw_ts=2024-10-01 08:00; normalized_ts=['2024-10-01T08:00:00.000', '2024-10-01T08:00:00.500']
MEMBENCH ThirdAgentDataHighLevel_multiple_0.json: raw=str; events=11; signals2=4; roles=['user', 'assistant']; speakers=['user', 'user']; raw_ts=2024-10-01 08:00; normalized_ts=['2024-10-01T08:00:00.000', '2024-10-01T08:00:00.500']
MEMBENCH ThirdAgentDataLowLevel_multiple_0.json: raw=str; events=20; signals2=4; roles=['user', 'assistant']; speakers=['user', 'user']; raw_ts=2024-10-01 08:00; normalized_ts=['2024-10-01T08:00:00.000', '2024-10-01T08:00:00.500']
BEAM 100k: sessions=3; turns=188; first_session_turns=60; signals2=4; source_roles=['user', 'assistant']; produced_roles=[['user', 'assistant'], ['user', 'assistant']]; produced_speakers=[['user', 'user'], ['assistant', 'assistant']]; raw_ts=March-15-2024; normalizer=ValueError: Invalid isoformat string: 'March-15-2024': Failed to parse session time format: 'March-15-2024'. Expected something like '2023/05/20 (Sat) 00:44'
BEAM 10m: sessions=100; turns=19895; first_session_turns=150; signals2=4; source_roles=['user', 'assistant']; produced_roles=[['user', 'assistant'], ['user', 'assistant']]; produced_speakers=[['user', 'user'], ['assistant', 'assistant']]; raw_ts=July-01-2024; normalizer=ValueError: Invalid isoformat string: 'July-01-2024': Failed to parse session time format: 'July-01-2024'. Expected something like '2023/05/20 (Sat) 00:44'
FORMAT '[Memory recorded on: 01 October 2024, Tue]\nsample fact'
```

## 6. Blocker 清单与准入结论

| 级别 | 现象 | 根因锚 | 修复建议（不施工） |
|---|---|---|---|
| blocker | BEAM 100k/10m 首批均在官方 `MessageNormalizer` 抛 `ValueError` | BEAM `%B-%d-%Y`；adapter 原样透传（`beam.py:612-619`；`lightmem_adapter.py:1418-1426`），官方只收 regex/ISO（`lightmem.py:28-57`） | 在 LightMem adapter 的时间适配层显式、可测地把 BEAM 月名日期转 ISO；保留原值供审计。不得改 frozen benchmark adapter。 |
| blocker（formal） | 10m conversation 7 / `p1:s1` 244 turns 完全无时间，先在 `_turn_timestamp` 报错 | 真实全量扫描 §5.3；无时间即抛（`lightmem_adapter.py:1418-1422`） | 由架构师裁定缺时政策；不能自行发明日期。至少应在付费调用前做离线 fail-fast 预检。 |
| risk | 100k/10m 有 30 万字符级单 turn；若压缩失败后仍 >=512，sensory buffer 可能无进展 | compressor 异常保留内容（`pre_compressor/llmlingua_2.py:55-89`）；空 buffer oversized 分支（`sensory_memory.py:15-38`） | 时间 blocker 修复后，先做无 API 的本地 compressor/buffer 边界测试；必要修复须保持 LightMem 算法核心不变并由架构师裁决。 |
| scale risk | 10m 每 conversation 18,760-23,716 次 `add_memory` | turn 粒度注册（`registry.py:382-384`）+ 单 pending batch（`lightmem_adapter.py:532-587`） | 真实 smoke 只跑 frozen 的 10m 极小切片；full 成本单独估算，不以一次性消息数问题误诊。 |

role 载体变化不列 blocker：原 assistant 内容虽以 user-role message 进入，但
speaker_name 仍为 assistant，且 extraction prompt 实际输出 speaker_name 与完整 content
（`memory_manager/openai.py:281-313`）。MemBench 也没有 `unknown` speaker。

**最终准入：MemBench 四源可以进入真实 smoke；BEAM 100k/10m 目前不可以进入真实
smoke，必须先由架构师裁定并施工时间格式与完全缺时 session 两个 blocker。**

## 施工报告

- worktree 创建命令：
  `git worktree add ../mb-actor-m04 -b actor/m0-4-membench-beam-compat`
- worktree / branch：`/Users/wz/Desktop/mb-actor-m04` /
  `actor/m0-4-membench-beam-compat`；创建输出基点为 `5e1480c`。
- 环境命令：`uv sync`；实际结果为 `Resolved 154 packages`、`Installed 130 packages`，
  项目 editable build 成功。
- 本卡 commit：`docs: audit LightMem MemBench and BEAM compatibility`（hash 以本分支
  `git log -1` 为准）；未 push。
- 改动范围：仅新建本文件；未改 `src/`、`tests/`、`third_party/`，未复制主树
  gitignored data，未调用真实 API。
- frozen-v1 交叉核对：MemBench 的 First=dict / Third=str 与
  `docs/reference/integration/membench.md:29-32` 一致；BEAM 100k 标准结构、10m
  plan-dict 展开及双 run smoke 与
  `docs/reference/integration/beam.md:13-16,25-27,31-34` 一致，未触发“档案过期”
  停工条件。
- 计划偏差：无。取证发现 BEAM blocker，按卡片要求只记录与建议，不施工。
