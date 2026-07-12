---
id: ws02.7
parent: ws02
status: in-progress（Method Track M0 启动；benchmark 侧五家已 frozen-v1 + B6 完成）
created: 2026-07-12
---
# ws02.7 Method Track M0（method 侧解冻后逐个接入）

benchmark 侧五家 frozen-v1 + B6 横向总验收完成（ws02.6，2026-07-12），
method 侧解冻。本 workstream 按 `docs/reference/method-integration-checklist.md`
的 B1-B11 标准，逐个 method 审查 + 双轨接入 + 极小 smoke。

**接入顺序（用户 2026-07-12 拍板）**：LightMem 首（外部校准器，原则 #16）
→ 其余按 method-interface-inventory 排 → **EverOS 最后**。

## 当前断点（2026-07-12）

- 2026-07-12（**M0 立项 + LightMem M0.1 审查完成 + 首 actor 卡开**）：
  ① 标准清单落盘 `docs/reference/method-integration-checklist.md`
  （benchmark A1-A8 + method B1-B11 的 Definition of Done）。
  ② **一手核实 native 配置矩阵**（更正架构师此前先验错误——见下表，
  Mem0/SimpleMem 都被漏报）。③ LightMem M0.1 审查完成
  [notes/lightmem-m0-audit.md](notes/lightmem-m0-audit.md)：物理隔离/
  offline flush/provenance=none/api_usage 已做/native={locomo,longmemeval}
  全部一手锚，零阻塞。④ 双 embedding 省钱想法**否决**（method 内部
  embedding 无法分叉、检索耦合构建会分叉文本，见 plan §3）。⑤ 首 actor
  卡 [actor-prompt-m0-lightmem-config.md](actor-prompt-m0-lightmem-config.md)
  = config-track 机制 + LightMem locomo native profile（离线实现+测试）。
  **下一步：用户派发 actor 卡 → 架构师验收 → 架构师跑真实 unified smoke
  （measure-first：先 LightMem×LoCoMo 一个，读成本，再铺开）。**

## 一手 native 配置矩阵（2026-07-12 架构师逐仓库核实）

| method | locomo | longmemeval | beam | membench | halumem |
|--------|:--:|:--:|:--:|:--:|:--:|
| Mem0 | ✓ | ✓ | ✓ | – | – |
| MemoryOS | ✓ | – | – | – | – |
| A-Mem | ✓ | – | – | – | – |
| LightMem | ✓ | ✓ | – | – | – |
| SimpleMem | ✓ | ✓ | – | ✓ | – |
| MemOS | ✓ | ✓ | – | – | – |
| EverOS | ✓ | – | – | – | – |
| Letta/LangMem/Supermemory | 未见 | 未见 | 未见 | 未见 | 未见 |

证据出处见 plan §2。**边界**：Letta/LangMem/Supermemory 是工程产品，
grep 目录/py 未见 academic 实验配置，各自 M0 时深挖确认；"有实验目录"
≠"能完整抽出 native config"，逐格抽取 + 架构师验收才算数。native 轨
只在 ✓ 格存在；unified 轨所有格都要。

## 里程碑

- **M0.1** 逐 method 接口审查（架构师一手）→ audit note。
- **M0.2** 双轨接入（config-track 机制 + native profile 抽取，actor 实现）。
- **M0.3** 极小 unified smoke（架构师跑真实 API，measure-first）→ 成本观测。
- **M0.4** native 轨 smoke（有配置的格子）+ method-frozen-v1。
- 之后：I0 离线矩阵 → R0 真实校准（lightmem 论文对齐，见
  ws02.6 judge-config-audit §6；用户批预算）。
