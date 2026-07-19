# Mem0 × LoCoMo current-main 差量预检

- 执行 actor：Claude Sonnet 5（Claude Code，本会话系统提示确认为 `claude-sonnet-5`）。
- worktree：`/Users/wz/Desktop/mb-actor-mem0-locomo`，分支
  `actor/mem0-locomo-delta-preflight`，基线 `6643e56`（`docs(mem0): issue parallel
  recertification audits`）。`data/` 为软链到主工作区的只读复用，未联网下载、未读
  `.env`。
- 范围：只审 Mem0 × LoCoMo 的 current-main 差量；不调用真实 API、不改生产代码、不
  重新普查整个 LoCoMo dataset（复用 `docs/survey/异常情况/locomo.md` 与
  `docs/survey/{datasets,workflows}/locomo.md` 的稳定账）。`Memory.add()` 是否要求
  role 交替由并行 core 卡裁决，本 note 只记录实际调用序列。

## 0. 唯一总判词

```text
BLOCKED(caption-raw-concat-no-wrapper)
```

Mem0 生产 adapter 对 LoCoMo caption 的处理是**裸拼**（raw concatenation），不是共享
`image_text.turn_text_with_images()` 的 `[Sharing image that shows: {caption}]`
wrapper；caption 文本被无标记地拼进 speaker 发言之后，与该 speaker 说出的话在字节层面
不可区分。这正是 `docs/survey/异常情况/locomo.md` §6 "Mem0 已知裸拼债" 与本卡 §5 明确
写下的一票否决条件："若当前 adapter 仍裸拼 caption 或漏 caption，必须判 BLOCKED，不得
用'文字大致相同'放行"。role/speaker/session-time/单 turn add/isolation 五项均通过
（见 §5-§6），唯一阻塞点是 caption wrapper。

## 1. 两代官方 harness 对表（§4）

