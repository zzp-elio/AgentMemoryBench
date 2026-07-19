# Mem0 × LongMemEval current-main 差量预检

> actor: Claude Sonnet 5（本会话系统提示自报模型；未与用户核实身份，如实标注）。
> worktree: `/Users/wz/Desktop/mb-actor-mem0-longmemeval`，branch
> `actor/mem0-longmemeval-delta-preflight`（本次由 actor 从 main `6643e56` 新建，任务卡
> 假设的路径原不存在）。`data/` 通过只读软链接到主仓 `/Users/wz/Desktop/memoryBenchmark/data`
> 补齐（卡 §0 允许）。**只读审计，零真实 API，零生产代码改动。**

## 0. 判词

**`READY_FOR_JOINT_RULING`**（不等于付费 smoke 授权；不代表本卡已裁定 blank-turn 差异是
bug/improvement/variant——只给证据）。

## 1. 源身份复核

- `data/longmemeval/longmemeval_s_cleaned.json`：277,383,467 bytes；现场
  `shasum -a 256` = `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`，
  与 `docs/workstreams/ws02.6-first-smoke-hardening/notes/longmemeval-source-lock.json`
  完全一致。未漂移，直接复用稳定异常账（`docs/survey/异常情况/longmemeval.md`），不重新
  统计 blank/assistant-first/same-role/pure-session 计数。
- `_m_cleaned.json` 未现场重算 SHA-256（2.7GB，本卡范围只需 S 变体做 shape 探针，M 的身份
  由既有 source-lock 承重，未发现需要重开的信号）。

## 2. current-main 承重链结论（逐项落实卡 §4 八类映射）

### 2.1 注册粒度与聚合路径

- `methods/registry.py:202-211 _mem0_consume_granularity()`：`benchmark_name=="longmemeval"`
  → `"session"`（非 `"pair"`）。`tests/test_method_registry.py:168` 现场断言同一事实。
- 因此 LongMemEval × Mem0 **完全不经过** `runners/event_stream.py` 的
  `GranularityAggregator._aggregate_pairs()`（user 锚定配对、orphan/dangling 标记）。走的是
  `_aggregate_sessions()`（`event_stream.py:156-162`）：按 `session_id` 分组连续事件，产出
  **一个** `SessionBatch`，内含该 session **全部**（已跳过 blank 后）retained turn，原序不变，
  不做任何 role 相关判断。
- 真正的“两两切块”完全在 adapter 内部：`mem0_adapter.py:572-617 _ingest_native_session()`
  对 `batch.events` 转换出的 `turns` 执行纯位置切片
  `turns[start : start + 2] for start in range(0, len(turns), 2)`（`:595-597`），与 role 无关，
  与官方 `run.py:314-324 pair_turns()` 的 `for i in range(0, len(cleaned), 2): pair = cleaned[i:i+2]`
  同构（都是位置切块，不做 user 锚定）。**这与 core 卡若审 `Memory.add` 内部接受性无关，
  本卡只确认这层调用序列真实存在。**
- `_turn_batch_metadata()`（`:1524-1548`）为每个 chunk 记录 `turn_ids/first_turn_id/
  last_turn_id/speaker="+".join(...)/session_time/first_turn_time/last_turn_time`；无私有字段。

### 2.2 结构化 role 是否被按 speaker 首现改写

- `_turn_to_message()`（`:1444-1482`）：
  `role = normalized_role if normalized_role in VALID_MESSAGE_ROLES else speaker_roles.get(turn.speaker, "user")`。
  `normalized_role` 来自 LongMemEval canonical `Turn.normalized_role`，而该字段由 benchmark
  adapter `_normalized_role()`（`benchmark_adapters/longmemeval.py:643-656`）从原始 `role`
  字段直接映射，只要原始 `role in {user,assistant,system}` 就恒非空——LongMemEval 数据的
  `role` 字段结构化且从不缺失（稳定异常账 §3.3：`未知结构化 role：0`）。
  **结论：`speaker_roles` 的“按 speaker 首现交替 user/assistant”回退分支对 LongMemEval 是死
  代码，从不触发**；assistant-first、same-role、pure-user/pure-assistant、singleton 一律保留
  结构化 role，不被重写。用 real assistant-first fixture 现场验证：
  `tests/test_mem0_adapter.py:1057-1121 test_native_mem0_longmemeval_assistant_first_session_keeps_official_chunks`
  断言 `add_calls[0]["messages"][*]["role"] == ["assistant","user"]`，即首条 chunk 真实保留
  `assistant` 在前，未被强制改写成 `user`。
