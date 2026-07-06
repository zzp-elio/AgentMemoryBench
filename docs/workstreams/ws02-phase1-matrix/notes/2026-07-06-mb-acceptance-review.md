# M-B（四 adapter 原生化）验收审查记录

- 日期：2026-07-06
- 审查人：Claude（架构师）
- 结论：**APPROVED，零缺陷**——七个 commit 按 task 切分，六个等价测试形态
  完全达标，架构师本机复跑全量回归 **771 passed**（新基线），compileall 通过，
  工作区干净。

## 审查方法与证据

- 结构核对：`4b72fdb`(T0 语料) → `2c83c7e`(T1 等价骨架) → `c594bed`(Mem0) →
  `34cdbca`(LightMem) → `98abd2d`(A-Mem) → `4b0c98d`(MemoryOS) → `1c6bfe5`(收尾)。
- 关键机制精读：LightMem 延迟一拍缓冲（`_native_pending_batches`，
  lightmem_adapter.py:337/531）+ 末批 force 标志（:476/560）；实例级粒度特化
  （四 adapter 构造参数 + registry 按 benchmark 条件设置，registry.py:170/288）。
- 等价测试精读：`test_native_lightmem_locomo_matches_bridge_force_and_update_sequence`
  为最难场景——同一 conversation 分别走桥接/原生路径，
  `bridge_result.calls == native_result.calls` 全序列比对，另显式断言
  force_extract 序列 `[F,F,F,T]` 与 post-build 顺序
  `construct_update → offline_update`。这正是 plan 要求的"调用序列等价"标准形态。
- 复跑验证：`uv run pytest -q` = 771 passed, 3 deselected（架构师本机）；
  compileall exit 0；`git status` 干净。

## 里程碑意义

- 四个内置 method 的 registry 主路径均为原生 `protocol_version=v3`；
  机制卡第 7 节"形变记录"中因整段 `add(conversation)` 而生的拆分代码已按
  plan 处置。协议 v3 从 spec 变成了全链路现实。
- M-A 验收发现的 fake 语料盲区（图片 caption、连续同 speaker）已由 T0 补入
  常规回归。

## 下一步（M-C）

Track B/C 全面解冻：架构师写第一个新 benchmark 的 adapter spec
（顺序 MemBench → HaluMem → BEAM，用户 2026-07-06 已确认）；真实 API 对照
smoke（spec §9.2：native 口径迁移前后一致性）等用户确认预算后执行。