| 维度 | legacy 论文 harness（`evaluation/src/memzero/{add,search}.py`） | current-main harness（`memory-benchmarks/benchmarks/locomo/run.py` + `common/mem0_client.py`） | 本项目生产 adapter（`mem0_adapter.py`） |
| --- | --- | --- | --- |
| 入口/用途 | 论文复现脚本，`from mem0 import MemoryClient` | 当前官方 eval harness，`Mem0Client`（`benchmarks/common/mem0_client.py`） | `src/memory_benchmark/methods/mem0_adapter.py::Mem0` |
| 调用面 | Mem0 **cloud/platform** `MemoryClient.add(..., version="v2", enable_graph=...)` | **REST** 调 self-hosted OSS server（`POST /memories`、`POST /search`，`docker compose up`）或 cloud V3；不是本地 core 调用 | **本地 core**：`mem0_module.Memory.from_config(...)`（`third_party/methods/mem0-main/mem0/memory/main.py::Memory.add/search`，进程内直接调用，非 REST） |
| namespace 数量 | **两个**：`speaker_a_user_id = f"{speaker_a}_{idx}"`、`speaker_b_user_id = f"{speaker_b}_{idx}"` | **一个**：`user_id = f"locomo_{conv_idx}_{run_id}"` | **一个**：`run_id=isolation_key`（= `conversation_id`，LoCoMo 场景） |
| 每个 namespace 收到的 role 视角 | **双视角复制**：speaker_a 的 namespace 收到 `messages`（a=user/b=assistant），speaker_b 的 namespace 收到 `messages_reverse`（a=assistant/b=user，同一份对话整段重复写两次，角色对调） | 单一视角：`role = "user" if speaker == speaker_a else "assistant"`（**按 speaker_a/b 显式身份**固定映射，不看说话顺序） | 单一视角：`speaker_roles[turn.speaker]` 按**该 conversation 内该 speaker 首次出现顺序**分配 user/assistant（第一个出现的 speaker=user，第二个=assistant），与官方"speaker_a 恒 user"不是同一算法，但 LoCoMo 数据里两者结果通常一致（需 speaker_a 恰好先说话） |
| speaker 前缀 | `f"{speaker_a}: {text}"` / `f"{speaker_b}: {text}"` | `f"{speaker}: {text}"` | `f"{prefix}{turn.speaker}: {content}"`（同款 `speaker: text` 前缀，位置一致） |
| chunk size | `batch_size=2`（默认，`add_memories_for_speaker` 每次 2 条一批） | `CHUNK_SIZE = 1`（逐 turn） | `ingestion_chunk_size=1`（`Mem0Config.__post_init__` 强校验必须为 1，与 current-main 一致） |
| timestamp | `metadata={"timestamp": timestamp}`，`timestamp` 是原始 `session_<n>_date_time` **字符串原文**，不解析 | `timestamp=session_epoch`（`locomo_date_to_epoch()` 解析出的 **Unix epoch int**），走 REST payload `timestamp` 字段（`_add_oss`/`_add_cloud`） | 本地 core `Memory.add()` **没有 `timestamp` 参数**（已核实签名：`user_id/agent_id/run_id/metadata/infer/memory_type/prompt`）；adapter 改用 `[Session time: ...]`/`[Turn time: ...]` 文本前缀 + `prompt=` 扩展点传 observation date（`_effective_time_prefix`/`_observation_time_prompt`），是唯二可行注入点，已被 mem0.md B4 记录为已知设计选择 |
| image wrapper | **无**任何 caption/img_url 处理，脚本只读 `chat["text"]` | `session_to_chunks()` 三分支：query+blip→`[Sharing image - query: {q}. The image shows: {blip}]`；query-only→`[Sharing image - query for: {q}]`；blip-only→`[Sharing image that shows: {blip}]`（**blip-only 分支与本项目共享 `image_text.turn_text_with_images()` 的 `[Sharing image that shows: ...]` 格式逐字节一致**） | **裸拼**：`content_parts=[text]+[caption,...]`，`" ".join(content_parts)`——**不带任何 wrapper/标记**，也不使用 `query`（`_turn_to_message`，见 §5 实测） |
| search 合并方式 | 两次独立 `search_memory()` 结果分别注入 answer prompt（`speaker_1_memories`/`speaker_2_memories` 并列） | 单次 `mem0.search(query, user_id, top_k)`，`format_search_results()` 按 `score` 降序排序后单列表 | 单次 `Memory.search(query, filters={"run_id": isolation_key}, top_k=20)`，`_normalize_search_results` 后单列表注入 `formatted_memory` |

**结论**：legacy 双 namespace 是论文复现专属行为（对话整段复制两次、角色对调），不是"官方现行做法"；current-main 与生产 adapter 都是**单 namespace**，这与 AGENTS.md 的"一个 `run_id` + physical worker isolation"更接近，legacy 只能作 future `author_locomo` 候选，未混入 unified 主轨（TOML 当前也确实没有 `author_locomo` section）。current-main 使用 REST 调用 self-hosted server，生产 adapter 使用本地 core 直接调用；两者是不同部署面，但共享同一套 `Memory` 算法源（vendored `mem0/` 包），调用参数语义（messages/user_id/timestamp）已逐项对表如上。

## 2. Production 映射与强反例（§5，零 API）

**方法**：直接调用生产代码的纯函数/静态方法（`LoCoMoAdapter.load()` → 真实
`build_turn_events()` → `Mem0._turn_from_event()` / `Mem0._turn_to_message()` /
`Mem0._native_turn_metadata()` / `Mem0._session_time_from_event()` /
`Mem0._observation_time_prompt()`），不构造真实 backend、不触网、不需要 OpenAI
settings（这几个方法本身是 `@staticmethod`，`_add_with_provenance` 才需要
`self._memory`，未被调用）。probe 脚本本身未提交仓库；以下按 actor-handbook 要求把
构造与 stdout 逐字写入本 note。

探针脚本核心逻辑：

