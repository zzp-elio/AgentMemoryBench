# LightMem `messages_use`、MemBench role 与 BEAM 时间审计

> 日期：2026-07-16。性质：架构师一手审计与裁决；零真实 API、零生产代码修改。
> 触发：OpenCode + DeepSeek V4 Flash 指出 LightMem `messages_use="user_only"`
> 可能丢 assistant 信息，并指出 MemBench FirstAgent 被拼成伪 user turn。其报告只作线索，
> 以下结论均由架构师重新读取官方源码、真实数据与当前框架代码后独立裁定。

## 1. 结论先行

1. **LightMem 报告的现象成立，但部分外推不成立。**`messages_use` 真正过滤 extraction
   prompt 和 extraction token 计数；`user_only` 会让真实 assistant 文本不参与事实抽取。
   但“官方模板误复制导致配置错了”没有一手证据；官方 collaborator 已明确确认
   LongMemEval Table 2 的初版结果就是 user-only。
2. **官方代码不是“执行错了”，而是执行了一个受限 profile。**该 profile 可用于复现
   Table 2，却不能冒充“完整双边对话输入”的通用 LightMem 结果。LongMemEval 真实数据
   含 56/500 个 `single-session-assistant` 问题，答案可只存在于 assistant 内容。
3. **unified 主轨改判为 role-complete。**LightMem 必须把 `messages_use` 提升为显式、
   可校验、落 manifest/build identity 的配置；unified 五格固定为 upstream 支持的
   `hybrid`，不按 benchmark 偷换。官方 LongMemEval `user_only` 另列
   reproduction build profile，不能与 unified build collapse。
4. **不修改 LightMem sensory segmentation 核心。**upstream 即使在 `hybrid` 下仍以
   user token/边界为锚，并硬编码 user/assistant 偶对；这是算法身份/限制，不是 adapter
   可悄悄修的兼容 bug。adapter 只负责提供合法 pair/占位与真实 role。
5. **MemBench FirstAgent canonical 映射判错。**官方 reference agent 把 pair 串成文本，
   是它适配 text-only `memory.store()` 的 method-specific serialization，不是 benchmark
   canonical 契约。公共 `Turn` 必须一条 speaker utterance；FirstAgent 一个 step 应拆成
   user turn + assistant turn，ThirdAgent string 仍是一条 user observation。
6. **不能立即施工拆分。**官方 `target_step_id` 指向 pair 级 step；拆成两条 turn 后，
   Recall 的一个 gold 单元应是“命中该 step 的任一/语义承载 child turn”还是另有规则，
   必须先形成通用 evidence-unit/qrel 契约，禁止机械把一个 gold step 变成两个必命中项。
7. **BEAM 时间现状正确，不解冻。**100K/500K/1M 的真实 Arrow 均只在每 session
   首个 user turn 放 `time_anchor`；当前 adapter 将其提升为 `session_time`，事件层按
   `turn_time → session_time → None` 传递。10M 只有 1/1000 session 完全无 anchor，
   继续诚实保持 None。

## 2. LightMem `messages_use` 的真实执行链

### 2.1 配置与过滤不是装饰字段

- `BaseMemoryConfigs.messages_use` 默认 `user_only`，允许
  `user_only/assistant_only/hybrid`：
  `third_party/methods/LightMem/src/lightmem/configs/base.py:37-44`。
- `ShortMemBufferManager._count_tokens()` 按配置选择 role；`hybrid` 才同时计入两侧：
  `third_party/methods/LightMem/src/lightmem/factory/memory_buffer/short_term_memory.py:11-21`。
- OpenAI manager 在 `concatenate_messages()` 中再次按 role 过滤，过滤后的文本才进入
  extraction prompt：
  `third_party/methods/LightMem/src/lightmem/factory/memory_manager/openai.py:281-313`。
- 当前 framework 没有 `LightMemConfig.messages_use` 字段，而是在
  `build_backend_config()` 中硬编码 `"user_only"`：
  `src/memory_benchmark/methods/lightmem_adapter.py:521`。

