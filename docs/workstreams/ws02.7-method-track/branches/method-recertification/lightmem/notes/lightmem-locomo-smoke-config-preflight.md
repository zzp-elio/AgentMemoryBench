# LightMem × LoCoMo smoke 配置离线预检

> 日期：2026-07-17；基线：main `be4f390`；范围：零真实 API 的输入、build、
> retrieval/readout 与数据异常预检。结论：五条主链成立，但图片 caption 存在确定性
> 丢失，故 B2/B4 与 B11 在修复前不得关闭。

## 1. 架构裁决

| 问题 | 裁决 | 一手证据 |
|---|---|---|
| unified 主 profile 是否为 hybrid | **是** | `configs/methods/lightmem.toml:18-21,23-41` 显式声明；backend 读取 `config.messages_use`（`lightmem_adapter.py:697-730`） |
| hybrid 是否改变 LoCoMo 的 user-only extraction 输入 | **不改变** | LoCoMo 的 assistant slot 是 marker=True 的空 placeholder；vendored prompt/token 两处都只跳过严格 marker=True（`openai.py:281-316`、`short_term_memory.py:11-26`）；强反例 `test_lightmem_locomo_placeholder_keeps_hybrid_user_only_prompt_and_tokens_equal` 字节/整数严格相等 |
| 双 speaker 是否被误当作真实 user/assistant | **没有** | canonical `Turn.normalized_role=None`，保留原 human name；adapter 仅把 role 当 LightMem 的结构槽位，同时把真实身份写入 `speaker_id/speaker_name`（`locomo.py:_turn_from_raw`、`lightmem_adapter.py:_locomo_pair`） |
| 注入是否为 pair | **backend 是 pair-shaped；framework 消费粒度仍是 turn** | registry 对 LoCoMo 声明 `consume_granularity="turn"`；每个 TurnEvent 经 `_native_turn_batch()` 变成 `[real user, empty assistant]`，每个真实 utterance 单独调用一次 `add_memory()`。不得把这句话简写成“公共协议 pair 粒度” |
| source timestamp 是否进入每条 message | **是** | LoCoMo 无 turn time，`_turn_timestamp()` 按 turn→session 回落并转成 LightMem 格式；同一 pair 两 slot 都写同一 source timestamp（`lightmem_adapter.py:624-656,1907-1965`） |
| 是否执行 LoCoMo offline consolidation | **主 profile 不执行** | `lifecycle_profile="online_soft"`；`end_conversation()` 只 flush 最后一批，只有显式补充 profile 才运行全库 update（`lightmem_adapter.py:954-981`） |
| retrieval 是否为作者 reported combined top-60 | **是，检索深度/模式一致** | 当前 `retrieve_limit=60`，通过同一 HF embedder + Qdrant cosine search 全局取 top-60，之后只为 readout 标 speaker；官方 `search_locomo.py` 默认 `combined` + `total-limit=60` |
| 当前配置是否等于作者 LoCoMo 复现配置 | **不是，也不得这样命名** | 当前是跨五格 unified smoke build；与作者 harness 的 user_only、rate=0.6、extract=0.1、post-build update=0.9 等存在有意差异，见 §4 |
| 是否可以现在跑付费 smoke | **不可以** | 1,226 个 caption turn 当前对 LightMem 丢失；默认 1-round smoke 的 D1:1/D1:2 又没有图片，无法暴露该缺陷 |

## 2. 实际 LoCoMo message 形态

官方 `experiments/locomo/add_locomo.py:104-154,320-337` 对每条 named-speaker
utterance 构造：

```python
[
    {
        "role": "user",
        "content": real_utterance,
        "speaker_id": "speaker_a" | "speaker_b",
        "speaker_name": real_name,
        "time_stamp": session_time,
    },
    {
        "role": "assistant",
        "content": "",
        "speaker_id": same_id,
        "speaker_name": same_name,
        "time_stamp": session_time,
    },
]
```

本框架 `_locomo_pair()` 同形，并额外写公开 lineage：两 slot 的
`external_id/source_external_ids` 都是该真实 turn id；空 assistant 用内部 marker 标识，
不制造 canonical turn，也不进入 extraction prompt/token count。

全量数据离线复算：272 session、5,882 turn；所有 272 个 session timestamp 均可转换，
所有 5,882 个 speaker 都严格映射到声明的 speaker_a/speaker_b，0 重复 turn id、0 空文本。
因此 LoCoMo full 会形成 5,882 个 backend pair batch；默认 1-round smoke 则是两个 canonical
turn、两个相互独立的 pair batch，不是把 Caroline 和 Melanie 合成一对 user/assistant。

## 3. 时间戳的两层含义

1. **dataset source time**：LoCoMo 只有 session timestamp；每个真实 utterance 继承它，
   两个结构 slot 在送入 `add_memory()` 前都携带同一转换值。这是可审计的 benchmark 事实。