- pure-user/pure-assistant singleton session（长度 1）：`_ingest_native_session` 的
  `range(0, 1, 2)` 只产出一个 chunk `turns[0:1]`，长度 1，与官方 `pair_turns()` 对长度 1
  session 产出 `cleaned[0:2]`（实际只有 1 个元素）行为一致。

### 2.3 speaker 前缀：确认存在，且官方 harness 没有对应字节

- `_turn_to_message()` 最终 content 为
  `f"{prefix}{turn.speaker}: {' '.join(content_parts)}"`（`:1479-1482`）。对 LongMemEval，
  `turn.speaker` 来自 `_turn_from_raw()`：`speaker = role or ...`（无独立 named speaker 字段），
  即 `turn.speaker` 字面值就是 `"user"` 或 `"assistant"`。因此 message content 实际形如
  `"[Session time: ...] user: <正文>"`——在已经有独立 `role` 字段的前提下，content 里又重复
  写入一遍角色字面量。
- 对照官方 `run.py:314-324 pair_turns()`：`cleaned = [{"role": t["role"], "content": t["content"]}]`，
  content **不含**任何角色前缀或时间前缀，纯原文。
- 这是一处真实、可复现的 content-byte 差异（未在
  `docs/reference/integration/mem0.md` B4 现有条目中提及 speaker 前缀本身，B4 只讨论时间
  前缀口径）；`[Session time: …]` 前缀属于已裁决的 B4 additive 时间策略
  （`docs/reference/actor-handbook.md` §6 时间判例 + `mem0.md` B4），但 `{speaker}: ` 角色
  字面量前缀不在 B4 裁决范围内，**只给证据、不代裁**是否需要改动或已知可接受。

### 2.4 Blank turn：canonical 层跳过 vs 官方逐 pair 跳过——确认为真实行为差异

这是本卡命中的最主要发现，用真实 S 数据现场验证（探针见 §3）。

- **canonical 层行为**：`benchmark_adapters/longmemeval.py:397-399`，blank turn 在
  session→Turn 转换阶段被**逐条**丢弃（`skipped_blank_turn_count += 1; continue`），不进入
  canonical `Session.turns`。之后 `_ingest_native_session()` 只看到已经去除 blank 的
  turn 列表，再按位置两两重新切片。
- **官方 harness 行为**（`run.py:314-324` + `:438-443`）：`pair_turns()` 先对**原始**（含
  blank）session 做位置切片，得到成对的 `[cleaned[i], cleaned[i+1]]`；随后
  `ingest_question()` 逐 pair 检查
  `if any(not msg.get("content","").strip() for msg in messages): continue`——**只要 pair
  内任一条消息为空，整个 pair（包括其中非空的另一条）都不会调用 `mem0.add()`**。
- 二者的关键差异不是“谁丢了 blank 本身”，而是：**official 会连带丢弃与 blank 同一原始
  position-pair 的非空搭档消息；current-main 只丢 blank 本身，其余非空 turn 会重新与后续
  turn 组成新的（原本不相邻的）pair**。真实数据现场验证见 §3，两例都显示 official 会丢弃
  真实非空 assistant/user turn，而 current-main 会把这些 turn 送进 `Memory.add()`（有时单独
  成一个 singleton chunk，有时与原本不相邻的 turn 重新配对）。
- `docs/survey/异常情况/longmemeval.md`：S 变体 blank turn=12，M=295（已稳定，未重新统计）；
  本卡只新增“这些 blank 如何影响 Mem0 pairing”这一 method 差量事实，不重开 blank 计数本身。
- 卡内既有裁决模板要求“只给证据，不擅自代裁”：this is `LEGAL_EDGE` vs
  `SOURCE_HETEROGENEITY` 无关的 pure method-adapter 行为分叉，是否算 bug/fidelity
  improvement/variant，留给架构师联合裁决。

### 2.5 Session 内 duplicate occurrence 边界

- canonical 层 `_unique_session_id()`（`benchmark_adapters/longmemeval.py:454-467`）为重复
  原始 session id 的第 2+ 次出现追加稳定 `#occurrence_N` 后缀，产生的公开 `session_id`
  彼此不同。