因此，DeepSeek 关于“assistant 不进入事实抽取、最终无法从 Qdrant 检索”的核心判断成立。

### 2.2 官方 LongMemEval 事实与 PR #72 的证据等级

- 官方 GPT/Qwen 脚本都显式写 `"messages_use": "user_only"`，同时把真实
  user/assistant pair 传给 `add_memory()`：
  `experiments/longmemeval/run_lightmem_gpt.py:100,151-173` 与
  `run_lightmem_qwen.py:118,169-191`。
- [GitHub issue #70 的 collaborator 回复](https://github.com/zjunlp/LightMem/issues/70#issuecomment-4849709276)
  明确说明：初版使用 `user only`，对应 Table 2。此回复是一手作者侧说明。
- [PR #72](https://github.com/zjunlp/LightMem/pull/72) 只修改
  `experiments/longmemeval/readme.md`，截至取证时仍为 OPEN、无 review；
  PR 作者不是 collaborator。它准确转述脚本与 issue，但只是文档澄清，不能证明该选择
  对所有任务语义合理，更没有修复 extraction 行为。

裁决：**官方 Table 2 user-only 是可复现事实，不是通用正确性证明。**“模板误复制扩散”
属于无证据推测，撤回；“配置造成双边数据丢失”则由源码直接证明，保留。

### 2.3 LongMemEval 不是纯 user-memory 数据

对 `data/longmemeval/longmemeval_s_cleaned.json` 流式扫描 500 题，类别计数为：

| question_type | 数量 |
|---|---:|
| single-session-user | 70 |
| single-session-assistant | 56 |
| single-session-preference | 30 |
| multi-session | 133 |
| temporal-reasoning | 133 |
| knowledge-update | 78 |

真实 `single-session-assistant` 样本 `7161e7e2` 的问题询问 Sunday 的 Admon shift；user
只给人数、班次、日期范围与姓名，最终分配表只在 assistant reply 中。另一个样本
`c4f10528` 的餐厅名与 Nasi Goreng 推荐也在 assistant reply。`user_only` 对这类问题不是
“粒度差异”，而是 source evidence 不可见。

### 2.4 `hybrid` 仍然是 user-anchored segmentation

`sensory_memory.py` 的实现有三条必须原样披露的限制：

1. token 累计与 `_recount_tokens()` 只看 `role == "user"`（`:11-18`）；
2. coarse boundary 文本只取 user（`:47-48`）；
3. fine segmentation 按 `[i], [i+1]` 硬编码偶对（`:59-63`）。

所以 `hybrid` 能让 assistant 内容进入 extraction，却不把 segmentation 变成完全对称算法。
Phase 1 不修改这段算法核心；build identity/note 必须写
`hybrid extraction + user-anchored pair segmentation`，防止“hybrid”被误读成全链对称。

## 3. 五 benchmark role 传递矩阵

| benchmark | canonical 源形态 | 当前 benchmark adapter | 当前 LightMem 路径 | 裁决 |
|---|---|---|---|---|
| LoCoMo | 两个命名 speaker，不是 user/assistant | speaker 名无损保留 | 每条 utterance 包成 user + 空 assistant | 官方姿态；`hybrid` 下空 assistant 不增加内容 |
| LongMemEval | 真实 user/assistant | role 正确 | pair 正确，但 `user_only` 丢 assistant | unified 改 `hybrid`；官方 user-only 另列 reproduction build |
| HaluMem | 真实 user/assistant | role 正确 | session 原 role，`user_only` 丢 assistant | unified 仍按固定 role-complete build 用 `hybrid`；HaluMem Mem0-Graph 的 user-only 指令只证明一个 method-specific native profile |
| BEAM | 真实 user/assistant | role 正确 | 每个 TurnEvent 被重包成 user + 空 assistant，内容没丢但 role 被洗掉 | 必须改为真实 role 的 pair/合法占位；不能以“speaker_name 还在”宣布 B4 通过 |
| MemBench FirstAgent | 一个官方 step 含 `{user, agent}` | **错误：拼成一个 user turn** | 拼接文本作为 user，内容在但 canonical role 已坏 | benchmark adapter 定点解冻，先裁 evidence-unit 契约再拆 |
| MemBench ThirdAgent | observer 收到的 string stream | 一条 user observation | user + 空 assistant | 当前角色语义成立 |

HaluMem 特别说明：官方 `eval_memzero_graph.py:27-53` 的 Mem0 Graph custom instruction
明确要求只从 user message 抽 memory；因此 DeepSeek 所说“assistant 幻觉修正一定丢失”不能
直接升格成 benchmark 结论。另一方面，HaluMem adapter 与 method-neutral reader 都保留双侧
对话。unified 五格不为某一官方 method harness 动态改 `messages_use`，避免同一 build identity
跨 benchmark 漂移；user-only HaluMem 如需复现，应单独盖 native/reproduction identity。

## 4. MemBench：官方 step 不是 canonical Turn

### 4.1 为什么当前拼接有来源、仍然是错的

- 官方 `load_test_data.py:188-205` 把 FirstAgent 每个 source pair 输出为
  `{user: ..., agent: ...}`；这说明两个 role 都是公开数据。
- 官方 `MembenchAgent.py:65-72` 因它的 memory 接口只收 text，才调用
  `memory.store("'[user]': ...; '[agent]': ...")`，并把 agent reply 同时作为环境 action。
- 当前 framework `membench.py:712-740` 把这段 method-specific serialization 搬到
  benchmark adapter，再把整条标成 `speaker=user/normalized_role=user`。
- 核心实体 `core/entities.py:37-49` 已明确：`Turn` 是“一个 speaker 的一次 content”。

裁决：官方 reference agent 的字符串格式可以作为 text-only method renderer 参考，不能成为
canonical schema。现有“1 step = 1 turn”测试是旧裁决产物，必须随版本化修复改写。

### 4.2 不能用简单拆二解决 Recall

官方 `target_step_id` 是 `message_list` 的 0 基 step id。FirstAgent 的一个 step 拆成
`<step>:user` 与 `<step>:assistant` 后，至少存在四种实现候选：

1. gold qrel group：一个 step 对应一组 child turn ids，以 any-of/group 规则计一次；
2. provider 另报 `source_unit_id`，与 `source_turn_ids` 分离；
3. 把 `TurnPair` 升成 canonical 数据实体；
4. 通过 turn-id 字符串前缀反推 step。

第 4 种脆弱；第 3 种改动面最大；第 1/2 种谁更符合现有 RetrievalEvidence、BEAM raw-id
歧义与 LongMemEval session/turn 双粒度，需要独立一手审计。审计完成前不让 actor施工，
Recall/NDCG 保持 pending，不用现有绿测替错误输入背书。

## 5. BEAM 时间与 role 的真实数据复核

用本地官方 Arrow 全量逐 turn 统计：

| variant | rows | turns | 非空 anchor | session 形态 | role |
|---|---:|---:|---:|---|---|
| 100K | 20 | 5,732 | 90 | 90/90 都只有首 turn | user/assistant 各 2,866，严格交替 |
| 500K | 35 | 38,058 | 350 | 350/350 都只有首 turn | user/assistant 各 19,029，严格交替 |
| 1M | 35 | 74,630 | 350 | 350/350 都只有首 turn | user/assistant 各 37,315，严格交替 |
| 10M | 10 | 208,696 | 999 | 999 first-only + 1 none | 基本交替；存在 2 个同 role adjacency |

所有非空 anchor 都落在 user role。当前 `beam.py:612-640` 把 session 内首个非空
`time_anchor` 同时写入该 turn 的 `turn_time` 与 session 的 `session_time`；
`event_stream.py:30-49` 再用 `turn.turn_time or session.session_time` 生成每个事件的
effective timestamp。这正是用户裁定的 `turn → session → None`，无需把同一个 anchor
复制进每个 canonical Turn 字段。

BEAM temporal question 的 source content 经抽样也常含显式日期，但框架不能因此丢弃结构化
anchor：两条通道都保留，既不依赖文本偶然措辞，也不制造新事实。10M 唯一无 anchor session
继续 None；两处同 role adjacency 要进入未来 pair 强反例，禁止假设所有数据绝对交替。

BEAM role 另有独立问题：当前 canonical role 正确，LightMem `_native_turn_batch()` 却把每个
event 重包成 user。真实 gold `source_chat_ids` 统计显示 assistant evidence 确实存在：例如
100K information_extraction 有 7/40 题是 assistant-only，summarization 有 12/40 题
assistant-only、21/40 mixed；因此不能用 user-only role truth 解释现有行为。

## 6. 过时文字与勘误

`notes/m0-4-membench-beam-lightmem-compat.md:427-429` 曾裁：assistant 内容虽被改成
user-role，但 `speaker_name` 与 content 还在，所以 role 变化不列 blocker。该裁决现已过时：

1. extraction filter 看的键是 `role`，不是 `speaker_name`；
2. canonical role 是 method 输入语义的一部分，内容没丢不等于 role 无损；
3. MemBench FirstAgent 在更上游已经把两个 speaker 合成一个伪 user turn；
4. BEAM gold 中存在 assistant-only/mixed evidence。

旧 note 保留历史，不改写当时输出；文件顶部增加 superseded banner，现行结论以本文为准。

## 7. 对 LightMem 重认证的影响

- 保留：B1 产品接口、B3 物理隔离、B6 online-soft/finalize、B7 观测框架、B8/B8+、
  canonical-required MiniLM 的既有一手证据；这些不因 role 问题自动作废。
- 重开：B2（pair/session 组织）、B4（role/input visibility）、B5/B5+（step vs turn
  evidence unit）、B9（`messages_use` 属 build identity）、B10（unified hybrid 与
  official user-only 不同 build）、B11（受影响五格必须重新 build/smoke）。
- RetrievalEvidence M1 与本支线合流：evaluator 必须先理解 gold evidence unit，不能只校验
  provider provenance granularity。
- 未获用户预算、规模、run_id 批准前，继续禁止真实 API、模型下载与付费 smoke。

## 8. actor 线索评价

OpenCode + DeepSeek V4 Flash 本轮的价值很高：准确抓到 `messages_use` 的实际过滤效果和
MemBench 拼接点，直接推翻了一个旧准入结论。需要架构师订正的部分有两处：

1. “官方模板复制失误”无作者证据；官方已确认 user-only 是初版实验设置；
2. HaluMem assistant 内容是否应进入 memory 不能凭直觉下结论，官方至少有一条明确的
   user-only method prompt。

由于这不是按正式 actor 卡提交的 commit/diff，暂不写 10 分制正式评分；记录为
“高价值发现，外推需收紧”。

## 9. `hybrid` 与空 slot 的补充裁决（2026-07-16）

用户提出：五 benchmark 固定 `hybrid`，LoCoMo/第三人称等单侧 utterance 用另一 role 的
空 message 补齐 LightMem 偶对结构。方向成立，但“与 user-only 效果完全一样”要拆成两层：

1. **事实 payload 等价**：LoCoMo 的真实 speaker utterance 仍只在 user slot；空 assistant
   不携带事实，因此 `hybrid` 覆盖了 user-only 可见的全部真实内容。
2. **当前 prompt 字节不等价**：官方 `concatenate_messages()` 对允许 role 不检查空 content，
   会把空 assistant 也渲染成 `序号.Speaker A: ` 一行（
   `third_party/methods/LightMem/src/lightmem/factory/memory_manager/openai.py:295-311`）；
   short-memory token join 也会保留空项产生的分隔空格（`short_term_memory.py:18-22`）。
   所以未经修复不能声称 token、prompt 或随机输出严格等价。

正式裁决仍是：**unified 五格固定显式 `messages_use="hybrid"`。**adapter 用一个通用
role-slot normalizer 保留每条真实 utterance 的 user/assistant role，并只为满足 upstream
偶数位置约束补结构占位：user-only utterance→`[real user, empty assistant]`；
assistant-only utterance→`[empty user, real assistant]`；正常 user→assistant 可直接成对；
连续同 role、assistant-first、dangling 与单 role session 均不得丢弃或改 role。

结构占位必须带明确内部 marker，继续参与 sensory pair 位置，但在 compression token 计数与
extraction 文本渲染时被排除；这样 LoCoMo 的事实 extraction 输入才与 user-only 真正收敛，
同时 LongMemEval/BEAM/HaluMem 的 assistant 事实可进入 hybrid extraction。该适配不修改
LightMem 的 user-anchored segmentation 算法；assistant-only pair 的 boundary 仍不完全对称，
作为 upstream algorithm limitation 留在 build identity/note 中。官方 LongMemEval Table 2
`user_only` 继续是独立 reproduction profile，不能与 unified-hybrid 产物 resume/collapse。

## 10. `source_id` 是 pair index：hybrid 可见性不等于 turn-level lineage（2026-07-16）

用户给出的 LightMem PR #72 经架构师现场打开确认：它仍是 **open 的 docs-only PR**，作者
说明 LongMemEval 两个脚本硬编码 `user_only`，并称 Table 2 使用该配置；同时把 `hybrid`
描述为同时索引 user/assistant。它证明“官方实验姿势”和“配置选项的设计意图”，但没有
maintainer review/merge，也没有修改下述运行时代码，因此不能拿 PR 文案替代源码验收。

继续沿源码追到 extraction→MemoryEntry 后，发现一个比空 placeholder 更承重的边界：

- extraction prompt 的展示编号是 `sequence_number // 2`（
  `factory/memory_manager/openai.py:295-311`），所以同一 user/assistant pair 共用一个
  `source_id`；
- `convert_extraction_results_to_memory_entries()` 与
  `_create_memory_entry_from_fact()` 固定用 `source_id * 2` 读取 user slot 的 timestamp、
  speaker 和 `external_id`（`memory/utils.py:263-303,342-355`）；
- `max_source_ids` 也按 user slot 数量计算（`memory/lightmem.py:363`）。

因此，`[empty user, real assistant]` 若只修 prompt 过滤，assistant 内容虽可被看到，生成的
MemoryEntry 仍会从空 user slot 取 lineage；正常 `[real user, real assistant]` 下，官方
`source_id` 也无法分辨事实来自 pair 中哪一侧。**“assistant 进入 extraction prompt”不等于
“得到 assistant-turn 精确 provenance”。**

正式裁决补充如下：

1. unified 五格仍统一显式 `hybrid`；这是 role-complete 产品主轨。LongMemEval
   `user_only` 单列 reproduction profile，不与 unified 合并。
2. 通用 role-slot normalizer 为每个 pair 生成稳定的 real-child-id 集合；结构 placeholder
   只补位置，不作为额外 child。该集合以纯观测字段穿过 normalizer→MemoryEntry→Qdrant
   payload→RetrievedItem；单真实 utterance 退化为 1 个 id，正常 pair 为 2 个候选 id。
   这不修改抽取、embedding、检索或更新算法。
3. placeholder 必须在 short-memory token 计数与 extraction 文本中跳过；但仍留在 sensory
   偶数位置。assistant-only pair 的 boundary 仍由空 user 锚定，属于 upstream
   user-anchored segmentation limitation，必须在 build identity/报告披露。
4. pair candidates 只是“该 fact 的来源候选集合”，不得把每个 child 都宣称为精确语义
   来源。按 benchmark 裁资格：LoCoMo 每 pair 只有 1 个真实 utterance，可保持 turn-level
   exact；MemBench FirstAgent 的官方 gold 本来就是 pair-step，待 canonical split + gold
   group 后可按 step unit 计；LongMemEval 的 **turn** qrel 与 BEAM 单 message qrel不能从
   pair candidates 得到精确语义映射，M1 前保持 N/A/pending；LongMemEval session view
   待 M1 单独裁；HaluMem 无 turn qrel，仍 N/A。

所以用户的“hybrid 覆盖 user_only”在**真实内容可见集合**上成立；在 prompt 字节、分段、
随机抽取结果与 turn-level provenance 上不成立。这个区分既保住五格统一 profile，也避免
为了填 Recall/NDCG 矩阵制造假精度。
