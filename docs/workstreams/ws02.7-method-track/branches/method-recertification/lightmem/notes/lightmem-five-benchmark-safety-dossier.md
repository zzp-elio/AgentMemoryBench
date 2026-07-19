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
| LightMem × LoCoMo | `REAL_SMOKE_PASSED` | current-v7 3-round 单/双 worker 已实跑，readout、embedding observation、caption lineage、metric 与隔离验收通过 | 不是 full、效果、成本、resume 或 stable-ranking 认证 |
| LightMem × LongMemEval | `REAL_SMOKE_PASSED` | current-v7 单/双 worker 已实跑，完整 ISO readout、zero-hit、embedding observation、N/A summary 与隔离验收通过 | 不代表 full、效果、成本校准或 turn-level retrieval metric 有资格 |
| LightMem × MemBench | `REAL_SMOKE_PASSED` + `100K_SENTINEL_REFILL_PENDING` | current-v7 `0_10k` 四源单/双 worker 已实跑且不触达 forced-flush 输出改变；旧 100k 哨兵的 ThirdHigh 确定漏过 automatic step 1，须在新 source identity 下最小补跑 | 不是 100k full、效果、成本、resume 或 stable-ranking 认证 |
| LightMem × BEAM | `REAL_SMOKE_PASSED` | current-v7 100K W2 + 10M W1 已实跑；pair lineage、ISO readout、prediction efficiency、Recall N/A、rubric score、2+1 条 judge observation 与隔离通过 | 不是 full、效果、成本、resume 或 stable-ranking 认证 |
| LightMem × HaluMem | `REAL_SMOKE_PASSED` | forced-flush 新 identity 的 Medium W1 已实跑；四份 session report、local Qdrant、online-soft LTM、三类官方 judge、memory-type、离线答案指标与全部效率观测通过 | 不是 Long/full、效果、成本、resume 或 turn-level retrieval metric 认证；operation-level 仅支持 W1 |

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
| 运行身份 | adapter `conversation-qa-v7` + concrete `consume_granularity` + protocol/manifest identity | readout/观测/caption/role/lifecycle/投递粒度变化会阻止旧 store 被误 resume |

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

本格 current-v7“已真实跑通”建立在四层证据上：

1. source-locked LoCoMo 全量异常账；
2. canonical Turn → LightMem payload 的离线强反例，含 caption v6；
3. v6 单 worker + 双 worker 的完整历史验货；
4. current-v7 单/双 worker 对 product readout、逐题 evidence、embedding observation、caption
   lineage、summary v2 与物理 state 的受影响门复验。

它不是“因为测试没报错”，也不是“因为作者自己跑过 LoCoMo”。v7 曾因改变所有格共用的
public readout 与 embedding observation 而主动重开；2026-07-19 的四-run 受影响门已经把它
重新关闭。完整命令、原验货脚本的过强断言与 R1 见
[v7 受影响格 B11 命令包](lightmem-v7-readout-observability-b11-command-pack.md)。

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
| `lm-locomo-v7-r3q1-w1` | 1 conversation × 3 rounds × 1 question × 1 worker | current product ISO readout、build/retrieval embedding observation、caption lineage |
| `lm-locomo-v7-r3q1-c2-w2` | 2 conversations × 3 rounds × 1 question × 2 workers | current-v7 双 worker state、summary v2、逐题 metadata/evidence 单事实源 |

这些 run 均检查 checkpoint、prediction/prompt/private-label 行数、隐私扫描、formatted memory、
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
- [current-v7 受影响门复验命令包](lightmem-v7-readout-observability-b11-command-pack.md)

---

## 4. LightMem × LongMemEval

### 4.1 当前结论

```text
REAL_SMOKE_PASSED
```

latest v6 的离线门与真实 cropped B11 已经证明主接线；v7 零 API 修复门又证明：

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

六类真实 role 形状均无丢失、重复、跨 session 配对或 role 猜测；W1/W2 也完成 prediction、
六项 evaluate 与 worker 隔离。架构师开箱发现的公共 readout 降精度、embedding observation
缺失、逐题 metadata 粒度冲突和全 N/A summary 误表示已经完成代码修复与强验收；旧 v6
artifact 也已零 API 重评出正确 summary。2026-07-19 的 current-v7 W1/W2 已进一步用真实
artifact 证明 readout、observation 与 summary 修复，因此本格恢复为 `REAL_SMOKE_PASSED`。

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

### 4.7 B11 实跑证明了什么

current v6 的零 API preflight 已完成：

