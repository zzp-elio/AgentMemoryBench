# LoCoMo Benchmark 调研卡片

更新日期：2026-07-10

## 1. 一句话结论

LoCoMo Phase 1 是标准的长期 `conversation → session → turn → conversation-level QA`
任务：框架必须按 session 时间顺序向 memory method 注入两个 speaker 的全部公开 turn，
完整 conversation 构建结束后再逐题 retrieve，由 benchmark-owned unified reader 生成短
答案，并用官方 QA F1（以及 provider 有 turn provenance 时的官方 retrieval recall）评测。

本卡只冻结 LoCoMo QA。论文另外定义 event summarization 与 multimodal dialogue
generation，但官方 README 对这两条执行代码仍标为 `Coming soon!`，不进 Phase 1。

## 2. Dataset 数据结构

### 2.1 官方资产与本地一致性

- 官方仓库：`https://github.com/snap-research/locomo`，HEAD
  `3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376`（2024-08-12）。
- 本地官方快照：`third_party/benchmarks/locomo-main/`；关键 README、QA runner、
  scorer、prompt 与 dataset 已逐文件锁定；该目录没有独立 `.git`，不能在目录内用
  `git rev-parse` 推断官方 commit。
- 官方快照许可证：Creative Commons Attribution-NonCommercial 4.0 International
  （CC BY-NC 4.0，见 `LICENSE.txt`）。
- canonical dataset：`data/locomo/locomo10.json`，SHA-256
  `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`；与官方
  `data/locomo10.json` 字节一致。
- 本地论文副本：
  `third_party/benchmarks/locomo-main/Maharana 等 - 2024 - Evaluating Very Long-Term Conversational Memory of LLM Agents.pdf`，
  SHA-256 `218188e1d66a553afe324491e3e5e5d0af107196c9ff32c65bb3640ebf638539`。
  官方 README 链接的仓库路径是 `static/paper/locomo.pdf`，但当前本地快照没有这个路径；
  因此只锁定本地副本身份，不声称两份 PDF 字节一致。

### 2.2 真实数据剖面

本地全量扫描结果：

| 粒度/字段 | 实测 |
| --- | ---: |
| conversation | 10 |
| 实际 `session_<n>` 列表 | 272 |
| turn | 5,882 |
| QA | 1,986 |
| 有 URL 的图片 turn | 910 |
| 有 `blip_caption` 的 turn | 1,226 |
| 奇数 turn session | 140 / 272 |
| 缺失 session 时间的实际 session | 0 |
| 带 turn 级时间字段的 turn | 0 / 5,882 |
| 连续相同 speaker 的相邻 turn | 0 |

每个 top-level sample 包含 `sample_id`、`conversation`、`qa`、`observation`、
`session_summary`、`event_summary`。Phase 1 QA 的公开输入只来自 `conversation` 和
`qa.question/category`；其他生成摘要和 event gold 不交给 method。

`conversation` 含 `speaker_a`、`speaker_b`、实际 `session_<n>` 列表及其
`session_<n>_date_time`。每个 turn 必有 `speaker`、`dia_id`、`text`，可选
`img_url`、`blip_caption`、`query`、`re-download`。`dia_id` 在 conversation 内唯一，
也是 QA evidence 的引用键。

异常形态：`conv-26` 有 `session_20_date_time` 至 `session_35_date_time`，但没有对应
`session_20` 至 `session_35` 列表，共 16 个 date-only key。官方代码按实际 session 列表
取 session numbers，因此忽略这些孤立日期；框架必须显式记录该形态，不能凭 date key
构造空 session。

QA category 实测映射：

| category | 语义 | 数量 |
| --- | --- | ---: |
| 4 | single-hop | 841 |
| 1 | multi-hop | 282 |
| 2 | temporal | 321 |
| 3 | open-domain / commonsense | 96 |
| 5 | adversarial / unanswerable | 446 |

`qa.answer` 与 `qa.evidence` 是 evaluator-only 私有字段。evidence 为 `dia_id` 列表；
1,986 题全部是 list，其中 4 题为空列表。当前 Phase 1 既有决策跳过 category 5，故
正式 QA 分母为 1,540，而非官方五类总计 1,986。

## 3. Evaluation 流程

官方 QA 流程（`task_eval/evaluate_qa.py:67-113`）：

1. 按 sample/conversation 读取 conversation 与 QA；
2. 非 RAG 把尽可能多的带日期 conversation 放入 reader context；RAG 则从 dialog、
   observation 或 session summary 数据库按 question 检索 top-k；
