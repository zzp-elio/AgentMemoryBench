# Actor 卡：LightMem LoCoMo image caption 无损注入

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你是施工 actor，不是架构师；按本卡裁决实现，遇到停工条件交回。

## 0. 这张卡解决什么

LoCoMo 有 1,226 个带 `blip_caption` 的 turn。规范事件流已同时保存原始文本和公开
`turn_images`，但 LightMem v3 bridge 恢复 Turn 时只取 `original_content`、没有恢复
ImageRef；legacy `_locomo_pair()` 也只写 `turn.content`。结果是 caption 在进入
LightMem extraction/embedding 前确定性丢失。

本卡只修复 method 输入表示：legacy 与 v3 都使用项目现有共享 helper
`turn_text_with_images()`，输出 `[Sharing image that shows: {caption}]`；不下载图片、不读取
LoCoMo `query`、不改 LightMem extraction/segmentation/embedding/update/retrieval 算法。

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

1. `LightMem._turn_from_event()` 必须从公开 `event.metadata["turn_images"]` 恢复
   `ImageRef`，边界姿势可复用 MemoryOS 已验收的 `_images_from_event()`，但不要让两个 method
   相互依赖私有 helper。
2. LightMem 所有真实 message content（至少 `_locomo_pair()` 与通用 `_real_message()`）统一由
   `methods/image_text.py::turn_text_with_images()` 生成。无 caption 的普通 turn 语义保持不变。
3. v3 不得直接使用 `event.content`：通用事件流当前已用另一种历史格式渲染 caption，直接使用会
   绕过共享 R7 v2 格式。正确输入是 `original_content + 恢复的 ImageRef`，再调用共享 helper。
4. legacy `add(Conversation)` 与 v3 `ingest(TurnEvent)` 对同一个 Turn 必须字节级一致；caption
   只出现一次。
5. `query`、img URL/path、redownload metadata 都不能进入 content；多个 caption 按公开顺序各
   渲染一次；空/纯空白 caption 跳过；caption-only turn 合法。
6. role、speaker_id/name、source timestamp、external_id/plural lineage、placeholder marker、
   force_segment/force_extract、hybrid/user_only parity 语义全部不变。
7. `LIGHTMEM_ADAPTER_VERSION` 从 `conversation-qa-v5` 升为 `conversation-qa-v6`。这是 memory
   build 输入变化，必须让旧 store/manifest 无法 resume；同步修订准确描述版本的测试名/docstring。
8. 不改 TOML。当前 `hybrid + online_soft + MiniLM/384 + top60` 配置与本卡无关。

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