2. **method-derived order time**：LightMem `MessageNormalizer(offset_ms=500)` 与后续
   `assign_sequence_numbers_with_timestamps()` 为同一 raw session key 内的 message slot 排序。
   LoCoMo 每个真实 utterance 后有一个 placeholder，所以最终 real-user source slot 通常按
   1,000ms 间隔排列，placeholder 占中间 500ms slot。这与官方空-assistant 喂法一致，只能
   当 tie-break/order time，不能冒充 dataset 提供的 turn timestamp。

`missing_timestamp_policy="preserve_none"` 对 LoCoMo 不产生分叉：本地 272 个真实 session
没有缺时间；该字段只为 MemBench 等格服务。

## 4. 当前 TOML 与作者复现配置

### 4.1 当前 `[smoke]` 实际解析值

- memory manager LLM：`gpt-4o-mini`，backend max_tokens=16,000；framework timeout 60s、
  max retries 8；runner worker=1；
- embedding：本地 `all-MiniLM-L6-v2`，384 维，cosine/Qdrant，CPU；
- LLMLingua-2：本地 multilingual meetingbank 模型，CPU；pre-compress=true，rate=0.7；
- STM=512；topic segmentation=true；entry text summary=true；flat extraction；
- extract threshold=0.5；retrieve limit=60；
- `messages_use="hybrid"`；`lifecycle_profile="online_soft"`；
- `offline_update_score_threshold=0.8` 在 online-soft 路径中不被调用；
- `official_full` 与 smoke 只有 worker 10 vs 1 的运行并发差异。

backend config 里的 `update="offline"` 是 upstream 命名债：它选择抽取结果的
`offline_update(memory_entries)` direct-insert 实现，并不等于 conversation 末尾的全库
`offline_update_all_entries()`；后者受 `lifecycle_profile` 独立 gate，当前 online-soft 不调用。

### 4.2 与作者 LoCoMo harness 的有意分叉

官方脚本/README 是：user_only、rate=0.6、extract=0.1、combined top-60、HF
MiniLM/384，并在 ingest 后执行 all-entry offline consolidation(score=0.9)。论文 Table 3
又报告多组 rate/STM，而不是一个唯一 author profile。因此：

- 当前配置可以称 **unified 主 smoke build**，不能称“LoCoMo author reproduction”；
- hybrid 在 LoCoMo 的 extraction 输入与 user_only 等价，但 lifecycle/threshold/rate 不等价；
- `official_full` 是历史命名债，不代表作者复现；在现有 5×10 flow-through smoke 完成前不为
  名称重构打断主线，但任何报告不得借该名字声称 official parity；
- 已裁 TOML/builder 重构仍放在**首个作者 calibration 或真实效果 full 之前**：届时一个 method
  TOML 可新增稀疏 `author_locomo`，完整声明 author build + answer builder；不从 CLI 逐项传参，
  不按 benchmark 暗切。当前 flow-through smoke 不等待效果调参。

unified answer readout 不使用 LightMem 的 `ANSWER_PROMPT`：LoCoMo registry 选 benchmark-owned
`build_locomo_unified_answer_prompt()`，采用官方 short-phrase prompt（temporal category 追加
DATE 提示）；answer LLM 为 gpt-4o-mini、temperature=0、max_tokens=32、top_p=1。LightMem
provider 自己生成的 prompt_messages 只供显式 author/native readout 使用。

当前 benchmark smoke policy 是 1 conversation / 1 round（两个连续 utterance）/ 1 question；
它只验四步 flow-through，不保证截断 history 足以回答所选问题，故该分数没有效果解释力。
用户已于 2026-07-17 批准：caption 修复并经架构师强验收后，B11 的 LoCoMo 命令采用
**3 rounds / 1 question**，因为第一个真实 caption 在 D1:5，三轮才会把它送进真实 backend。
这次拍板只批准 smoke **规模**；真实 API 预算与 `run_id` 仍须另行确认。无需修改全局默认
policy，也不能在修复前用扩大 smoke 掩盖缺陷。

## 5. 必须先修：caption 在 LightMem 边界丢失

vendored Mem0 LoCoMo harness 的 `session_to_chunks()` 在 blip-only 分支把
`blip_caption` 表示为 `[Sharing image that shows: {blip}]`，正文存在时追加、正文为空时单独
保留；同函数另有 query 分支。项目现行 R7 v2 有意只采用语义最清晰的 blip-only 表示，裁定
method 注入统一调用 `methods/image_text.py::turn_text_with_images()`，格式为
`[Sharing image that shows: {caption}]`，`query` 永不进入 method。此前“LoCoMo 官方 build 会拼成
`(image description: ...)`”的写法混淆了通用事件流的历史 renderer 与格式的一手来源，现已订正。