- `build_turn_events()` 按 `conversation.sessions` 顺序逐 session 展开 `TurnEvent`，同一
  session 的 turn 总是连续产出（不会跨 session 交错）；`_group_by_session()` 只按“连续且
  session_id 相同”分组（`event_stream.py:210-228`）。因为一次 conversation 的事件流严格按
  session 顺序线性展开，两次 occurrence 即使原始 id 相同，其内部去重后的 `session_id`
  字符串不同，且彼此不相邻，天然落入不同的分组、不同的 `SessionBatch`，不会被误合并、
  也不会互相覆盖 provenance。命名空间（`isolation_key` = 该 question 的 conversation_id）
  相同，但 turn provenance 靠 `source_turn_ids`（公开 turn id，含 occurrence 后缀）区分，
  每个 retained turn 只在它自己的 `source_turn_ids` 里出现一次。
- 未见到需要 fixture 补的新反例；`docs/survey/异常情况/longmemeval.md` 的 894/1,182 次
  duplicate occurrence 计数（S/M，已稳定）继续适用，本卡未重新统计。

### 2.6 Session 排序：raw haystack 顺序 vs 官方 `sort_sessions_chronologically()`

- current-main **不对 haystack session 重新排序**：
  `_sessions_from_instance()`（`benchmark_adapters/longmemeval.py:309-339`）严格按
  `haystack_session_ids/haystack_dates/haystack_sessions` 原始并行顺序遍历，直接生成
  `Session` 列表顺序，`build_turn_events()` 也严格按 `conversation.sessions` 的这个顺序展开。
- 官方 `run.py:291-311 sort_sessions_chronologically()` 会在 ingest 前把
  `(session_id, date, session)` 按 `parse_longmemeval_date()`（完整 `YYYY/MM/DD HH:MM`）
  重新排序。
- 现场对 S 变体全量 500 instance 做探针（§3.3）：**按完整 date+time 排序，500 个 instance
  中有 211 个（42.2%）的原始 haystack 顺序不是完整时间戳单调不降**；但**按日期（丢弃
  HH:MM）排序，500 个全部单调不降（0 个日期级乱序）**。也就是说重新排序只会在同一
  calendar day 内部重新调整 session 相对顺序，不会跨天移动。
- 与 `docs/survey/datasets/longmemeval.md` §2.1 已有裁决交叉：OWNER issue #8 明确
  “question annotation 只确定 date、未确定可靠的具体时间”，`docs/survey/异常情况/longmemeval.md`
  §3.1 现行裁决是“不用相邻 session、首个有时 turn 或人工时间覆盖 raw JSON”。这条既有裁决的
  精神支持“不信任 HH:MM 做排序键”，而官方 `pair_turns` 前置的 chronological sort 恰恰依赖
  HH:MM 排序。**这是一处可复现的、真实存在的 ingestion 顺序差异**（仅限同日内 session
  互换位置，不跨天），是否需要对齐官方排序、或现行“不信任 HH:MM”的政策已经隐式否决了对齐
  官方排序的必要性，留给架构师裁决，本卡不代裁。

### 2.7 隔离与检索（§5 要求）

- `retrieve(RetrievalQuery)` → `_retrieve_native()`（`:979-1076`）：`Memory.search(...,
  filters={"run_id": query.isolation_key}, top_k=...)`；`isolation_key` 对 LongMemEval
  = `default_isolation_key(run_id, conversation_id)` = `f"{run_id}_{question_id}"`
  （`event_stream.py:23-26`；`conversation_id=question_id` 见
  `benchmark_adapters/longmemeval.py:260`）。因此每题（=每个 instance）天然独立
  namespace，backend/run_id 不跨题泄漏。
- 没有 question-time cutoff：`_retrieve_native` 的 `Memory.search()` 调用只传 `filters`
  和 `top_k`，不传时间参数；`question_time` 只被塞进 `native_question` 供
  `_reader_messages()`/answer builder 使用，不参与 `search()` 调用。与
  `docs/survey/workflows/longmemeval.md` §2 现行契约（"retrieve 明确 filters=None"，此处
  实际是 `filters={"run_id":...}`，语义等价于官方"整段 haystack 可见、无时间过滤"）一致。
- unified 完整 answer builder：`_retrieve_native` 返回 `RetrievalResult(formatted_memory=...,
  prompt_messages=..., evidence=...)`，供框架统一 answer builder 消费；legacy
  `_reader_messages()`/`get_answer()`/`_build_mem0_longmemeval_prompt()` 是 Mem0 自己的
  native readout 路径（`author_longmemeval` 校准用），本轮预检未运行、未触碰。