- 六类 role 形状走 production adapter → event stream → TurnPair → LightMem ingest → final flush；
- payload 检查 content、role、speaker、time、lineage、placeholder marker 与 force flags；
- 私有 `answer/answer_session_ids/has_answer` 强反例全链零泄漏；
- TOML→强类型 config→backend 对表为 hybrid/online-soft/preserve-none/MiniLM-384/top-60；
- evaluator 对 N/A 产 `score=None/status=n/a`，不报错、不回落旧 run-level 字段；
- 架构师独立定向复跑 `219 passed, 1 warning`。

随后真实执行 W1=`1 conversation × 1 round × 1 question × 1 worker` 与 W2=`2 conversations ×
1 round × 1 question × 2 workers`。机器验货均 PASS，证明 registered 默认/覆盖规模、artifact
数量、compact judge、逐题 N/A 与 worker state 隔离可用。它仍只是接线 smoke；正式 full 必须
使用完整 haystack，六类异常则由前置 production-path 探针覆盖。

v7 修复后又以新 run id 执行同样的 W1/W2。开箱结果补上了旧 v6 缺失的受影响证据：W1 是
合法 zero-hit/0 LTM，只有 retrieval embedding；W2 的第二个 conversation 落库 2 条 memory，
恰有 2 次 insert build embedding，并命中保留完整 ISO timestamp 的 product readout。两组
Recall/rank summary 都按全部问题计数并保持 `mean=null/status=n/a`，metadata 与 v1 evidence
均为 `none`。原命令包曾错误要求每个 conversation 都有 build embedding；R1 已改成按实际
持久化 entry 约束调用，不再把“没发生的调用”当观测缺失。

### 4.8 LongMemEval 仍然诚实保留的边界

1. v7 受影响门只由本次新 artifact 关闭；v6 不得 resume 或冒充修复后证据；
2. build embedding 资格按实际调用判断：每题必须有 retrieval observation；有持久化 LTM entry
   的 conversation 必须覆盖相应 insert embedding；0 entry 可以合法 0 build embedding；
3. smoke 不估效果，也不用 pair/add_memory 数估 API 成本；首个完整成本 pilot 必须读真实
   API-call/token/wall-time/efficiency artifact；
4. turn Recall/rank 因 pair-source 非 child-exact 保持 N/A；
5. stable ranking pending，top-k=10 不覆盖官方 k30/50；
6. unified hybrid 不是作者 `user_only` reproduction；`author_longmemeval` section/完整 builder
   留到作者校准门；
7. method-derived time 只能作 order tie-break；效果报告必须同时保留 source session time 说明；
8. source/config/adapter、pair bridge、placeholder marker、timestamp helper 或 RetrievalEvidence
   契约任一变化，本格重新降级到离线预检。

底层证据：

- [LongMemEval 输入异形与时间审计](lightmem-longmemeval-input-time-audit.md)
- [latest-main 六类输入与 B11 readiness 预检](lightmem-longmemeval-latest-main-preflight.md)
- [已执行并含开箱判词的单/双 worker B11 命令包](lightmem-longmemeval-b11-command-pack.md)
- [current-v7 受影响门复验命令包](lightmem-v7-readout-observability-b11-command-pack.md)
- [LongMemEval dataset 稳定结构卡](../../../../../../survey/datasets/longmemeval.md)
- [LongMemEval workflow 稳定卡](../../../../../../survey/workflows/longmemeval.md)

---

## 5. LightMem × MemBench：current-v7 `REAL_SMOKE_PASSED`

### 5.1 benchmark 原子与全量异常账

source-locked 8 个正式文件共有 4,260 trajectories、452,245 source steps 和
767,075 canonical turns。FirstAgent 的一个 dict step 是一个真实 user/assistant pair，
canonical 层展开为两个 child，private gold 仍以 any-of group 只计一个官方 step；
ThirdAgent 的 string step 只有一个 user child，连续 user 不得彼此配对。

经架构师独立重算的稳定异常包括：100k 有 258,000/307,738 source steps 没有
place/time 尾注；8 文件有 39 处相邻带时 step 时钟倒序；2 题 target 越界、1 题
target 为空。详细位置、分布、OpenCode 旧计数勘误和处置见
[`survey/异常情况/membench.md`](../../../../../../survey/异常情况/membench.md)。

### 5.2 canonical → LightMem 真实投递

