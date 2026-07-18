# LightMem × 五 benchmark 格子安全说明（living dossier）

> 读者：项目 OWNER、架构师与后续接任 actor。
>
> 目的：用一份人能直接复查的文档回答“为什么这个格子敢跑”。本页不替代底层 audit、实现
> note、测试和 run artifact；它只把承重结论、异常处置、能力边界与证据入口压成一张安全图。
>
> 更新规则：每压实一个 LightMem × benchmark 格子，就在本页完成一个章节；发现新反证时先
> 降级该格状态，再更新底层证据，禁止让旧绿灯继续挂着。

## 0. 为什么不是 5 × 10 份顶层文档

Phase 1 确实有 50 个 method × benchmark **验证格子**，但不需要 50 份互相漂移的顶层说明。
现行组织是：

- **每个 method 一份 living dossier**，最终约 10 份；
- 每份 dossier 内有 5 个 benchmark 章节，格子仍逐一给判词；
- 全量数据统计、临时 probe stdout、实现历史和真实 run 验货继续放在各自底层 note；
- dossier 只写“异常是什么 → 哪一层处理 → method 最终看到什么 → 为什么可接受 → 还缺什么”，
  并链接底层证据，不重复倾倒几百行取证。

这样既保留 50 格的独立责任，又不会制造 50 个孤立入口。**一份 method dossier 是目录和安全
摘要，不是把五格混成一个总绿灯。**

## 1. 状态图与判词含义

| 格子 | 当前判词 | 这句话实际承诺什么 | 尚未承诺什么 |
|---|---|---|---|
| LightMem × LoCoMo | `REAL_SMOKE_PASSED` | v6、hybrid、online-soft 的单/双 worker 真实 B11 已验货 | 不代表作者 post-update reproduction、稳定排序或 full 效果 |
| LightMem × LongMemEval | `READY_FOR_B11_SMOKE` | current v6 离线输入链、异常链、readout 与 metric 资格已闭合，可以开始裁剪 smoke | 尚无 latest-v6 真实 B11，不代表 full、效果或成本校准完成 |
| LightMem × MemBench | `PENDING_GRID_RECERTIFICATION` | 既有代码/历史 smoke 仍是证据索引 | 本 dossier 尚未逐异常重新对表，不在本页宣布通过 |
| LightMem × BEAM | `PENDING_GRID_RECERTIFICATION` | 同上 | 同上 |
| LightMem × HaluMem | `PENDING_GRID_RECERTIFICATION` | 同上 | 同上 |

判词必须分层：

1. `READY_FOR_B11_SMOKE` 只允许发真实接线 smoke；
2. `REAL_SMOKE_PASSED` 才表示 B11 五件套与并行实测已验收；
3. `FULL_READY` 还需效果参数、成本 pilot、resume 等正式实验门，本页前两格均未宣称；
4. `N/A` 是某项 metric 的诚实能力结论，不会把整个接入格判成失败。

## 2. LightMem 五格共同前提

以下是两个已写章节共用的 method 契约；每格仍需证明 benchmark 映射没有破坏它。

| 共同轴 | 当前主配置 | 安全含义 |
|---|---|---|
| 产品入口 | `LightMemory.add_memory()` + embedding retriever search | 走通用产品实现，不走 benchmark 专用评测 runner |
| role 可见性 | `messages_use="hybrid"` | user 与 assistant 的真实文本都可进入 extraction；结构 placeholder 被严格 marker 过滤 |
| lifecycle | `online_soft` | 抽取后 direct insert LTM；conversation 尾只 flush，不执行全库 merge/delete consolidation |
| embedding | `all-MiniLM-L6-v2` / 384 / Qdrant cosine | 当前 smoke build 身份明确；效果主表最终 embedding 仍待正式实验前裁定 |
| reader | benchmark-owned unified builder | LightMem 只提供 `formatted_memory`；answer prompt/LLM 在同 benchmark 内 method-neutral |
| 隐私 | method 只收 public Turn/Query | answer、gold evidence、`has_answer`、judge label 不可达 ingest/retrieve/answer prompt |
| 运行身份 | adapter `conversation-qa-v6` + protocol/manifest identity | caption/role/lifecycle 变化会阻止旧 store 被误 resume |

最重要的共同边界是：**online-soft direct insert 可以逐题判断当前条目的 provenance；显式
consolidated profile 会 merge/update，不能继承同样的 Recall/NDCG 资格。**本 dossier 的前两格
都只认证 Phase 1 主 `online_soft` build。