```python
def dump(label, event, speaker_roles):
    turn = Mem0._turn_from_event(event)
    if turn.speaker not in speaker_roles:
        speaker_roles[turn.speaker] = (
            "user" if len(speaker_roles) % 2 == 0 else "assistant"
        )
    session_time = Mem0._session_time_from_event(event)
    message = Mem0._turn_to_message(turn, speaker_roles, session_time=session_time)
    metadata = Mem0._native_turn_metadata(event)
    prompt = Mem0._observation_time_prompt(session_time)
    # -> 这四个值恰好就是 _ingest_native_turn() 传给
    #    self._add_with_provenance([message], source_turn_ids=(event.turn_id,),
    #    run_id=event.isolation_key, metadata=metadata, infer=..., prompt=prompt)
    #    的 messages[0]/metadata/prompt，run_id=event.isolation_key
```

真实数据来源：`LoCoMoAdapter("/Users/wz/Desktop/mb-actor-mem0-locomo").load(limit=1)`
→ `conv-26`（Caroline/Melanie），`build_turn_events(conversation, "conv-26")` 产出的
真实 `TurnEvent` 序列（未裁剪，非 smoke）。

### 2.1 逐例结果（真实数据集案例 1/3/4/5/6/8）

**case1a 单 turn add + speaker A（D1:1, Caroline）**

```text
raw turn → D1:1 {"speaker":"Caroline","dia_id":"D1:1","text":"Hey Mel! Good to see you! How have you been?"}
→ canonical Turn(content="Hey Mel! Good to see you! How have you been?", images=[])
→ TurnEvent(turn_id="D1:1", session_id="session_1", timestamp="1:56 pm on 8 May, 2023")
→ Memory.add(
    messages=[{"role": "user", "content": "[Session time: 1:56 pm on 8 May, 2023] Caroline: Hey Mel! Good to see you! How have you been?"}],
    run_id="conv-26",
    metadata={"conversation_id": "conv-26", "session_id": "session_1", "turn_id": "D1:1", "speaker": "Caroline", "session_time": "1:56 pm on 8 May, 2023"},
    prompt="The observation date and time for this message is '1:56 pm on 8 May, 2023'. Resolve relative time expressions such as 'yesterday', 'today', and 'last week' only against this observation time, even if another current or observation date appears elsewhere in the extraction prompt.")
```

speaker_roles 累计：`{'Caroline': 'user'}`（Caroline 首次出现，取 user）。

**case1b 单 turn add + speaker B（D1:2, Melanie，与 case1a 相邻）**

```text
raw turn → D1:2 {"speaker":"Melanie","dia_id":"D1:2","text":"Hey Caroline! Good to see you! I'm swamped with the kids & work. What's up with you? Anything new?"}
→ Memory.add(
    messages=[{"role": "assistant", "content": "[Session time: 1:56 pm on 8 May, 2023] Melanie: Hey Caroline! Good to see you! I'm swamped with the kids & work. What's up with you? Anything new?"}],
    run_id="conv-26",
    metadata={"conversation_id": "conv-26", "session_id": "session_1", "turn_id": "D1:2", "speaker": "Melanie", "session_time": "1:56 pm on 8 May, 2023"},
    prompt=... 同上 session time)
```

speaker_roles 累计：`{'Caroline': 'user', 'Melanie': 'assistant'}`。每个真实 utterance
恰一次 `Memory.add()` 调用（单 turn add，`consume_granularity="turn"`，
`_mem0_consume_granularity("locomo")` 落入默认分支返回 `"turn"`，与 manifest 一致）；
role 是稳定 speaker→user/assistant 映射，content 含 named speaker 前缀
`{speaker}: `，Melanie 的发言正确进入 `assistant` role（未被误当"无事实的 agent
回复"丢弃或改写）。

**case8 URL + query + caption 同时存在（D1:5, Caroline）——BLOCKED 关键证据**

```text
raw turn → D1:5 {"speaker":"Caroline","img_url":["https://i.redd.it/l7hozpetnhlb1.jpg"],
  "blip_caption":"a photo of a dog walking past a wall with a painting of a woman",
  "query":"transgender pride flag mural","dia_id":"D1:5",
  "text":"The transgender stories were so inspiring! I was so happy and thankful for all the support."}
→ canonical Turn(content="The transgender stories were so inspiring! I was so happy and thankful for all the support.",
    images=[ImageRef(caption="a photo of a dog walking past a wall with a painting of a woman",
                      metadata={"url": "https://i.redd.it/l7hozpetnhlb1.jpg", "source_field": "img_url", "query": "transgender pride flag mural"})])
→ Memory.add(
    messages=[{"role": "user", "content":
      "[Session time: 1:56 pm on 8 May, 2023] Caroline: The transgender stories were so inspiring! I was so happy and thankful for all the support. a photo of a dog walking past a wall with a painting of a woman"}],
    run_id="conv-26",
    metadata={"conversation_id": "conv-26", "session_id": "session_1", "turn_id": "D1:5", "speaker": "Caroline", "session_time": "1:56 pm on 8 May, 2023"},
    prompt=...)
```