外部预检首轮揭示 registered path 误把 MemBench 配为 `turn`：helper 直测虽然展示
pair 语义，生产 runner 却把 FirstAgent 一个 source step 拆成两次 `add_memory()`。这是
公开投递契约 bug，不是“需先付费证明 STM 可以容忍它”的未知项。

R1 现用注册级单一 resolver 同时驱动 factory 与 manifest：LightMem × MemBench =
`pair`。生产事件流强反例已证明：

- FirstAgent 一 source step 只形成一个 `TurnPair`/一次 `add_memory()`，同批有两个
  真实 role 和两个 child id，零 placeholder；
- ThirdAgent 每个 singleton 各自形成单边 pair，LightMem 只补 structural assistant，
  连续 user 不互配、lineage 不串；
- concrete `consume_granularity` 已进入 strict manifest/resume identity；旧缺字段、
  `turn↔pair` 均 mismatch，不通过 bump adapter v7 连坐其他 benchmark。

实现与生产路径证据见
[`lightmem-membench-pair-r1-implementation.md`](lightmem-membench-pair-r1-implementation.md)；
首轮审计的有效 census 与 R1 勘误链见
[`lightmem-membench-anomaly-coverage-preflight.md`](lightmem-membench-anomaly-coverage-preflight.md)。

### 5.3 content、time 与 question time

MemBench 每条消息尾部的 place/time 是 source content 的一部分；送入 LightMem 时不删除、
不重写，同时把该 child 自身解析出的 `turn_time` 写入 typed `time_stamp`。
100k no-time noise 的 content 原样保留，`time_stamp=None`；不从兄弟 turn、相邻消息、
wall clock 或 QA 时间回填。39 处时钟倒序保留 source list 顺序和各自时间，不排序或修钟。

`QA.time` 映射为 `Question.question_time`，只用于官方 answer builder 的
`Question: (current time is {time}) ...`；它不进 history content/timestamp。这个单向边界已由
official-template byte parity 与 registered artifact 强反例共同锁定。

### 5.4 metric、隐私与尚未承诺的事

target-step gold 只在 evaluator-private `GoldEvidenceGroup` 中可见，不可达 method/build/
answer prompt。FirstAgent 的 pair-step 以两个 canonical child any-of 命中一次；2 个 OOB
group 保留在分母且恒 miss，1 个 empty-target 题的 retrieval metric 记 N/A。LightMem
online-soft 的 current semantic lineage 可用时，MemBench Recall 按 v1 逐题资格计分；
stable ranking 仍不由本章臆测宣布。

四层离线门先把本格推进到 `READY_FOR_B11_SMOKE`；随后 current-v7 新 pair identity 已用
真实 W1/W2 跑过，结果见下节。它仍不承诺 100k、full、效果、成本、resume 或 stable ranking。

### 5.5 current-v7 真实 B11

两个 `0_10k` run 都按默认四源各取一条：W1/W2 各 4 conversations × 1 round × 1 question，
predict workers 分别为 1/2。架构师开箱确认：

- manifest 为 `conversation-qa-v7`、`consume_granularity=pair`、hybrid/online-soft/
  preserve-none；4/4 conversation 与 question 全部 Completed；
- 25 个 product readout item 全部保留 ISO timestamp；8 道 query 的 retrieval embedding 全齐，
  25 条 LTM 与 25 次 build embedding 对齐；
- 持久化 payload 实见 9 条 FirstAgent 双 child lineage 与 16 条 ThirdAgent singleton lineage；
  W2 的 FirstHigh/ThirdHigh 只在 worker 0，FirstLow/ThirdLow 只在 worker 1；
- choice/source accuracy 两轮均为 0.5，Recall 均为 1/6、四题全部 valid/turn；分数只证明 artifact
  可算，不是效果结论；
- W2 一条 invalid choice 来自被裁到 step 1 的 smoke 无法回答 target step 119，模型拒答后 parser
  正确记 0，不是 prompt/并发失败。

首版验货器用完整 conversation id 在被截为 64 字符的 Qdrant 可读目录前缀中做子串搜索，因
FirstHigh 尾部 `-0` 被合法截断而误报。R1 改用 production storage-safe helper 生成完整
name+hash 后，同一批 run 全绿，无需重跑 API。原始输出、修正理由与 artifact 明细见
[`lightmem-membench-b11-command-pack.md`](lightmem-membench-b11-command-pack.md) §7。
因此本格升为 `REAL_SMOKE_PASSED`。

### 5.6 100k 补充哨兵被新 reachability 证据局部降级