另一个容易误读的 upstream 命名债：backend config 仍写 `update="offline"`，它在 vendored
实现里选择的是 `offline_update(memory_entries)` 这个“抽取结果 direct insert”函数；真正的全库
合并/删除入口是 `offline_update_all_entries()`，另受 lifecycle gate 控制。前两格的主 profile
均挡住后者。conversation 末尾的 `force_extract=True` 只是刷出最后一批，不等于全库 offline
consolidation。

---

## 3. LightMem × LoCoMo

### 3.1 当前结论

```text
REAL_SMOKE_PASSED
```

这里的“可以跑”建立在三层证据上：

1. source-locked LoCoMo 全量异常账；
2. canonical Turn → LightMem payload 的离线强反例，含 caption v6；
3. 最新 v6 单 worker + 双 worker 真实 build、retrieve、answer、evaluate 与物理 state 验货。

它不是“因为测试没报错”，也不是“因为作者自己跑过 LoCoMo”。

### 3.2 双 speaker 不是 user / assistant，如何不把身份弄错

LoCoMo 的发言者是两个 named human speaker。canonical adapter 保留：

```text
Turn.content          = 原 utterance
Turn.speaker          = 真实 human name
Turn.normalized_role  = None
Turn.id               = D<session>:<line>
```

LightMem 产品接口需要 `[user, assistant]` 形状，因此本框架对**每个真实 utterance 独立**构造：

```text
[
  REAL user slot:
    content=<原文 + 可选 caption wrapper>
    speaker_id=speaker_a|speaker_b
    speaker_name=<真实 human name>
    external_id/source_external_ids=<该 turn id>
  EMPTY assistant slot:
    content=""
    speaker_id/name/time/lineage 镜像同一真实 turn
    memory_benchmark_structural_placeholder=True
]
```

- framework 的公共消费粒度仍是 **turn**；只是 backend payload 是 pair-shaped；
- `user/assistant` 只是 LightMem 结构槽，不会把第二位 human 冒充 assistant；
- empty assistant 不是 canonical turn，不产生新 id，并从 extraction prompt 与 token count 过滤；
- 因此 `hybrid` 在 LoCoMo 上与官方 `user_only + empty assistant` 的可见文本字节级等价。

承重实现：`locomo.py::_turn_from_raw`、`lightmem_adapter.py::_locomo_pair/_native_turn_batch`。

### 3.3 LoCoMo 特殊/异常情况与处置

| 编号 | 数据事实或风险 | 框架如何处理 | 为什么可以接受 / 不能怎样解释 |
|---|---|---|---|
| L1 | `conv-26` 只有 19 个 session list，却多出 16 个 date-only key | canonical adapter 只枚举严格 `session_<n>` list；孤儿日期留在 raw，不建 phantom Session | 不会给 LightMem 灌入 16 段不存在的对话，也不写 `conv-26` method 特判 |
| L2 | 140/272 个 session 为奇数 turn | 原顺序全保留；每个 named-speaker utterance 自成一个 LightMem pair | 不会丢尾 turn，也不把相邻两个人类发言硬解释成 user→assistant |
| L3 | 5,882/5,882 turn 无独立时间；272/272 session 有时间 | 每个 turn 只继承所属 session source time；真实与 placeholder slot 都携带它 | 不用 question time、相邻 turn 或 wall clock 造时间；LightMem 后续 500ms/1,000ms 只是 method-derived order time |
| L4 | 910 个 `img_url` turn、1,226 个 caption turn、316 个 caption-without-URL | canonical 保存 raw text + `ImageRef.caption`；LightMem v6 在 method 边界恰渲染一次 `[Sharing image that shows: {caption}]` | caption 对 extraction/embedding 可见；URL/query 不进 content、不下载图片；无有效 caption 时原文 bytes 不变 |
| L5 | 9 个 raw evidence unit 无法 exact-match turn，例如 `D8:6; D9:17`、`D`、`D:11:26` | evaluator-private Gold Evidence Group 保留 raw atom；turn view 标 `unmatched`、留分母恒 miss，不猜拆/纠错 | 这是 gold 标注异常，不是 method 输入；LightMem 永远看不到 evidence |
| L6 | `conv-50/qa[5]` 的 `D4:5` 重复出现 | group unit 按首次出现稳定去重并披露与官方 raw 重复计权的分叉 | 不让一个 utterance 因标注重复获得双重权重 |
| L7 | 4 道 category-3 题有 answer 但 evidence 为空 | 复刻官方 overall Recall=1，同时单报 empty count 与 non-empty mean | 这四个 1 不能解释为 LightMem 检索成功；gold 仍不可达 method |
| L8 | 当前 release 用 `img_url`，旧统计脚本写 `img_file` | source-locked adapter 只认当前 JSON 的 `img_url + blip_caption` | 不为了对齐旧脚本而制造不存在的字段 fallback |
| L9 | 图片 `query` 与 path/URL 也是公开 metadata | 共享 renderer 只读 caption | query 不会被当成 speaker 记忆，路径不会污染 embedding 文本 |