canonical LoCoMo adapter 本身没有丢 caption：它把原始 dialogue text 保存在
`Turn.content`，把 `blip_caption` 保存在 `Turn.images[].caption`，并只把 query 留在 metadata。
这里不应提前扁平化；结构化事实进入具体 method 时才恰好一次渲染，既保留未来多模态接口的
选择，也避免 event/method 双重 wrapper。

当前事件流已经把 caption 写进 `TurnEvent.content`，并在 metadata 保存原始 content 与
`turn_images`；但 `LightMem._turn_from_event()` 明确调用 `_original_content_from_event()`，且
没有像 MemoryOS 那样恢复 `ImageRef`。随后 `_locomo_pair()` 只读 `turn.content`。零 API
探针在首个 caption turn `conv-26/D1:5` 得到：

```text
event.content = 原文 + " (image description: a photo ...)"
event.original_content = 原文
lightmem.user.content = 原文
```

即 caption 确定性消失。全量有 1,226 个 caption turn（其中 316 个没有 img_url）；这会改变
memory extraction/embedding 可见事实，属于 B2/B4 正确性缺陷，不是报告披露即可接受。
默认 1-round smoke 只保留 `D1:1/D1:2`，两者都无 image，因此零报错也发现不了它。

修复边界：LightMem adapter 恢复公开 `turn_images`，对 legacy/v3 的真实消息统一调用共享
helper，并把 adapter version v5→v6 强制重建；不得下载图片、读取 `query`、改 extraction/
segment/update/retrieval 算法。任务卡见
`../cards/actor-prompt-lightmem-locomo-image-caption.md`。

## 6. 已有 LoCoMo 异常审计，不重复造轮子

benchmark 级全量异常已在
`docs/workstreams/ws02.6-first-smoke-hardening/notes/locomo-b1-audit.md` 固化并由 frozen-v1
source lock 接管：10 conversation、272 session、5,882 turn、1,986 QA（Phase 1=1,540）、
140 个 odd session、0 turn-level timestamp、0 session missing time、910 个 img_url turn、
1,226 个 caption turn、316 个 caption-only turn、conv-26 有 16 个 date-only orphan key、
0 duplicate/missing dia_id、0 consecutive same-speaker、4 道 explicit empty-evidence QA。补充复算
确认 9/2,815 个 raw evidence token 无法 exact-match canonical turn，且 9 个全在 Phase 1
（Phase 1 raw token=2,355）；`conv-50/qa[5]` 另有一个重复 `D4:5`，现行 Gold Evidence Group
稳定去重后为 2,354 units。turn view 的 9 个坏 unit 全部记 `unmatched`，session view 只有
`D` 与 `D:11:26` 仍 unmatched，其余 7 个按官方首 prefix 上卷。

现行判断：

- date-only orphan key 已被精确 session regex 忽略，不生成 phantom session；
- odd session 对 LightMem LoCoMo 特殊映射无害，因为每个 utterance 自成 pair，不按两个 human
  speaker 硬凑 user→assistant；
- empty-evidence 官方 Recall=1，同时另报 non-empty subset，已由 evaluator 契约处理；
- malformed/composite/越界 evidence 不拆、不猜改，Gold Evidence Group 按 raw list atom 保留，
  unmatched 留在分母；它们是 evaluator-private gold，不进入任何 LightMem 输入；
- 重复 evidence occurrence 按语义 unit 稳定去重；这与官方 raw scorer 的重复计权有意分叉，
  必须在 report 披露，但不构成 method 输入缺陷；
- `img_file`/`img_url` 是官方旧统计脚本漂移，canonical adapter 读取真实 `img_url` + caption；
- **尚缺的不是再做一遍 benchmark 异常扫描，而是关闭本次找到的 method 输入 caption 缺口。**

## 7. 本轮零 API 自检

```text
uv run pytest -q tests/test_locomo_conversation_adapter.py tests/test_lightmem_adapter.py \
  -k 'locomo or messages_use'
51 passed, 103 deselected, 1 warning in 5.86s

uv run pytest -q tests/test_method_official_smoke_profiles.py \
  tests/test_benchmark_registry.py::test_locomo_registration_declares_unified_prompt_track \
  tests/test_benchmark_registry.py::test_locomo_unified_prompt_uses_official_short_phrase_qa_prompt \
  tests/test_benchmark_registry.py::test_locomo_unified_prompt_appends_official_date_hint_for_category_2 \
  tests/test_lightmem_native_prompts.py
11 passed in 2.29s
```

第一条现有测试证明 speaker/pair/time/hybrid 主链，但没有 caption 断言；零 API payload 探针才
暴露该空洞。因此在 caption R1 合入并由架构师复跑前，不生成 B11 付费命令。
