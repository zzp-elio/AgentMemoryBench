# Actor 卡：LightMem LoCoMo image caption 无损注入

> **历史卡，禁止重复执行。**Opus 4.8 `ea08431` + Codex R1 `9f5ef69` 已强验收合入主线
> `78196bc` + `65f5805`；B2/B4 caption 门关闭，下一门是用户批准预算/run_id 后的 B11 smoke。

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你是施工 actor，不是架构师；按本卡裁决实现，遇到停工条件交回。

## 0. 这张卡解决什么

LoCoMo 有 1,226 个带 `blip_caption` 的 turn。canonical LoCoMo adapter 已无损保存两层事实：
原始 dialogue text 留在 `Turn.content`，caption 留在 `Turn.images[].caption`；它没有丢数据，
也不应提前把两者压成一个字符串。真正缺口在 method 注入边界：LightMem v3 bridge 恢复 Turn
时只取 `original_content`、没有恢复 ImageRef；legacy `_locomo_pair()` 也只写
`turn.content`。结果是 caption 在进入 LightMem extraction/embedding 前确定性丢失。

本卡只修复 method 输入表示：legacy 与 v3 都使用项目现有共享 helper
`turn_text_with_images()`，输出 `[Sharing image that shows: {caption}]`；不下载图片、不读取
LoCoMo `query`、不改 LightMem extraction/segmentation/embedding/update/retrieval 算法。
该格式的一手语义锚是 vendored Mem0 LoCoMo harness
`third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/run.py::session_to_chunks()`
的 blip-only 分支：正文存在时把 wrapper 追加到正文，正文为空时只保留 wrapper。项目 R7 v2
有意只采用这个 blip-only 表示并全局排除 `query`；不要照搬同函数的 query 分支。这里引用的是
官方 harness 的表示语义，不代表项目当前 Mem0 adapter 已经完成同一修复，也不授权改 Mem0。

## 1. 隔离环境与必读顺序

- worktree：`/Users/wz/Desktop/mb-actor-lightmem-locomo-image`
- branch：`actor/lightmem-locomo-image-caption`
- 基线：用户创建 worktree 时的 main HEAD；先记录 `git rev-parse --short HEAD`

只按顺序读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/README.md`
4. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
   lightmem-locomo-smoke-config-preflight.md`
5. `docs/reference/actor-handbook.md`
6. 本卡允许清单内的生产代码与相关既有测试；不要重扫全部历史

## 2. 已裁实现语义

1. canonical LoCoMo adapter 继续保持 `Turn.content=原始 dialogue text`、
   `Turn.images[].caption=结构化 caption`；**不得**为了本卡把 wrapper 提前写回 benchmark
   adapter 的 `Turn.content`。否则会丢失结构边界，并可能在 v3/method 侧二次渲染。恰好一次的
   文本化位置是 LightMem method 注入边界。
2. `LightMem._turn_from_event()` 必须从公开 `event.metadata["turn_images"]` 恢复
   `ImageRef`，边界姿势可复用 MemoryOS 已验收的 `_images_from_event()`，但不要让两个 method
   相互依赖私有 helper。
3. LightMem 所有真实 message content（至少 `_locomo_pair()` 与通用 `_real_message()`）统一由
   `methods/image_text.py::turn_text_with_images()` 生成。无 caption 的普通 turn 语义保持不变。
4. v3 不得直接使用 `event.content`：通用事件流当前已用另一种历史格式渲染 caption，直接使用会
   绕过共享 R7 v2 格式。正确输入是 `original_content + 恢复的 ImageRef`，再调用共享 helper。
5. legacy `add(Conversation)` 与 v3 `ingest(TurnEvent)` 对同一个 Turn 必须字节级一致；caption
   只出现一次。
6. `query`、img URL/path、redownload metadata 都不能进入 content；多个 caption 按公开顺序各
   渲染一次；空/纯空白 caption 跳过；caption-only turn 合法。
7. role、speaker_id/name、source timestamp、external_id/plural lineage、placeholder marker、
   force_segment/force_extract、hybrid/user_only parity 语义全部不变。
8. `LIGHTMEM_ADAPTER_VERSION` 从 `conversation-qa-v5` 升为 `conversation-qa-v6`。这是 memory
   build 输入变化，必须让旧 store/manifest 无法 resume；同步修订准确描述版本的测试名/docstring。