- `RetrievalEvidence`：`_build_retrieval_evidence()`（`:1078-1118`）对
  `benchmark_name in {"longmemeval","halumem"}` 声明
  `EvidenceAssertion(status="valid")` + `provenance_granularity="session"`，`stable_ranking`
  统一 pending。**这与 §2.1 的注册粒度诚实一致**：既然实际投递单元是 session 级批次
  （批内两条消息共享同一批 provenance），就不冒充 turn 级 exact lineage；`Recall`
  仅能安全声明到 session 粒度，`rank` 继续 pending，符合
  `docs/reference/integration/mem0.md` B5 现行结论（"LongMemEval 只能安全声明
  valid(session)，不得冒充 turn"）。
- 私有字段可达性：`_native_turn_metadata()`（`:678-696`）、`_turn_batch_metadata()`
  （`:1524-1548`）只写 `conversation_id/session_id/turn_id(s)/speaker/session_time/turn_time`；
  benchmark adapter 的 `_public_message_metadata()`（`longmemeval.py:659-675`）已经在更早一层
  过滤掉 `PRIVATE_MESSAGE_KEYS`（含 `answer/answer_session_ids/has_answer` 等）。逐层核对
  未发现私有字段可达 method 的路径。

## 3. 真实数据现场探针（stdout 原文）

以下探针均基于真实 `data/longmemeval/longmemeval_s_cleaned.json`（经软链只读访问），零真实
API、零 method 状态改动。构造与执行方式：`uv run python -` 内联脚本，逐条粘贴于此，供跨模型
复核（不依赖任何会话私有 scratchpad）。

### 3.1 Session 日期级 vs 完整时间戳级排序探针

命令：

```
uv run python - <<'EOF'
import ijson, re
from datetime import datetime

def parse(d):
    try:
        c = re.sub(r"\s*\([A-Za-z]+\)\s*", " ", d).strip()
        return datetime.strptime(c, "%Y/%m/%d %H:%M")
    except Exception:
        return None

path = "data/longmemeval/longmemeval_s_cleaned.json"
count = 0
unsorted_instances = 0
total = 0
with open(path, "rb") as f:
    for inst in ijson.items(f, "item"):
        total += 1
        dates = inst["haystack_dates"]
        parsed = [parse(d) for d in dates]
        seq = [p for p in parsed if p is not None]
        is_sorted = all(seq[i] <= seq[i+1] for i in range(len(seq)-1))
        if not is_sorted:
            unsorted_instances += 1
print("total", total, "unsorted_instances", unsorted_instances)
EOF
```

stdout：

```
total 500 unsorted_instances 211
```

日期粒度复测（丢弃 HH:MM，仅比较 date）：

```
total 500 date_level_unsorted 0
```

**结论**：全量 500/500 instance 的 haystack session 原始顺序按日期单调不降；211/500
（42.2%）按完整 `date+time` 排序会与原始顺序不同——即官方 `sort_sessions_chronologically()`
只会在同一天内部重排 session 相对顺序，不跨天移动。

### 3.2 Blank turn 与非空搭档 collateral drop 探针

命令：

```
uv run python - <<'EOF'
import ijson

def is_blank(t):
    c = t.get("content")
    txt = t.get("text")
    val = c if c is not None else txt
    return val is None or (isinstance(val, str) and val.strip() == "")

path = "data/longmemeval/longmemeval_s_cleaned.json"
found = 0
with open(path, "rb") as f:
    for inst in ijson.items(f, "item"):
        for sidx, sess in enumerate(inst["haystack_sessions"]):
            blanks = [i for i,t in enumerate(sess) if is_blank(t)]
            if blanks and len(sess) > 2:
                print(inst["question_id"], "session", sidx, "len", len(sess), "blank_idx", blanks)
                for i,t in enumerate(sess):
                    print("  ", i, t.get("role"), repr((t.get("content") or t.get("text"))[:30] if not is_blank(t) else "<BLANK>"))
                found += 1
                break
        if found >= 2:
            break
EOF
```

stdout：