**裁决**：`img_url`、`query` 均未泄漏进 message content（符合隐私/无 locator 泄漏要求，
`_turn_to_message` 只读 `turn.content` 与 `image.caption`，不读 `image.metadata`）——这一点
是干净的。但 caption `"a photo of a dog walking past a wall with a painting of a
woman"` 被**原样追加**在 Caroline 原话之后，用单个空格连接，**没有 `[Sharing image
that shows: ...]` 或任何等价标记**。最终 message 读起来像是 Caroline 自己连续说了
"...for all the support. a photo of a dog walking past a wall with a painting of a
woman"——把一句图片描述伪装成了该 speaker 的下一句话。这与 current-main harness 的
blip-only 分支（`[Sharing image that shows: {blip}]`，见 §1 表）和本项目共享
`image_text.turn_text_with_images()` 的格式都不一致。

**case6 text + caption，无 URL（D4:4, Melanie）**

```text
raw turn → D4:4 {"speaker":"Melanie","blip_caption":"a photo of a stack of bowls with different designs on them",
  "dia_id":"D4:4","text":"That's gorgeous, Caroline! It's awesome what items can mean so much to us, right? Got any other objects that you treasure, like that necklace?"}
→ Memory.add(messages=[{"role": "assistant", "content":
    "[Session time: 10:37 am on 27 June, 2023] Melanie: That's gorgeous, Caroline! It's awesome what items can mean so much to us, right? Got any other objects that you treasure, like that necklace? a photo of a stack of bowls with different designs on them"}], ...)
```

同样裸拼，caption 紧跟在 Melanie 原话问句之后，读起来像是这句问话之后又冒出一句陈述句，
边界不清。**真实数据集扫描确认**（10 个 conversation 全量，非抽样）：LoCoMo 中不存在
"caption 存在但正文为空"的真实 turn（`caption_no_text` 命中 0 条），也不存在"同一 turn
2+ 个 `img_url`"（`multi_img` 命中 0 条），也不存在 `blip_caption` 字段存在但为空白
字符串的 turn；因此 caption-only（案例 7）、多 caption（案例 9）、blank-caption-field
（案例 10 的字段存在但为空白的子情形）三类在真实 canonical 数据里**不出现**，下方用
synthetic Turn/TurnEvent 单独验证代码路径本身的行为，不代表这是真实 LoCoMo 的问题
频次。

**case3 奇数 session 尾 turn（D2:17，session_2 共 17 turn，最后一条，Melanie）**

```text
→ Memory.add(messages=[{"role": "assistant", "content":
    "[Session time: 1:14 pm on 25 May, 2023] Melanie: No doubts, Caroline. You have such a caring heart - they'll get all the love and stability they need! Excited for this new chapter!"}],
    run_id="conv-26", metadata={..., "session_id": "session_2", "turn_id": "D2:17", ...})
```

按 turn 粒度单独 add，未被丢弃、未与相邻 turn 强行配对（因为 LoCoMo×Mem0 走
`consume_granularity="turn"`，不是 `pair`，不存在 BEAM 那种 dangling-tail 问题）。

**case4 跨 session 边界（D1:18 session_1 尾 Melanie → D2:1 session_2 首 Melanie，
同一 speaker 跨 session 相邻）**