完整异常位置、JSON 行号和实例见
[LoCoMo 异常处置账](../../../../../../survey/异常情况/locomo.md)。

### 3.4 图片缺口为什么已经真正关闭

首轮离线预检曾发现 v3 event 虽保留 `turn_images`，LightMem 却只恢复
`original_content`，导致 1,226 个 caption 确定性丢失；默认 1-round smoke 又刚好看不到首个
caption，所以“零报错”无法发现。

v6 的关闭条件不是“加了一个字符串”：

- legacy 与 v3 都恢复同一个 `ImageRef`；
- 两条入口共用 `turn_text_with_images()` 语义；
- caption-bearing payload 字节级一致、wrapper 恰一次；
- caption-only、多 caption、空/纯空白 caption、无 caption 都有强反例；
- query、URL/path 与旧 `(image description: ...)` wrapper 均不泄漏；
- 无可渲染 caption 时保留原 content 首尾空白；
- adapter v5→v6，旧 store 不可被新 run 误 resume。

真实 smoke 又特意取 3 rounds，使首个 caption turn `conv-26/D1:5` 真正进入 backend；单/双
worker 的 Qdrant lineage 均能看到该 turn。离线测试证明输入字节，真实 smoke 证明新 build
确实走了这条路径，两层证据缺一不可。

### 3.5 lifecycle、检索与 metric 为什么没有勉强计算

- 主 profile 是 `online_soft` direct insert，不跑 all-entry merge/delete；因此 retrieved item 的
  turn lineage 没有被后续内容更新破坏；
- method 自身 combined retrieval limit=60，framework 当前落 artifact 的 observation depth=10；
- LoCoMo 逐题 semantic provenance=`valid`、granularity=`turn`，所以 group Recall@10 可算；
- 架构师从 top-k public ids 与 private gold groups 独立复算三题 Recall 均为 1；重复 retrieved
  source id 先去重，不重复加分；
- stable ranking 仍为 `pending`，所以不能由 Recall=1 推导 NDCG/rank 健康；
- consolidated 补充 profile 会 merge/update，provenance metric 保持 N/A，不借主 profile 的绿灯。

### 3.6 真实 B11 验货覆盖

| run | 规模 | 额外覆盖 |
|---|---|---|
| `lm-locomo-v6-r3q1-w1` | 1 conversation × 3 rounds × 1 question × 1 worker | caption turn、单 state、四项当时适用 metric |
| `lm-locomo-v6-r3q1-c2-w2` | 2 conversations × 3 rounds × 1 question × 2 workers | worker 物理隔离、两 collection、跨 conversation 无 state 泄漏 |

两个 run 均检查 checkpoint、prediction/prompt/private-label 行数、隐私扫描、formatted memory、
Qdrant payload、效率三层 summary 与 evaluator artifact。后续 normalized EM/substring EM 直接
消费既有 prediction，零 API 追加；lexical 低分不反向解释为接线失败。

### 3.7 LoCoMo 仍然诚实保留的限制

1. 当前主配置是 unified hybrid/online-soft，**不是**作者 user-only + post-update 的完整复现；
2. 当前 smoke 不代表 full 效果，三题分数不能作 method 排名；
3. stable ranking 未审计，rank/NDCG pending；
4. 本地 embedding revision 为 `local_unpinned`，效果 full 前要完成最终参数裁决；
5. `author_locomo` section、完整作者 answer builder 与真实 resume 留到对应正式门；
6. dataset/source identity、caption renderer、Gold Evidence Contract 或 adapter version 任一变化，
   本格必须重新开门，不能沿用本页旧绿灯。

底层证据：