```
dd2973ad session 12 len 10 blank_idx [8]
   0 user 'tradingview'
   1 assistant 'TradingView is a popular onlin'
   2 user 'how to connect tradingview to '
   3 assistant 'To connect TradingView to your'
   4 user 'can you make an example'
   5 assistant "Sure, here's an example of how"
   6 user 'can i add a transaction from t'
   7 assistant 'Yes, it is possible to add a t'
   8 user '<BLANK>'
   9 assistant 'Did you have a question or nee'
gpt4_7fce9456 session 40 len 10 blank_idx [3, 4, 7, 8]
   0 user '「ゴージャスで宝石の装飾のあるウェディングドレス風のダンス用'
   1 assistant 'A young girl danced gracefully'
   2 user '「AIが考える一番エレガントな女子\n高校制服\n」の超高精細の'
   3 user '<BLANK>'
   4 user '<BLANK>'
   5 assistant 'The most elegant high school g'
   6 user '「AIが考える一番かわいい女子高生\n\n」の超高精細の長文英語'
   7 user '<BLANK>'
   8 user '<BLANK>'
   9 assistant 'As envisioned by AI, the cutes'
```

**逐例人工推演（未运行真实 `Memory.add`，纯位置/正文逻辑推演，可复算校验）**：

- `dd2973ad` session 12（10 raw turns，blank 在原始 index 8）：
  - 官方 `pair_turns` 对原始 10 条切 5 对：`[0,1],[2,3],[4,5],[6,7],[8,9]`；pair `[8,9]`
    因 index 8 为空被整体跳过 → **官方从不对 index 9（真实 assistant 回复）调用
    `mem0.add()`**。
  - current-main：canonical 层先丢弃 index 8，retained 9 条（原 index 9 变成 retained 第 9
    个，0 基 index 8）；adapter 再对 9 条 retained 位置切块：`[0,1],[2,3],[4,5],[6,7],[8]`——
    最后一块是单条 chunk，内容就是原 index 9 的真实 assistant 消息。**current-main 会把
    官方永不发送的这条真实内容单独发给 `Memory.add()`。**
- `gpt4_7fce9456` session 40（10 raw turns，blank 在原始 index 3,4,7,8）：
  - 官方切 5 对：`[0,1],[2,3],[4,5],[6,7],[8,9]`；因 3/4/7/8 均为空，pair `[2,3]`、`[6,7]`、
    `[8,9]` 全部整体跳过 → **官方只会对 pair `[0,1]` 和 `[4,5]` 调用 `mem0.add()`**，原始
    index 2/6/9（均为非空真实内容）被连带永久丢弃。
  - current-main：canonical 层丢弃 4 条 blank，retained 6 条（原始 index 0,1,2,5,6,9）；
    adapter 位置切块：`[0,1],[2,5],[6,9]`（这里的下标是 retained 序，对应原始
    index 0-1、2-5、6-9）。**三对全部送入 `Memory.add()`**，且第二对把原本不相邻的原始
    index 2（真实 user 内容）与原始 index 5（真实 assistant 内容）重新配成一对——这是原始
    session 里从未相邻出现过的组合。

**确认的行为差异（只陈述事实，不代裁分类）**：
1. 官方对"pair 内任一消息为空"采取**整对跳过**（含连带丢弃非空搭档），current-main 采取
   **逐条跳过 blank 本身 + 对幸存 turn 重新位置配对**。
2. 该差异会造成：(a) 官方从不发送、current-main 会发送的真实内容（如上两例的 index 9 与
   index 2/6/9）；(b) 官方不会形成、current-main 会形成的“原本不相邻 turn 被拉到同一
   pair”的新组合（如 `gpt4_7fce9456` 的 index2+index5）。
3. `docs/survey/异常情况/longmemeval.md` 记录 S 变体 blank turn 总数=12（含本卡两例共 5 个
   blank turn instance 内的 5 处），未逐个统计有多少 blank 与真实搭档相邻、因而受本条影响；
   本卡只证明差异**存在且可复现**，不重新普查全量受影响的 blank 计数（该计数已有稳定值，
   变的是"如何解释这些 blank 对 pairing 的下游影响"这一 method 差量事实，不是 blank 本身
   的计数）。

## 4. 官方 harness 对照小结（`run.py`）

