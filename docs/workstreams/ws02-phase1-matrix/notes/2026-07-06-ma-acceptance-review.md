# M-A（协议 v3 落地）验收审查记录

- 日期：2026-07-06
- 审查人：Claude（架构师）
- 结论：**APPROVED（含两处架构师修复）**——Codex 六个 task 交付质量高，
  审查发现两个缺陷已由架构师当场修复并补测试，修复后全量回归
  `758 passed, 3 deselected`（Codex 交付时 756 + 新增 2 条测试）。

## 审查范围与方法

逐文件精读三个新核心模块（`provider_protocol.py` 329 行、`event_stream.py`
237 行、`provider_bridge.py` 196+ 行），逐 diff 审读 `prediction.py` 两轮改动
（c008fb6 +269、5f90a16 +189）与 T5 补丁（672ce35），复跑全量回归与 compileall。
核心协议代码属 AGENTS 硬规则强制 review 项。

## 亮点

- 协议实体与 spec §2 逐条吻合；桥接 fallback 链完全按 T3 裁定实现，且加了
  未要求的防御（conversation_id 对齐校验、`bridge_legacy_answer_prompt` 保留）。
- manifest 协议字段带 pre-T3 向后兼容比较（`_manifests_match_for_resume`），
  避免新字段破坏旧 run resume——这是 plan 没写、Codex 主动补的正确设计。
- `session_memory_report=True` 声明未报告 → fail-fast，正确沿用 efficiency
  contract 先例；sentinel 计数进 summary。
- T5 主动完善桥接往返保真（turn_time/images/session start/end 恢复）。

## 发现与处置

1. **［已修复］caption 双重拼接破坏桥接等价性**：`_turn_content()` 按定案把
   图片 caption 烤进规范事件 content，但桥接重建 Turn 时用 `event.content` 且
   同时恢复 `images`——Mem0（mem0_adapter.py:973）与 MemoryOS
   （memoryos_adapter.py:1277）会从 `turn.images` 再拼一次 caption，真实 LoCoMo
   图片 turn 的记忆文本将与迁移前不一致。fake smoke 未拦截（合成对话无图片）。
   修复：事件 metadata 增加 `original_content`，桥接重建用原始文本
   （`provider_bridge._original_turn_content()`）；新增测试
   `test_bridge_restores_original_content_without_baked_caption`。
2. **［已修复］session report 在 retry 场景重复累积**：两处合并点只做
   `extend`，`--retry-failed` 重新 ingest 同一 conversation 会追加重复记录，
   HaluMem extraction 类评测将重复计数。修复：新增
   `_merge_session_report_records()` 按 conversation 整体替换，两处合并点接线；
   新增 helper 单测。

## 验证证据（架构师本机复跑）

- `uv run pytest tests/test_legacy_provider_bridge.py tests/test_event_stream.py -q`
  = 20 passed；dedupe helper 单测 1 passed。
- `uv run pytest -q` = **758 passed, 3 deselected, 2 warnings, 6 subtests passed**
  （≥709 基线 ✓）。
- `uv run python -m compileall -q src/memory_benchmark tests` exit 0。

## 遗留（转 M-B / 后续）

- 桥接等价性目前由 fake/offline 测试保证；M-B 每个 adapter 原生化时按 plan 做
  桥接 vs 原生 artifact 等价验证，真实 API smoke 等用户确认预算后执行。
- `bridge_legacy_answer_prompt` 整段进 metadata 有 artifact 体积增量，属
  artifact 瘦身范畴（ws03 已有条目），不阻塞。
- fake 测试语料建议在 M-B 中补充含图片 caption 的合成对话，把发现 1 的场景
  纳入常规回归（已写入 M-B plan 要求）。