```text
D1:18 → Memory.add(messages=[{"role": "assistant", "content":
    "[Session time: 1:56 pm on 8 May, 2023] Melanie: Yep, Caroline. Taking care of ourselves is vital. I'm off to go swimming with the kids. Talk to you soon!"}], ..., "session_id": "session_1", ...)
D2:1  → Memory.add(messages=[{"role": "assistant", "content":
    "[Session time: 1:14 pm on 25 May, 2023] Melanie: Hey Caroline, since we last chatted, I've had a lot of things happening to me. I ran a charity race for mental health last Saturday – it was really rewarding. Really made me think about taking care of our minds."}], ..., "session_id": "session_2", ...)
```

发现：conv-26 里 session_1 末尾发言者（Melanie）与 session_2 首位发言者（Melanie）是
**同一人**——跨 session 边界处出现"同一 speaker 连续两条"的真实形态，但因为中间跨了一个
`Memory.add()` 调用边界（一次 session_1 D1:18 的单 turn add，一次 session_2 D2:1 的单
turn add），且 `speaker_roles` 字典按 `isolation_key`（=整个 conversation）持续累计、不
随 session 重置，所以两次 add 的 role 仍一致（都是 `assistant`），session time 各自取
自己 session 的 `session_<n>_date_time`，未混用、未跨 session 继承旧时间。这与 pair
粒度 method（如 BEAM）在 session 边界要处理 dangling/anchor 回退不同——turn 粒度天然
没有这个问题。

### 2.2 Synthetic 探针（真实数据集无此形状，仅验证代码路径边界；不代表 LoCoMo 真实频次）

**case2-SYNTH 同一 speaker 连续两条**（真实数据集内 0 例，因为数据集始终 speaker
alternating；用手工构造的两条连续 Caroline turn 验证 `speaker_roles` 不会因为连续同人
而重新分配或报错）：

```text
Memory.add #1: {"role": "user", "content": "[Session time: 1:00 pm on 1 Jan, 2023] Caroline: First synthetic Caroline turn."}
Memory.add #2: {"role": "user", "content": "[Session time: 1:00 pm on 1 Jan, 2023] Caroline: Second synthetic Caroline turn immediately after."}
```

两次都稳定映射为 `user`（因为 `speaker_roles["Caroline"]` 已在真实数据处理阶段确定
为 `user` 并持续复用），无异常、无角色跳变。

**case7-SYNTH caption-only（无正文）**：

```text
Turn(content="", images=[ImageRef(caption="a synthetic caption with no turn text")])
→ Memory.add(messages=[{"role": "assistant", "content":
    "[Session time: 1:00 pm on 1 Jan, 2023] Melanie: a synthetic caption with no turn text"}], ...)
```

**这是最严重的裸拼后果**：当正文为空时，最终 message 变成
`"Melanie: a synthetic caption with no turn text"`——**与 Melanie 真的说了这句话完全
不可区分**，没有任何括号、前缀或标记表明这是图片描述而非人类发言。虽然真实 LoCoMo
数据集里没有这个形状（§2.1 已确认扫描结果为 0），但只要 canonical 层的 `ImageRef`
契约允许 caption-without-text（datasets/locomo.md §3 明确保留该可能性），这条代码路径
就是真实存在的风险面，不是纯假设。

**case9-SYNTH 多 caption（同一 turn 两张图片）**：

```text
Turn(content="Look at these two photos.", images=[ImageRef(caption="first synthetic caption"), ImageRef(caption="second synthetic caption")])
→ Memory.add(messages=[{"role": "user", "content":
    "[Session time: 1:00 pm on 1 Jan, 2023] Caroline: Look at these two photos. first synthetic caption second synthetic caption"}], ...)
```

两个 caption 之间**没有任何分隔符**（`_turn_to_message` 用单个空格 `" ".join(...)`
拼接所有 `content_parts`），如果 caption 本身较长或以小写字母结尾/开头，读者无法界定
两个图片描述的边界。真实数据集里没有单 turn 多 `img_url` 的情况（§2.1 已确认 0
例），此路径当前不会被真实 LoCoMo 触发，但代码本身没有该防护。

**case10-SYNTH 空白 caption 字段（whitespace-only）**：

```text
Turn(content="Just text, caption field is whitespace only.", images=[ImageRef(caption="   ")])
→ Memory.add(messages=[{"role": "assistant", "content":
    "[Session time: 1:00 pm on 1 Jan, 2023] Melanie: Just text, caption field is whitespace only."}], ...)
```