9. 不改 TOML。当前 `hybrid + online_soft + MiniLM/384 + top60` 配置与本卡无关。
10. 用户已批准 caption 修复并经架构师强验收后的 LoCoMo B11 **规模**为
    `3 rounds / 1 question`，以覆盖首个 caption turn `D1:5`；这不是本卡的付费执行授权。
    actor 不运行真实 smoke、不改全局 smoke policy；API 预算与 `run_id` 仍由后续单独确认。
11. `conv-26` date-only key、odd session、malformed/duplicate/empty gold evidence 均已在
    benchmark 层审计并处置；gold 只走 evaluator-private 通道，不能进入 LightMem。本卡不得
    读取、清洗或因这些异常改写 method 输入，也不得给 LightMem 增加 benchmark gold 特判。

## 3. 允许修改文件

```text
src/memory_benchmark/methods/lightmem_adapter.py
tests/test_lightmem_adapter.py
tests/test_lightmem_registered_prediction.py
docs/reference/integration/lightmem.md
docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
  lightmem-locomo-image-caption-implementation.md
```

不要改 `methods/image_text.py`、event_stream、benchmark adapter、TOML、registry、provider
protocol、evaluator、vendored `third_party`、其它 method、父/支线 README、preflight note、
data/models/outputs。若现有 shared helper 无法表达已裁语义，停工交回，不自行改 helper 或格式。

## 4. 必测强反例

- legacy LoCoMo：正文 + 一个 caption 的 user content 精确等于
  `正文 [Sharing image that shows: caption]`；空 assistant 保持空且 marker=True；speaker/time/
  lineage 零变化。
- v3 event round-trip：即使 `event.content` 已含历史 `(image description: ...)`，最终 LightMem
  content 仍只出现一次共享格式，绝不同时保留两种包装。
- legacy 与 v3 对同一 turn 的两条 message payload 字节级一致（允许隔离 key 等非 message
  外围字段不同）。
- caption-only、多个 caption、空/纯空白 caption、无 caption；顺序稳定。
- query/img_url/path/redownload 字符串都不出现在 content。
- named speaker A/B、同一 source timestamp 两 slot、单 utterance plural lineage 不退化。
- 通用 `_real_message()` 也调用同一 helper；没有图片的 LongMemEval/MemBench 等既有 role/pair
  强反例保持原文。
- manifest 明确 v6；旧 v5 fixture/resume identity 不得被测试放宽成兼容。
- 必须有一个会在当前 main 上失败的断言，直接锁住“v3 从 turn_images 恢复 caption”，不能只测
  shared helper 本身（它早已是绿的）。

## 5. 唯一定向自检

```bash
uv run pytest -q \
  tests/test_image_text.py \
  tests/test_lightmem_adapter.py \
  tests/test_lightmem_registered_prediction.py
```

这些测试使用 fake runtime；不得调用真实 API、下载模型、跑付费 smoke、全量 pytest 或
compileall。若隔离 worktree 缺 gitignored `data/`，优先不依赖真实数据完成本卡；不要把软链
提交入 git。

## 6. 停工条件

- 无法在允许清单内让 legacy/v3 payload 等价；
- shared helper 与 preflight 已裁格式冲突；
- 必须修改 event_stream、benchmark adapter、third_party 算法或真实数据；
- caption 加入会改变 speaker/time/lineage/placeholder 或 hybrid/user_only extraction parity，
  且 15 分钟内无法定位；
- 定向测试出现清单外真实产品缺陷，不能在本卡范围内诚实修复。

停工时在 implementation note 写最小复现、源码锚、已完成安全部分和建议裁决；禁止删断言、
改 fake 绕过生产路径，或因默认 1-round smoke 没图片就宣称无问题。

## 7. 提交纪律与完成报告

- `git diff --check`；add 前后各看 `git status --short`；只显式 add，禁 `-A`/`.`；本地单
  commit，不 amend、不 push。
- commit 建议：`fix(lightmem): preserve image captions on ingest`
- implementation note 必须列出 legacy/v3 数据流、v5→v6 重建理由、third_party 零改动、测试
  尾行和任何偏差。
- actor 可按自己判断组织 subagent，但不得扩大 scope；若实质使用，完成报告披露分工，主 actor
  对最终 diff 与报告负责。
- Co-Authored-By 只写可核实真实模型；发生模型切换且无法核实时不猜。
- 按 actor-handbook §4 回报：commit hash、测试尾行原文、实际改动文件、偏差/停工点、subagent
  分工与模型切换（如有）。到此停止，等待架构师强验收。