- [LoCoMo 离线预检](lightmem-locomo-smoke-config-preflight.md)
- [caption v6 + R1 实现与强验收](lightmem-locomo-image-caption-implementation.md)
- [真实 smoke / frozen-v2 验货](lightmem-frozen-v2.md)

---

## 4. LightMem × LongMemEval

### 4.1 当前结论

```text
READY_FOR_B11_SMOKE
```

这里的“可以跑”只表示 latest v6 的离线门已经证明：

```text
raw instance
→ canonical role/time/public boundary
→ TurnPair
→ LightMem hybrid message
→ online-soft flush
→ retrieve(filters=None)
→ benchmark unified answer builder
→ evaluator eligibility
```

六类真实 role 形状均无丢失、重复、跨 session 配对或 role 猜测；但 latest v6 的真实 B11 尚未
执行，所以本格不能写 `REAL_SMOKE_PASSED`。

### 4.2 LongMemEval 的自然结构

- 1 instance = 1 question + 一整段专属 haystack；框架 conversation id = question id；
- session 有 `haystack_date`，turn 只有结构化 `role + content`，没有独立 timestamp；
- `answer`、`answer_session_ids`、turn 上的 `has_answer` 都是 evaluator-private；
- S/M 各 500 instance；S=`246,750` raw turn，M=`2,446,993` raw turn；
- 正式效果/full 必须保留完整 haystack；registered smoke 可以按 round 裁剪，只验证接线。

### 4.3 六类 role 形状如何进入 LightMem

LightMem 需要 pair，framework 的 user-anchor 聚合规则与最终 payload 如下：

| raw role 形状 | TurnPair | LightMem payload | 是否保留每条 real turn |
|---|---|---|:---:|
| `user→assistant` | real-real | `[real user, real assistant]` | 是 |
| `assistant→user→assistant` | orphan + real-real | `[placeholder user, real assistant]` + `[real user, real assistant]` | 是 |
| `user→user` | dangling + dangling | 每个 user 各自 `[real user, placeholder assistant]` | 是 |
| `assistant→assistant` | orphan + orphan | 每个 assistant 各自 `[placeholder user, real assistant]` | 是 |
| 单 user | dangling | `[real user, placeholder assistant]` | 是 |
| 单 assistant | orphan | `[placeholder user, real assistant]` | 是 |

placeholder 的契约非常严格：`content=""`、boolean marker=True，镜像同 pair 真实 child 的
speaker/time/external id/candidate ids；它不产生 canonical turn、不创造 source id，并从 extraction
prompt 与 token count 过滤。真实 blank turn 则在 canonical adapter 更早被跳过，两者不能混淆。

全量恒等式已经复算：

```text
retained canonical turn = raw turn - blank turn
                        = real-real pair * 2 + orphan + dangling
```

S=`246,738`、M=`2,446,698`，证明每个 retained real turn 恰好出现一次。

### 4.4 LongMemEval 特殊/异常情况与处置