旧 FirstHigh+ThirdHigh 哨兵曾按当时 source identity 合法完成，但 forced-flush R1 后的 exact-smoke
零 API probe 证明：ThirdHigh 两批压缩为 438/361 tokens，final add 确定同时产生 automatic step 1
与 forced step 2；旧实现只把 step 2 送进 STM。因此这不推翻 `0_10k` W1/W2 主 B11，却推翻旧
100k 哨兵对“完整 retained history 进入 extraction”的证明。当前只补跑同一 100k W1 哨兵，
不重烧其余四格；完成前本格附加状态=`100K_SENTINEL_REFILL_PENDING`。证据见
[forced-flush reachability](lightmem-front-four-forced-flush-reachability.md) 与
[100k 命令包 R4](lightmem-membench-100k-missing-time-sentinel-command-pack.md#7-r4-forced-flush-reachability-勘误)。

---

## 6. LightMem × BEAM / HaluMem current-v7

两格均复用 frozen benchmark 稳定层，不重复 census；只验证 LightMem/current runner 的差量。
每格仍需回答同一组问题：

1. benchmark 的自然原子和真实异常是什么；
2. canonical adapter 是否保留所有 public facts、id、role、time/place/image；
3. LightMem 的 pair/session bridge 最终实际发送了什么；
4. placeholder、缺时间、同 role、噪声等变换是否引入新事实或丢事实；
5. online-soft build、flush、retrieve/readout 是否与主 profile 一致；
6. private gold 是否全链不可达；
7. 每个 metric 是 valid、N/A 还是 pending，理由是否来自 runtime evidence；
8. 离线门、真实单 worker、真实多 worker、成本/效果门分别到哪一层；
9. 什么变化会让本格旧判词失效。

旧五格 smoke 可以作导航，不能自动替当前格盖章。

MemBench 这套“全量 census → deterministic test → registered probe → 真实 B11”分层方法
已成为后续格子的复用模板；但 BEAM/HaluMem 的自然原子和 metric 资格不同，不得复制其
pair 或 gold 结论。

从 BEAM 起执行“稳定层摊销”：先定点核 source lock 未漂移，再只验 LightMem 的 role/pair/time/
state/readout 差量。BEAM 已 frozen 的 raw-id 歧义、10m plan 展开、官方 prompt/judge 与 gold
group 不因换 method 重做全量调查；只有 source lock、shared contract 或新一手反证变化才重开。

### 6.1 BEAM：core 与 metric-side 观测均已通过

- 标准 100K 数据是严格 user→assistant；10M 有两处 dangling user、一处后续 answer 内容错槽、
  一个全缺时 session 与跨 session anchor 回退。canonical 层全部 preserve，不猜修 raw 内容。
- LightMem registration 已改为 `consume_granularity=pair`：正常 pair 一次投递；dangling user 只补
  assistant placeholder，不跨 session 借下一条回复。`messages_use=hybrid`，source time 只读本
  turn/session，缺失保持 None。
- BEAM gold 是 single-message / private group，而 LightMem extracted lineage 是 pair，因此
  `semantic_provenance=n_a / beam_gold_is_single_message / granularity=none`；stable ranking
  pending，Recall summary 正确为 N/A，不为了填表硬算。
- 真实 100K W2 与 10M W1 分别得到 1+1 与 3 条 LTM；每条 lineage 恰为当前 pair，两组共 5 次
  build embedding、3 次 retrieval embedding，100K 两 conversation 分居 worker0/worker1。
- R0 验货器误要求 answer-builder `metadata` 复制顶层 `retrieval_evidence`，对好产物报 KeyError；
  R1 只删错误断言，既有 run 全绿，production/API 均无需重跑。
- 共享 `_run_artifact_level_evaluation()` 的 metric-side 观测断链已由 `174bd46` 修复；既有两个
  run 只补跑 2+1 道 rubric judge，三条 scope、model inventory 与 `api_usage` token 机器门全绿，
  未重建 LightMem。

底层证据：

- [BEAM current-v7 命令、R1 输出与开箱](lightmem-beam-current-v7-b11-command-pack.md)
- [共享 evaluator 可观测性支线](../../../evaluator-observability/README.md)

### 6.2 HaluMem：forced-flush 新 identity 的真实 Medium B11 已通过

- Medium/Long hash 与 frozen lock 逐字一致，因此继承：真实数据严格 user→assistant、turn/session
  时间齐全；generated QA sessions 只 ingest；memory-point evidence 没有 turn id，retrieval
  Recall/NDCG N/A。
- registration 使用 `consume_granularity=session` 与 `session_memory_report=True`。每 session 恰
  一次 `add_memory(force_segment=True, force_extract=True)`，hybrid 同时保留 user/assistant；
  capture 只旁听本 session 成功 insert、报告增量非累计，空抽取如实记 empty。
- 主 profile 是 online-soft，HaluMem 不跑 LoCoMo-only 全库 consolidation。update probe 与 QA
  retrieve 均固定 `filters=None`；update probe 只把公开 memory content 作 query，不把 gold
  answer/evidence/original memories 送给 method。
- current-v7 readout 为完整 ISO product 格式；None time 不写字面 None，zero-hit 用明确 sentinel。
  HaluMem RetrievalEvidence 恒 `n_a / halumem_no_turn_qrel / none`。
- evaluator 固定顺序是 extraction → update → qa（三段 judge）→ memory-type（离线依赖前两份
  score），另有 F1/normalized EM/substring EM；operation-level runner 固定 workers=1。
- 论文主表细项没有被压成三个 overall：extraction 六列 R/Weighted R/Target P/Acc./FMR/F1、
  update C/H/O（另含 Other）与 QA overall C/H/O 均落盘。QA 又按六种 `question_type` 完整分报
  C/H/O 的 all/valid 双分母；memory-type 按 Event/Persona/Relationship 复刻官方共享分母，
  不是只留 overall。细项审计见
  [HaluMem metric breakdown R1](lightmem-halumem-metric-breakdown-r1.md)。
- 旧 note-only READY 被真实 sensory/STM 反例推翻：forced tail 曾按 boundary count 清 buffer，
  automatic prefix 也会被 tail 覆盖。`8879af9` 只修 bookkeeping 与 source identity，不改阈值、
  prompt、分段、抽取或 LTM 算法；real-vendored 双 session 强反例证明 report 局部、暂存态清空、
  早期非空 LTM 保留。
- 用户随后完成固定 Medium `1 conversation / 4 sessions × 2 turns / 1 QA / workers=1`。真实
  report=`[0,0,0,2]`，Qdrant 恰两条并只带 `s4:t1/s4:t2` lineage，7 个 update probe 也只读
  s4。前三 session 的 zero extraction 被如实保留，没有为了造非空 memory 换样本或重跑。
- judge preview 与真实 observation 均为 extraction/update/QA=`7/7/1`；scope、`gpt-4o-mini`
  inventory、`api_usage` token 精确。prediction 又实见 4 memory LLM、2 build+8 retrieval
  embedding 与 1 answer LLM；memory-type/F1/EM 不造空观测文件。extraction/update 低分是效果，
  QA semantic=1 与 lexical=0 是公式差异，均不改变接入正确性。
- 本次前三 session 都抽取为空，故“早期非空 LTM 经后续 session 保留”仍由 real-vendored 双
  session 强反例承重，不越权写成真实 crop 亲自证明。最终判词=`REAL_SMOKE_PASSED`；Recall/
  NDCG 继续 N/A、stable ranking pending，不外推 Long/full/效果/成本/resume。

底层证据：

- [HaluMem current-v7 source-locked 预检](lightmem-halumem-current-v7-preflight.md)
- [HaluMem forced-flush B11 命令与开箱](lightmem-halumem-current-v7-b11-command-pack.md)
- [HaluMem 论文细项、question-type 与 memory-type 对表](lightmem-halumem-metric-breakdown-r1.md)
- [共享 evaluator 可观测性支线](../../../evaluator-observability/README.md)

## 7. 本 dossier 的失效触发器

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

## 8. 本次生成与 current-main 复核

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
smoke；末句当时的 LongMemEval B11 待执行状态已由下方 current-v7 记录 supersede。

2026-07-19 追加：LoCoMo/LongMemEval current-v7 真实单/双 worker 已由用户执行且经
架构师开箱，两格均为 `REAL_SMOKE_PASSED`。MemBench 又经 source-lock census、
production event/pair 强反例、registered manifest/runtime 交叉校验与 evaluator-private 契约复核，
关闭离线四层门；首次主树 full 抓到的 9 个旧 fake fixture 漂移以生产零改方式
修复。最终主树门：

```text
1579 passed, 3 deselected, 2 warnings, 29 subtests passed in 144.49s
compileall: exit 0
```

该离线门随后已由 current-v7 真实 W1/W2 补齐；修正版机器验货与架构师开箱通过，MemBench
现为 `REAL_SMOKE_PASSED`。仍不得外推 100k/full/效果/成本/resume。