`_turn_to_message` 的 `if image.caption and image.caption.strip()` 守卫**正确**过滤了
纯空白 caption，不会拼出空字符串或多余空格；这一处行为正确，不在 BLOCKED 范围内。

### 2.3 真实数据集全量扫描结论（10 conversation，非抽样）

| 形状 | 真实命中数 | 说明 |
| --- | ---: | --- |
| 同一 session 内连续同 speaker | 0 | 与 `docs/survey/异常情况/locomo.md` L-A2 描述一致（session 内严格轮流，但跨 session 边界可能同人相邻，见 case4） |
| 单 turn 含 2+ `img_url` | 0 | 全部 910 个带图 turn 的 `img_url` 都恰好 1 项 |
| caption 存在但正文为空 | 0 | 与 datasets/locomo.md §3 "caption-without-URL 仍可同时带正文，不是只有 caption 没有正文" 完全吻合 |
| `blip_caption` 字段存在但为空白字符串 | 0 | 未发现 |

## 3. Retrieve / prompt / metric / identity（§6）

- **`Memory.search` 调用**：`self._memory.search(query.text, filters={"run_id":
  query.isolation_key}, top_k=self.config.top_k)`（`_retrieve_native`，
  mem0_adapter.py:1012-1022）。`top_k` 来自 `configs/methods/mem0.toml [smoke]
  top_k = 20`，与 `Mem0Config.smoke()` 硬编码值逐字节一致，且与 mem0.md B9 记录的
  "官方默认 20"（`mem0/memory/main.py:1020/1130`）一致，不是旧 paper 对齐值 200。
- **`formatted_memory`**：`Mem0._memory_context_text(memories)` 产出 `"- {created_at}:
  {memory}"` 或无时间时 `"- {memory}"` 的逐行列表（mem0_adapter.py:1979-1991），无
  created_at 时字节与旧格式保持不变（注释明确说明是为了兼容既有产物字节）。
- **unified answer builder**：`benchmark_adapters/locomo_prompt.py::
  build_locomo_unified_answer_prompt` 只读 `question.text/category` 与
  `retrieval_result.formatted_memory`，拼官方 `LOCOMO_OFFICIAL_QA_PROMPT`
  （逐字保留自 `third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:25-29`）+
  category 2 的日期后缀（`gpt_utils.py:243-244`），与
  `docs/survey/workflows/locomo.md` §3 记录的四步主线完全一致；这是本次预检唯一
  实际运行的 answer builder（未运行 legacy native/author builder，符合卡内约束）。
- **native prompt_messages（可选 sanity 通道，未作为主口径）**：`_retrieve_native`
  同时把 `_reader_messages()` 结果放进 `RetrievalResult.prompt_messages`；LoCoMo 场景
  下 `_reader_prompt_kind()` 恒返回 `"locomo"`，调用 `_build_mem0_locomo_prompt()` 加载
  **current-main** 官方 prompt 模块 `memory-benchmarks/benchmarks/locomo/prompts.py`
  的 `get_answer_generation_prompt`。这与 mem0.md B10 记录的"旧 native 注册 LoCoMo"
  一致；`mem0.toml` 目前没有 `author_locomo` section，因此该通道只作为产物里的
  sanity 对照，不驱动主 answer。
- **RetrievalEvidence（B5）**：`_build_retrieval_evidence()` 对 `benchmark_name ==
  "locomo"` 返回 `semantic_provenance=EvidenceAssertion(status="valid")`，
  `provenance_granularity="turn"`，`stable_ranking=_MEM0_UNAUDITED_STABLE_RANKING`
  （固定 `status="pending"`，reason_code=`ranking_fidelity_not_audited`）。逐题
  provenance 由 `_source_turn_ids_for_memory()` 从 sidecar 精确回查，缺映射直接
  `ConfigurationError` fail-fast，不静默回落——与 mem0.md B5 "LoCoMo=valid(turn)"
  结论一致。
