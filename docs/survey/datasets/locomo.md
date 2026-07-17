# LoCoMo Dataset 现行契约

更新日期：2026-07-17
状态：`frozen-v1`（Phase 1 QA）

本文只描述当前框架实际使用的数据结构和公私边界。官方流程、prompt、metric 与
method 接口的完整证据见 [LoCoMo Benchmark 调研卡片](../benchmarks/LoCoMo.md)，冻结
验收见
[locomo-frozen-v1.md](../../workstreams/ws02.6-first-smoke-hardening/notes/locomo-frozen-v1.md)。

## 1. 数据源与规模

- canonical file：`data/locomo/locomo10.json`
- SHA-256：`79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`
- 10 conversations、272 个实际 sessions、5,882 turns、1,986 QA
- Phase 1 排除 category 5，因此公开问题与 F1 分母为 1,540

一个 top-level sample 是一整段长期 conversation，不是一道题：

```text
sample
├── sample_id
├── conversation
│   ├── speaker_a / speaker_b
│   ├── session_<n>_date_time
│   └── session_<n>[]
│       └── turn {speaker, dia_id, text, img_url?, blip_caption?, query?}
├── qa[] {question, answer, evidence, category}
├── observation
├── session_summary
└── event_summary
```

QA 挂在完整 sample/conversation 下；不是每个 session 或 turn 后各自带题。

## 2. Canonical 映射

| Raw 字段 | 框架实体/字段 | 可达 method | 说明 |
| --- | --- | :---: | --- |
| `sample_id` | `Conversation.conversation_id` | 是 | conversation 也是隔离空间 |
| `session_<n>` | `Session` | 是 | 只认实际 list key，按数字升序 |
| `session_<n>_date_time` | `Session.session_time` | 是 | session 内所有 turn 继承此时间 |
| `speaker` | `Turn.speaker` | 是 | 原始人名，不伪造 user/assistant |
| `dia_id` | `Turn.turn_id` | 是 | recall provenance 对齐键 |
| `text` | `Turn.content` | 是 | 只保留原始发言 |
| `blip_caption` | `Turn.images[].caption` | 是（经文本 fallback） | canonical 层保留结构，method 注入边界最多渲染一次 |
| `img_url` | image reference metadata | 否（文本 Phase 1） | 不下载、不放进 content |
| `qa.question/category` | `Question` | 是 | category 5 在 loader 阶段排除 |
| `qa.answer/evidence` | `GoldAnswerInfo` | 否 | evaluator-only private labels |
| `event_summary` | 不进入 Phase 1 QA | 否 | 其他 task 的 gold |
| `observation/session_summary` | 不作为默认输入 | 否 | 官方 RAG 的可选数据库，不混入本项目主线 |

每个 raw turn 没有独立时间戳，因此 `turn_time` 使用所属 session 的时间。该继承是数据
映射事实，不是 method-specific 特判。

## 3. 图片字段口径

canonical adapter 不把 caption 提前烤进 `Turn.content`，而是保留原文与结构化
`ImageRef.caption`。当前项目没有多模态 method；文本 method 在注入边界统一渲染：

```text
content = 原 text + " [Sharing image that shows: " + blip_caption + "]"
```

- 有 `img_url` 的 turn：910
- 有 `blip_caption` 的 turn：1,226
- caption-only turn：316，也必须保留 caption
- URL 不下载、不进入 `content`；`query` 只留公开 metadata，不进入 fallback 文本

已抽查 `conv-26/D1:5`（URL + caption）与 `conv-26/D4:4`（caption-only）：都继承
session 时间，caption 只出现一次。

## 4. QA 与私有数据

| Category | 官方代码语义 | 数量 | Phase 1 |
| ---: | --- | ---: | :---: |
| 1 | multi-hop | 282 | 是 |
| 2 | temporal | 321 | 是 |
| 3 | open-domain / commonsense | 96 | 是 |
| 4 | single-hop | 841 | 是 |
| 5 | adversarial / unanswerable | 446 | 否 |

`answer`、`evidence`、`event_summary`、judge label 永不进入 dataset public view、method
ingest、retrieve query、answer prompt metadata 或 method prediction metadata。evidence
只在 artifact-only evaluator 中用于 recall。

## 5. 必须保留的真实异常

- 140/272 个 session 是奇数 turn，不能假设“一个 session 总是完整若干问答 round”。
- `conv-26` 有 16 个 date-only keys（20..35），没有对应 session list；adapter 必须忽略，
  不得生成 phantom sessions。
- 5,882 个 turn 都没有 turn 级时间字段。
- 4 道 category-3 QA 的 evidence 是显式空列表；official-compatible recall 记 1.0，
  同时另报 non-empty-evidence 均值和空 evidence 数。
- 当前 release 用 `img_url`；官方旧统计脚本残留 `img_file`，不能复制该漂移。

另有 **9/2,815 个 raw evidence token 无法精确映射到同 conversation 的 canonical turn**；
9 个全在 Phase 1（Phase 1 共 2,355 个 evidence token）：

| sample | `qa` 零基下标 | raw token | turn view 处置 |
| --- | ---: | --- | --- |
| `conv-26` | 37 | `D8:6; D9:17` | `unmatched` |
| `conv-42` | 58 | `D10:19` | `unmatched`（格式合法但目标 turn 不存在） |
| `conv-42` | 88 | `D` | `unmatched` |
| `conv-43` | 18 | `D:11:26` | `unmatched` |
| `conv-47` | 38 | `D4:36` | `unmatched`（格式合法但目标 turn 不存在） |
| `conv-49` | 31 | `D9:1 D4:4 D4:6` | `unmatched` |
| `conv-49` | 38 | `D22:1 D22:2 D9:10 D9:11` | `unmatched` |
| `conv-49` | 46 | `D21:18 D21:22 D11:15 D11:19` | `unmatched` |
| `conv-50` | 69 | `D30:05` | `unmatched`（实际 id 无前导零） |

框架不把分号/空格内容猜拆成多个 id，也不把 `D30:05` 猜改成 `D30:5`：官方 turn-context
scorer 对 list 元素做 exact match，擅自修复会改变 gold unit 与分母。Gold Evidence Group v1
按首次出现顺序稳定去重后，每个 raw 值保留一个 unit；turn view 的上述 9 个 unit 都是
`unmatched`、永远 miss 但仍在分母；session view 复刻官方 `split(':')[0]` 上卷，只有 `D` 与
`D:11:26` 两个仍 unmatched。

另有一个重复标注：`conv-50/qa[5]` 的 raw evidence 是
`["D4:5", "D4:5", "D5:5"]`。官方 raw scorer 会双重计权 `D4:5`；Gold Evidence Group v1
把同一 utterance 视为一个语义 unit，稳定去重。因此 Phase 1 为 2,355 个 raw token、2,354 个
group unit。这是有意的 framework normalization，不得宣称与官方 raw implementation 分母
逐字节一致。按现行去重 group 口径，turn-level overall recall 即使其它 gold 全命中，理论
上限也是 `0.996134817563389`；报告不得把这个数据上限误判为 method 漏检。

## 6. Smoke 数据子集

LoCoMo smoke 默认只做确定性公共裁剪：第一个 conversation、前两个连续 turns（1 round）、
第一个 Phase-1 public question；CLI 可用 `--rounds N` 显式覆盖该历史预算，不能用
`--turns/--sessions/--sources`。问题不要求能由截断 history 答对；选择与 public metadata 都
不得读取 evidence。`smoke_context_truncated` 只表示公开 history 是否被裁短。