3. 对完整 conversation 后挂载的 QA 生成 short answer；不是每 session/turn 后提问；
4. 对每题计算 F1；RAG 还用 retrieved context ids 与 evidence `dia_id` 计算 recall；
5. 按 category `[4, 1, 2, 3, 5]` 与 overall 聚合。

Phase 1 框架映射：

```text
sample_id -> isolation/conversation_id
session_<n> -> Session(session_id, session_time)
turn -> TurnEvent(speaker, content, inherited session timestamp, dia_id)
all sessions ingest + end_conversation
qa.question -> RetrievalQuery(purpose="qa")
RetrievalResult.formatted_memory -> LoCoMo unified reader -> short answer
answer + private gold -> F1 / auxiliary judge
retrieved source_turn_ids + private evidence -> conditional recall
```

图片口径有论文一手依据：论文 §5 与 Appendix C 明确说明 QA/event summarization 用
BLIP caption 替代图片，只有 multimodal dialogue generation 直接使用图片。官方 RAG
`gpt_utils.py:92-95` 也把 `blip_caption` 拼进 dialog 文本。本框架因此不下载 URL，不调
视觉模型；事件流把 caption 拼为 `text (image description: caption)`。只有 caption、
没有 URL 的 316 个 turn 也必须保留 caption。

隔离采用 v3 并置持久化：不同 conversation 使用不同 isolation key，session 之间不
reset，conversation 结束后状态可保留供审计。旧 workflow 文档中“每 conversation 后
reset”的说法不再是现行协议。

## 4. Metric 计算方式

### 4.1 官方 QA F1

官方 `task_eval/evaluation.py:75-145,189-241`：

- normalize：去逗号、转小写、去标点、去 `a/an/the/and`、压缩空白；
- token 做 Porter stemming；
- category 2/3/4 使用 token-overlap F1；category 3 先截掉 gold 分号后的解释；
- category 1 把 prediction/gold 按逗号拆成子答案，对每个 gold 取最佳 candidate F1，
  再取均值；
- category 5 检查预测是否包含 `no information available` 或 `not mentioned`。

当前 Phase 1 跳过 category 5，因此 official-profile F1 只聚合 1/2/3/4 共 1,540 题，
并必须在 summary 标明该分母差异。

### 4.2 官方 retrieval recall

官方 `evaluation.py:228-237` 对 evidence 非空题计算：

`命中的 evidence dia_id 数 / evidence dia_id 总数`。

若使用 session summary context，官方把 retrieved session id 向上匹配 evidence 所在
session；本框架 Phase 1 的 method 若只声明 session provenance，可计算 session-level
recall，但不得伪装成 turn-level recall。provider 声明 provenance=`none` 时该 metric
必须写 N/A，不计 0 分。

框架 frozen-v1 evaluator 名为 `locomo-recall`，只读 saved answer-prompt、public-question
与 private-label artifacts：三者 question ID 必须完全一致；每题必须保存实际
`retrieval_query_top_k`。声明 turn/session provenance 却缺失或给出空
`source_turn_ids` 时 fail-fast；历史 run 未声明 provenance 或 provider 明确声明 `none`
时输出结构化 N/A，不把不可评估伪装成 0 分。

官方实现对 evidence 为空的题直接记 recall=1，而不是从分母剔除；release 中有 4 道
此类 category-3 题。兼容官方的 overall 必须保留该行为，同时另报 non-empty-evidence
子集均值和空 evidence 数量，避免把这一实现细节误读成真实检索命中。

### 4.3 BLEU 与 LLM judge 的定位

BLEU-1 不是 LoCoMo QA 指标。论文中的 BLEU/ROUGE/FactScore 分别出现在 multimodal
dialogue generation 或 event summarization/NLG 设置；QA 表 2/3 只报告 answer F1 与
RAG recall。因此 Phase 1 LoCoMo QA 不新增 BLEU-1，避免把其他 task family 的 metric
混入 QA。

官方 QA 仓库没有 LLM-as-judge。项目现有 `locomo-judge` 参考 LightMem 的 LoCoMo
评测 prompt，属于 method-independent 的框架辅助指标，不得标成 LoCoMo 官方主指标。

## 5. Answer LLM / Judge LLM 配置和 Prompt

### 5.1 官方 answer prompt

`task_eval/gpt_utils.py:25-29` 要求：根据上方 context，用 short phrase 回答，并尽量使用
context 原词。category 2 在 `gpt_utils.py:243-244` 给 question 追加日期提示。RAG 单题
模式把 retrieved context 直接接在该 QA prompt 前。

官方 GPT 单题调用（`gpt_utils.py:283-289`、`global_methods.py:92-127`）：