| 维度 | current-main Mem0×LongMemEval | 官方 `run.py` | 差异性质 |
|---|---|---|---|
| 位置两两切块 | `_ingest_native_session()` 对 retained turns 做 `range(0,len,2)` | `pair_turns()` 对原始 turns 做同构切片 | 机制相同，**输入不同**（见下两行） |
| blank 处理 | canonical 层逐条跳过，adapter 对幸存 turn 重新配对 | 逐 pair 检查，任一空则整对跳过（含非空搭档） | **确认差异**，见 §2.4/§3.2 |
| session 排序 | 保留 raw haystack 顺序（日期级单调，HH:MM 级 42.2% 不同） | 显式按完整 date+time 重排 | **确认差异**，仅限同日内重排，见 §2.6 |
| role 来源 | 结构化 `role` 直接映射为 message role，speaker-alternation 回退为死代码 | 直接使用原始 `role` 字段 | 一致 |
| content 正文 | 前置 `[Session time: …]`/`[Turn time: …]`（唯一 fallback）+ `{speaker}: ` 前缀 | 纯原始 `content`，无任何前缀 | **确认差异**，时间前缀属已裁决 B4 additive 策略，speaker 前缀未见现行裁决覆盖，见 §2.3 |
| 隔离键 | `run_id=isolation_key`（`{run_id}_{question_id}`）过滤 `Memory.search` | `user_id=f"longmemeval_{question_id}_{run_id}"` 命名空间 | 隔离粒度一致（逐题独立），字段语义留给 core 契约卡裁 |
| retrieval 时间截断 | 无 | 无（官方也不做 as-of 截断） | 一致 |
| RetrievalEvidence | `granularity="session"`，诚实不冒充 turn | 无对应概念（官方无 provenance 声明） | current-main 侧诚实披露，无反证 |

## 5. Metric 资格与 smoke 候选（§5 要求）

- 未获取 core 卡是否已回卡的信息（本卡与其并行，六卡互不读对方 note）；本卡不依赖 core
  卡结论即可完成上述 benchmark 差量映射，`CORE_CONTRACT_DEPENDENCY_PENDING` 仅适用于"Mem0
  内部是否接受该 shape"这一问题本身，不影响本卡对"框架实际投递了什么"的陈述。
- B11 最小候选（**只按公开 shape 挑选，不看 gold/answer，不把 pair 数换算成 API 次数**）：
  - 普通 S question：`question_id=dd2973ad` 所属 instance（含上面探针命中的普通 session，
    也含其余正常 user→assistant session，可整体作为"含真实数据病态形状"的代表）。
  - 公开异形 S question：`question_id=gpt4_7fce9456` 所属 instance（session 40 含 4 个 blank
    turn，是本卡验证 blank/pairing 差异的直接来源，形状本身足够异形，不依赖 answer/gold 挑选）。
  - 两者均只依据 haystack 公开结构选出，未读取 `answer`/`answer_session_ids`/`has_answer`。
- 未见新的 metric 资格缺口：Recall/rank 仍受 §2.7 的 `session` granularity 限制，与既有
  `retrieval-metric-eligibility-ruling.md` 一致，未发现需要重开的证据。

## 6. 测试盲点（§6 要求，只陈述缺口不补测试）

- `tests/test_mem0_adapter.py::_build_longmemeval_conversation()`（`:419-472`）与
  `test_native_mem0_longmemeval_matches_bridge_session_sequence`（`:1012-1054`）的 fixture
  只有干净的 4+1 turn session，**不含 blank turn、不含 duplicate session occurrence、
  不含同 role 相邻（user→user / assistant→assistant）显式命名测试**。
- `test_native_mem0_longmemeval_assistant_first_session_keeps_official_chunks`
  （`:1057-1121`）覆盖了 assistant-first 与奇数长度（最后 singleton chunk），但同样不含
  blank turn 场景。
- 全仓 `tests/` 对 "`_ingest_native_session()` 在 blank 与非 blank 交错时的行为" 没有专门
  单测——即 §2.4/§3.2 描述的差异目前只有本卡的真实数据人工推演为证据，没有可复跑的自动化
  回归锁定当前行为（无论最终裁决是否需要修复，现状都缺一个显式测试固定"当前实际发生什么"）。
- `configs/methods/mem0.toml` 未见 `author_longmemeval` section（符合现行政策：无一手作者
  校准参数前不新增稀疏 section），不是本卡范围内的缺口。

## 7. 唯一判词

**`READY_FOR_JOINT_RULING`**。

汇总本卡新增的三处确认差异供联合裁决：
1. blank turn 处理口径（canonical 逐条丢弃 + adapter 重新配对 vs 官方整对丢弃）——
   §2.4/§3.2/§4。
2. session 排序（保留 raw 顺序 vs 官方显式 chronological re-sort，仅限同日内影响）——
   §2.6/§3.1/§4。
3. `_turn_to_message()` 的 `{speaker}: ` 前缀是否需要与官方 content-only 字节对齐——
   §2.3/§4。

其余映射（role 保真、隔离、检索时间、RetrievalEvidence 诚实声明、duplicate occurrence
边界、私有字段不可达）均已现场核实与官方/现行裁决一致，未发现新缺口。