| 编号 | 数据事实或风险 | 框架如何处理 | 为什么可以接受 / 必须披露什么 |
|---|---|---|---|
| M1 | blank turn：S=12、M=295 | 跳过空白正文，但公开 id 仍按 raw index 构造，后续 id 不前移 | 不向 method 注入无语义空文本，也不让删除导致 id 漂移 |
| M2 | assistant-first：1,871/18,822；pure-assistant：71/609；consecutive-same：5/39 | 结构化 role 原样读，不从 content/speaker 猜；orphan/dangling 用 placeholder 补产品 pair 槽 | retained turn 全保留，不跨 session 配对 |
| M3 | odd session：1,940/19,395 | 尾部真实 turn 形成 dangling/orphan pair | 不丢尾 turn；placeholder 不伪装成真实消息 |
| M4 | 官方 LightMem `user_only` harness 会丢 2,020/20,283 raw turn，含 3+3 个 answer-session assistant fact | Phase 1 主 profile 使用 hybrid + placeholder，保留全部 retained turn | 这是 unified 与 author reproduction 的有意分叉；不得把 hybrid 结果冒充论文 Table 2 复现 |
| M5 | turn 无时间，只有 session time | `_turn_timestamp` 只执行 turn→本 session fallback；不读 question/邻居/wall clock | source time 仍是 dataset session time；持久化的细粒度时间是 method-derived order time |
| M6 | 同 raw session time 会触发 LightMem 两层 500ms 序列化 | normalizer per-pair，force-extract 时按相同 raw key regroup 覆写；distinct raw timestamp 保持原值 | placeholder 占 slot；连续同 role 的真实 turn 间隔可能多 500ms，assistant-first fact 锚 pair base，必须披露，不能称 turn source time |
| M7 | q<latest：76/118；q<earliest：1/0；future-gold：44/42 | 保留 raw question/session timestamp与完整 history；retrieve 明确 `filters=None` | OWNER 说明同日 HH:MM 不可靠、官方也不按 question time filter；不清洗、不造 corrected timestamp |
| M8 | 30 个 `_abs` + 51 个 non-abs no-user-target | evaluator-private benchmark policy 按官方主 retrieval 路径剔除，canonical turn 分母=419 | 不把无官方 user target 的题塞进 retrieval 分母，也不让 method 看见筛选 gold |
| M9 | `has_answer` 可出现在 assistant side | 只在 private audit metadata 保留；canonical retrieval group 只用官方 user-side target | 不把 assistant target 偷加进官方主 scorer，也不泄漏给 method |
| M10 | pair 的 candidate ids 不能证明 fact 来自 pair 内哪个 child | RetrievalEvidence 发 `n_a/pair_source_id_not_turn_exact`、granularity=none | LongMemEval Recall/rank 写 `score=None,status=n/a`，不是报错或伪 0 分 |
| M11 | question time 对 temporal answer 有用，但不能控制记忆可见性 | 只进入 benchmark-owned `Current Date` answer prompt | 检索 embed 的只是 question text，search 无时间 filter |
| M12 | M variant 约 2.7GB | 只允许流式加载/扫描 | 不用一次性 `json.load/read_bytes` 制造内存风险；本轮不重复扫 M |

关于 M7 的关键裁决：cleaned JSON 虽有具体 `HH:MM`，但官方 OWNER 说可靠语义只到日期；
同日 question 应理解为紧接最后 conversation。框架没有改写 raw 字段，只遵循官方实际执行的
“完整 history 可见”语义。因此既不把错序当 as-of cutoff，也不制造第三份时间。

### 4.5 placeholder 与 500ms：保住了什么，又没有假装保住什么

placeholder 能无损保住：

- 真实 child 的 content 可见性；
- source session time；
- speaker；
- external id 与 pair candidate lineage；
- 每个 retained turn 恰一次。

placeholder **不能**证明：

- fact 来自 real-real pair 的哪一个 child；
- assistant-first fact 的 method-derived timestamp 精确等于 assistant slot；
- 连续真实 turn 的 500ms 间隔是 dataset 提供的时间。

所以框架没有为了算 Recall 强行声称 turn-exact provenance，而是保留 pair 结构用于 build，并把
LongMemEval turn Recall/rank 诚实判为 N/A。这正是“可以跑，但不是所有指标都能算”的例子。

### 4.6 lifecycle、query、answer 与 metric

- 主 `online_soft` 不运行全库 consolidation；conversation 末只 force segment/extract + direct
  insert；
- retrieve 使用同一 embedder、`limit=60`、`filters=None`、`return_full=True`；
- `formatted_memory + question + question_date` 进入 benchmark-owned non-CoT builder；
- unified answer：`gpt-4o-mini`、temperature=0、max_tokens=500、top_p=None；32-token 只属于
  LoCoMo；
- 可评 answer 指标：LongMemEval judge（付费）、token-F1、normalized EM、substring EM；
- retrieval Recall 与 rank 壳层仍运行资格判断，但 LightMem 本格得到 N/A，不落伪数值；
- stable ranking 仍 pending；framework observation depth=10 也不能冒充官方 k=30/50。

### 4.7 为什么已允许进入 B11 smoke

current v6 的零 API preflight 已完成：

- 六类 role 形状走 production adapter → event stream → TurnPair → LightMem ingest → final flush；
- payload 检查 content、role、speaker、time、lineage、placeholder marker 与 force flags；
- 私有 `answer/answer_session_ids/has_answer` 强反例全链零泄漏；
- TOML→强类型 config→backend 对表为 hybrid/online-soft/preserve-none/MiniLM-384/top-60；
- evaluator 对 N/A 产 `score=None/status=n/a`，不报错、不回落旧 run-level 字段；
- 架构师独立定向复跑 `219 passed, 1 warning`。