- message role：GPT-4 分支为 `user`；
- temperature：0；
- max tokens：32；
- top-p：代码未显式传，论文 Appendix C.2 说明 top-p=1；
- RAG batch size：1。

本项目模型名继续统一 `gpt-4o-mini`，但上述 benchmark-owned answer 参数必须在
LoCoMo 上跨 method 完全一致。

### 5.2 Judge prompt

LoCoMo 官方 QA 无 judge prompt。现有框架 judge 来源是
`third_party/methods/LightMem/experiments/locomo/llm_judge.py` 的 accuracy prompt，
按项目 prompt 三级政策只能标记为 `framework_auxiliary_lightmem_reference_v1`。judge
模型仍按项目政策使用 `gpt-4o-mini`、temperature=0，并记录 API usage。

## 6. Method Adapter 接口需求

LoCoMo 对 method 的原生需求是 benchmark 中立的 v3 memory-module 形态：

- isolation：一个 `sample_id` 一个隔离空间；
- ingest 顺序：session number 升序、session 内 turn 原顺序；
- per-turn 必需字段：speaker、文本、继承的 session 时间、session id、dia_id；
- 图片：文本方法接收拼好 caption 的 content，不接收 gold/image semantics；
- lifecycle：session 边界保留，所有 session 完成后 `end_conversation`；
- query：完整 conversation ingest 后逐题 retrieve；
- output：非空 `formatted_memory`，可选 `RetrievedItem.source_turn_ids`；
- 私有边界：answer、evidence、event_summary、judge label 永不可达 method。

method 可声明 turn/pair/session/conversation 任一消费粒度，由框架聚合 canonical turn
事件；LoCoMo 的 speaker 是人名而非 `user/assistant`，所以任何 pair 语义必须由 method
原生接口与 adapter 明确处理，不能盲用 user-anchored pair。

Smoke 的 `round` 只是历史预算单位，不升级为 canonical 实体。真实数据 140/272 个
session 是奇数 turn；LoCoMo smoke 的一个 round 精确定义为“按原顺序取当前历史的前两个
turn”，允许 full 数据保留 session 尾部 dangling turn。最小 smoke 为 1 conversation、
1 round、1 public question；问题无需在保留 history 中可回答，成功判据是四步流程与
artifact 完整，不是答案正确。

Resume 分层：

- smoke：禁用 resume；
- formal ingest：conversation 级完成边界，LoCoMo 不要求 turn/session 级 ingest resume；
- conversation 已完成 ingest 后：允许 question-level answer artifact resume，必须复用已
  保存 retrieval，不重复调用状态型 retrieve；
- evaluation：artifact-only，可按已保存 prediction 重跑，不构造 method。

成本下界：每个问题一次 framework answer LLM；启用辅助 judge 时每题再一次 judge LLM；
method 内部 ingest/retrieve 成本由 method 审计决定。官方 recall 为离线计算，不额外调 API。

## 7. 未确认项

1. 本地官方快照不含独立 `.git` 元数据；官方 commit `3eb6f2c...` 与本地关键源码/
   dataset 的逐文件 hash 已记录在 source lock，不能通过父仓库 `git rev-parse` 误认
   来源。本地 bundled PDF 与 README 所链官方仓库路径不是同一可复验本地文件，故只
   分别记录路径，不声称字节一致。
2. 官方代码有旧字段痕迹：`evaluation_stats.py:19` 检查 `img_file`，当前 release 使用
   `img_url`；QA/RAG 主路径则按 `blip_caption` 拼文本。本框架按真实 release 字段与论文
   caption 口径实现，并把该差异记录为官方代码漂移。
3. A4 已把 smoke 改为确定性的第一个 Phase-1 public question，不再用 evidence 选择
   question，也不再用 evidence 派生 method 可见 metadata；
   `smoke_context_truncated` 仅表示公开 history 是否被裁短。
4. turn-level retrieval recall 需要 method 返回 `source_turn_ids`。Benchmark Track 可以
   完成 evaluator 与 probe 验收，但五个真实 method 的支持状态必须等 Method Track 才裁定。
5. category 5 因官方 prompt 把 gold answer 作为二选一内容，Phase 1 继续排除。若未来恢复，
   必须另写 reader-only spec，仍不得让 gold 到达 method。
6. LoCoMo benchmark 侧已于 2026-07-10 达到 `frozen-v1`；冻结证据与已知限制见
   `docs/workstreams/ws02.6-first-smoke-hardening/notes/locomo-frozen-v1.md`。这不代表
   任何真实 method 的 LoCoMo 效果、效率或 provenance 支持已经验收。
