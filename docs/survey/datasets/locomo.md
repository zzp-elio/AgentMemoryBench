# LoCoMo Dataset 现行契约

更新日期：2026-07-10
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
| `text` | `Turn.content` 主体 | 是 | 原始发言 |
| `blip_caption` | `Turn.content` 图片描述 | 是 | 最多拼接一次 |
| `img_url` | image reference metadata | 否（文本 Phase 1） | 不下载、不放进 content |
| `qa.question/category` | `Question` | 是 | category 5 在 loader 阶段排除 |
| `qa.answer/evidence` | `GoldAnswerInfo` | 否 | evaluator-only private labels |
| `event_summary` | 不进入 Phase 1 QA | 否 | 其他 task 的 gold |
| `observation/session_summary` | 不作为默认输入 | 否 | 官方 RAG 的可选数据库，不混入本项目主线 |

每个 raw turn 没有独立时间戳，因此 `turn_time` 使用所属 session 的时间。该继承是数据
映射事实，不是 method-specific 特判。

## 3. 图片字段口径

当前项目没有多模态 method。对文本 method：

```text
content = 原 text + 一次 image-description 标记 + blip_caption
```

- 有 `img_url` 的 turn：910
- 有 `blip_caption` 的 turn：1,226
- caption-only turn：316，也必须保留 caption
- URL 不下载、不进入 `content`；`query` 也不替代 caption

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

## 6. Smoke 数据子集

LoCoMo smoke 只做确定性公共裁剪：第一个 conversation、前两个连续 turns（1 round）、
第一个 Phase-1 public question。问题不要求能由截断 history 答对；选择与 public metadata
都不得读取 evidence。`smoke_context_truncated` 只表示公开 history 是否被裁短。