registered smoke 默认：1 conversation × 1 round × 1 question。它可以截断 history，因为目标只是
验证 pipeline；正式 full 仍必须使用完整 haystack。六类异常已经离线走过 production path，
无需为了“再看一次异常”付费指定完整异常 qid；当前 CLI 也不支持任意 qid 直选。

### 4.8 LongMemEval 尚未关闭的门

1. latest-v6 真实单/双 worker B11 尚未执行；
2. smoke 不估效果，也不用 pair/add_memory 数估 API 成本；首个完整成本 pilot 必须读真实
   API-call/token/wall-time/efficiency artifact；
3. turn Recall/rank 因 pair-source 非 child-exact 保持 N/A；
4. stable ranking pending，top-k=10 不覆盖官方 k30/50；
5. unified hybrid 不是作者 `user_only` reproduction；`author_longmemeval` section/完整 builder
   留到作者校准门；
6. method-derived time 只能作 order tie-break；效果报告必须同时保留 source session time 说明；
7. source/config/adapter、pair bridge、placeholder marker、timestamp helper 或 RetrievalEvidence
   契约任一变化，本格重新降级到离线预检。

底层证据：

- [LongMemEval 输入异形与时间审计](lightmem-longmemeval-input-time-audit.md)
- [latest-main 六类输入与 B11 readiness 预检](lightmem-longmemeval-latest-main-preflight.md)
- [待执行的单/双 worker B11 命令包](lightmem-longmemeval-b11-command-pack.md)
- [LongMemEval dataset 稳定结构卡](../../../../../../survey/datasets/longmemeval.md)
- [LongMemEval workflow 稳定卡](../../../../../../survey/workflows/longmemeval.md)

---

## 5. 后续三格如何使用本页

MemBench、BEAM、HaluMem 到站时，不复制 LoCoMo/LME 的处理逻辑。每格必须重新回答同一组问题：

1. benchmark 的自然原子和真实异常是什么；
2. canonical adapter 是否保留所有 public facts、id、role、time/place/image；
3. LightMem 的 pair/session bridge 最终实际发送了什么；
4. placeholder、缺时间、同 role、噪声等变换是否引入新事实或丢事实；
5. online-soft build、flush、retrieve/readout 是否与主 profile 一致；
6. private gold 是否全链不可达；
7. 每个 metric 是 valid、N/A 还是 pending，理由是否来自 runtime evidence；
8. 离线门、真实单 worker、真实多 worker、成本/效果门分别到哪一层；
9. 什么变化会让本格旧判词失效。

只有对应章节完成并经过架构师强验收，状态图才能从
`PENDING_GRID_RECERTIFICATION` 升级。旧五格 smoke 可以作导航，不能自动替后续章节盖章。

## 6. 本 dossier 的失效触发器

以下任一项变化，相关格子先降级、后复证：

- benchmark source hash、schema、canonical id/role/time/image 映射；
- LightMem adapter version、consume granularity、placeholder marker 或 pair 聚合规则；
- `messages_use`、lifecycle、embedding、extract/segment/retrieve 配置；
- caption renderer、timestamp helper、offline consolidation 行为；
- RetrievalEvidence、Gold Evidence Group、metric eligibility 或 smoke policy；
- answer builder/decoding、worker isolation、resume manifest identity；
- 新真实 run 与本页“实际 payload/能力”描述冲突。

本页的价值不在于永久保持绿色，而在于让任何新反证都能迅速指出：**哪一格、哪一层、哪条
承诺需要重新打开。**

## 7. 本次生成与 current-main 复核

本页于 2026-07-18 基于 main `480ff8c` 与已强验收底层 note 汇编。为防止“旧 note 摘要正确、
current code 已漂移”，架构师用 dummy key + 不可达本机 base URL 合并复跑 LoCoMo/LME 承重集：

```text
tests/test_image_text.py
tests/test_locomo_conversation_adapter.py
tests/test_locomo_retrieval_recall.py
tests/test_lightmem_adapter.py
tests/test_longmemeval_conversation_adapter.py
tests/test_longmemeval_registered_prediction.py
tests/test_longmemeval_retrieval_recall.py
tests/test_longmemeval_retrieval_rank.py

272 passed, 1 warning in 80.79s
```

唯一 warning 是 vendored LightMem 的既有 Pydantic v2 class-config 弃用提示。测试未调用真实 API；
文档标准门另行通过。该数字只证明 current-main 契约仍与本页一致，不替代 LoCoMo 已有真实
smoke，也不冒充 LongMemEval 尚待执行的真实 B11。