- **adapter/source/protocol/track identity**：`build_mem0_source_identity()`
  对 vendored `mem0/**/*.py` + 根 `pyproject.toml` + `LICENSE` +
  `memory-benchmarks/benchmarks/{locomo,longmemeval}/prompts.py` 做确定性
  SHA-256（mem0_adapter.py:216-285）；`prompts.py` 被纳入哈希范围，意味着 current-main
  官方 prompt 文件变化会反映进 source identity，不会被悄悄漏掉。`consume_granularity`
  由 `_mem0_consume_granularity("locomo")` 落入默认分支返回 `"turn"`，与
  `IngestUnit` 实例类型（`TurnEvent`）交叉一致，参与 manifest/resume 严格比较。
- **TOML smoke 参数**（只抄 current `configs/methods/mem0.toml [smoke]`，未从旧
  frozen note 猜）：`extraction_model=gpt-4o-mini`、
  `embedding_model=sentence-transformers/all-MiniLM-L6-v2`、
  `embedding_dimensions=384`、`embedding_provider=huggingface`、
  `reader_model=gpt-4o-mini`、`top_k=20`、`max_workers=1`、
  `ingestion_chunk_size=1`、`infer=true`、`api_timeout_seconds=60.0`、
  `api_max_retries=8`。与 `Mem0Config.smoke()` classmethod 硬编码值逐字段核对一致
  （无 TOML/代码默认值漂移）；`ingestion_chunk_size` 在 `__post_init__` 强制校验必须
  为 1（非 1 直接 `ConfigurationError`），不是纯文档约束。
- **未修改**：本次预检未变更 metric 公式、gold group、prompt、TOML 或 top_k。

## 4. 现有测试盲点

- `tests/test_mem0_adapter.py` 有 46 个测试函数，其中
  `test_native_mem0_locomo_matches_bridge_add_and_search_sequence` 使用共享 fixture
  `tests/fake_corpus.py::build_multimodal_consecutive_speaker_conversation()`
  （含一个 caption turn `"a blue vase on a table"` 和一对连续同 speaker turn），但该
  测试**只断言 `bridge_result.calls == native_result.calls`**（bridge 与 native 两条
  内部路径的等价性）以及 `run_id`/`filters` 是否正确，**从未断言最终 message content
  的具体文本格式**，因此不会捕获裸拼问题——测试目前是"绿的"，但绿灯不覆盖 caption
  wrapper 正确性。
- 全仓搜索确认：`image_text.turn_text_with_images()` 共享 helper 只被
  `lightmem_adapter.py` 与 `memoryos_adapter.py` 引用，`mem0_adapter.py` 从未导入或
  调用它；`test_mem0_adapter.py` 里不存在任何 "image"/"caption" 关键字的断言。这是一个
  已确认的生产代码 + 测试双重盲点，不是"文档没写但代码其实对"的误报。

## 5. 唯一判词

```text
BLOCKED(caption-raw-concat-no-wrapper)
```

role、speaker 前缀、session time、单 turn add、isolation（namespace 不串
conversation，`_source_turn_ids_for_memory` 严格 fail-fast）五项均通过实测确认符合
canonical 契约与卡内锁死条款；唯一未通过项是 caption：生产 `_turn_to_message()`
（mem0_adapter.py:1444-1482）把 `image.caption` 直接并入 `content_parts` 并用空格
`join`，不使用共享 `[Sharing image that shows: {caption}]` wrapper，也不使用
current-main harness blip-only 分支的等价格式。这在 case7-SYNTH（caption-only）
下最严重：caption 文本与真实人类发言在字节层面完全不可区分。真实 LoCoMo 数据集当前
不产生 caption-only 或多 caption 的真实 turn（§2.3 全量扫描确认 0 例），但
text+caption 的裸拼（case6/case8，真实数据各 1,226/316 个 turn 命中该路径）已经是
真实存在、每次真实 smoke 都会触发的问题，不是纯假设性风险。是否需要生产修复、修复
范围是否影响其余四格（LongMemEval/MemBench/BEAM/HaluMem，据 mem0.md B2 均无独立
caption 处理路径，MemBench 原文本身可能已内嵌 place/time 但未见图片处理注释）由架构师
联合裁决决定，本卡不越权改代码。
