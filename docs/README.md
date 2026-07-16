# 文档地图

| 位置 | 内容 | 性质 |
| --- | --- | --- |
| `AGENTS.md`（仓库根） | 定位、硬规则、协作模式、导航 | 静态入口 |
| `docs/roadmap.md` | Phase 1 目标、workstream 索引、全局约束 | 方向文档 |
| `docs/workstreams/` | 每条任务线：README（状态页）+ spec + plan + notes/ | 活跃过程文档 |
| `docs/reference/` | 架构、数据模型、method 接口清单、接入指南 | 长期参考 |
| `docs/survey/` | [调查事实索引](survey/README.md) + benchmarks/ 总览、datasets/ 数据结构、workflows/ 官方评测流程 | 稳定调研资料 |
| `docs/archive/` | 已完成/被覆盖的 spec、plan、handoff、旧状态文档 | 只读历史 |
| `docs/调研资料/` | 用户个人 Obsidian 调研笔记（含 benchmark 总表） | 用户维护 |
| `opencode/` | OpenCode 通道任务与结果索引（archive/ 为历史） | 后备通道（待命） |
| `reports/` | 对外汇报材料（assets/ 存图片） | 汇报 |

## 本地目录说明（已 gitignore，不入库）

| 目录 | 性质 |
| --- | --- |
| `data/`、`models/` | 运行时数据集与本地模型权重（HF repo `BuptZZP/agentmemorybench-data`） |
| `outputs/` | 实验产物；`memoryos-locomo-full-20260603/` 受保护 |
| `third_party/benchmarks/` | 官方 benchmark 仓库副本（事实核查用） |
| `third_party/methods/` 中 6 个重仓库 | 见 `third_party/methods/MANIFEST.md` + fetch 脚本 |
| `old/` | 2026-06 之前的遗留草稿 |
| `tmp/` | 临时抓取与中间产物 |
| `paper-make/` | 论文 LaTeX 工作区 |
| `第三方框架参考/` | 第三方框架调研参考资料 |

## 查找路径

- 想知道"现在做到哪了"：`roadmap.md` → 对应 workstream README 的"当前断点"。
- 想知道"某个决定为什么这样定"：先查 workstream README 的"决策记录"，再查 `archive/`。
- 想找"某 benchmark/method 以前是否调查过"：先看 `survey/README.md`；benchmark 走三联
  survey，method 走 `reference/integration/<method>.md`，再顺链接读承重 evidence note。
- 想跑命令、查代码结构：`CLAUDE.md`。
- 想比较 actor 的真实交付：`reference/actor-performance-ledger.md`（任务级样本，不是
  脱离卡难度的模型神榜）。
