# LightMem × LoCoMo image caption 无损注入 — 实现 note

> 日期：2026-07-17；基线：main `66adb9b`（隔离 worktree
> `mb-actor-lightmem-locomo-image`，branch `actor/lightmem-locomo-image-caption`）。
> 范围：只修 LightMem method 注入边界的 caption 丢失；零真实 API、零算法改动。

## 1. 问题复述

canonical LoCoMo adapter 无损保留两层事实：原始 dialogue text 在 `Turn.content`，
`blip_caption` 在 `Turn.images[].caption`。缺口只在 LightMem method 输入表示：

- v3：`LightMem._turn_from_event()` 只调 `_original_content_from_event()`，**未**恢复公开
  `event.metadata["turn_images"]`，重建的 `Turn.images` 为空；
- legacy 与 v3 随后的 `_locomo_pair()` / `_real_message()` 只读 `turn.content`。

结果：全量 1,226 个 caption turn 的 caption 在进入 LightMem extraction/embedding 前确定性
丢失；默认 1-round smoke 的 `D1:1/D1:2` 恰好无图片，flow-through 零报错也发现不了。

## 2. 已裁实现语义（对照修复卡 §2）

1. benchmark adapter **不动**：`Turn.content` 仍为原文，`Turn.images[].caption` 仍为结构化
   caption；wrapper 只在 method 注入边界渲染一次。
2. v3 恢复 `ImageRef`：新增 `LightMem._images_from_event()`（本 adapter 私有副本，姿势与
   MemoryOS 已验收的 `_images_from_event()` 一致，但两 method 不互相依赖私有 helper）；
   `_turn_from_event()` 增加 `images=LightMem._images_from_event(event)`。
3. 统一渲染：`_locomo_pair()` 的真实 user slot 与通用 `_real_message()` 的 content 都改为
   `turn_text_with_images(turn)`（`methods/image_text.py`，格式
   `[Sharing image that shows: {caption}]`）。空 assistant placeholder 仍 `content=""`。
4. v3 不使用 `event.content`：事件流已用历史 renderer 把 caption 拼成
   `(image description: ...)`；本 adapter 输入是 `original_content + 恢复的 ImageRef`，再调
   共享 helper，最终只出现一次共享格式，绝不同时保留两种包装。
5. legacy 与 v3 对同一 Turn 字节级一致（定向测试断言 `legacy_pair == v3_pair`）。
6. `query`、img `path`/`img_url`、`redownload` 只留在 `ImageRef.metadata`/字段，共享 helper
   只读 `image.caption`，故永不进入 content；多个 caption 按公开顺序各渲染一次；空/纯空白
   caption 跳过；caption-only turn（正文空）合法。
7. speaker_id/name、source timestamp、external_id/source_external_ids、placeholder marker、
   force flags、hybrid/user_only parity 全部不变（定向测试以“无 caption 基线逐字段相等”锁定）。
8. `LIGHTMEM_ADAPTER_VERSION` 从 `conversation-qa-v5` 升为 `conversation-qa-v6`：这是 memory
   build 输入变化，全 manifest 比较使旧 v5 store 无法 resume。测试名/docstring 同步为 v6。

## 3. 数据流对照

### legacy `add(Conversation)`
`add` → `_normalize_session_to_pairs(session, conversation)` → LoCoMo 分支
`_locomo_pair(session, turn, conversation)`；`turn` 是 canonical Turn（`.images` 已由
benchmark adapter 填充）→ user content = `turn_text_with_images(turn)`。

### v3 `ingest(TurnEvent)`
`_native_turn_batch(event)` → `_native_conversation_from_events((event,))` →
`_turn_from_event(event)`（现恢复 `images`）→ `_normalize_session_to_pairs` → `_locomo_pair`
→ 同一 `turn_text_with_images(turn)`。

事件流锚点：`runners/event_stream.py:58` 把 `turn_images=[image.to_dict() for image in
turn.images]` 写入公开 metadata；`to_dict()`=`asdict(ImageRef)`，字段 image_id/path/caption/
metadata 与 `_images_from_event()` 逐字段对齐，故 legacy 与 v3 的 `Turn.images` 一致 →
payload 字节级一致。

## 4. v5→v6 重建理由

caption 从“对 LightMem 不可见”变为“进入 extraction/embedding 输入”，属 memory build 输入的
实质变化。若不升版本，旧 v5 store/manifest 会被 resume 系统的全 manifest `==` 比较错误接受，
导致新旧 build 混用。v6 强制旧 run 不可 resume，符合 resume 系统的 dataset+policy+method
config 精确匹配契约。

## 5. third_party 零改动

未触碰 `third_party/`；未改 extraction/segmentation/embedding/update/retrieval 算法；未下载
图片；未读取 LoCoMo `query`。仅在 adapter 输入表示层调用项目现有共享 helper。

## 6. 测试与定向自检

新增/修改测试（`tests/test_lightmem_adapter.py`）：
- `test_lightmem_locomo_legacy_pair_appends_single_caption_wrapper`（parametrize
  Alice→speaker_a / Bob→speaker_b）：legacy 单 caption 精确 wrapper + 相对无 caption 基线
  time/speaker/lineage 零变化 + 空 assistant marker。
- `test_lightmem_locomo_v3_event_restores_caption_from_turn_images`：**会在当前 main 失败**的
  断言，直接锁 v3 从 `turn_images` 恢复 caption（`restored.images` caption + 最终 content +
  “不同时保留两种包装”）。
- `test_lightmem_locomo_legacy_and_v3_caption_payloads_are_byte_identical`：字节级一致。
- `test_lightmem_locomo_caption_rendering_edge_cases`：caption-only / 多 caption / 空-空白
  caption / 无 caption，legacy 与 v3 均校验。
- `test_lightmem_locomo_caption_content_excludes_query_and_image_locators`：query/img locator
  不入 content。
- `test_lightmem_generic_real_message_renders_caption_via_shared_helper`：通用 `_real_message`
  也经共享 helper；无图 assistant 保持原文。
- `test_lightmem_config_manifest_includes_lifecycle_profile_and_adapter_version_v6`：重命名 +
  docstring + 断言均改 v6，旧 v5 不被放宽为兼容。

定向自检（card §5，fake runtime）：

```text
uv run pytest -q tests/test_image_text.py tests/test_lightmem_adapter.py \
  tests/test_lightmem_registered_prediction.py
1 failed, 145 passed, 1 warning in 59.89s
```

唯一失败 `test_lightmem_native_config_track_flows_through_both_official_grids` 是**环境性、
与本卡无关**：隔离 worktree 缺 gitignored `.env`，该测试的 monkeypatch 未覆盖真实
`load_openai_settings` 路径，落到 `settings.py:390` 的 “Missing OpenAI API key”。已用
`git stash` 在 pristine `66adb9b` 复现同一失败（`1 failed in 2.56s`），确认非本次修复引入的
回归。未按软链方式补 `.env`/`data`（避免把软链提交入 git）。

## 7. 偏差与停工点

无。全部在允许清单内完成；shared helper 足以表达已裁语义，未改 helper/event_stream/
benchmark adapter/TOML/third_party。
