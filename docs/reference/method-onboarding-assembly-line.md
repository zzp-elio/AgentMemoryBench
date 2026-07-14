# Method 接入流水线（LightMem M0 蒸馏版,2026-07-14）

> 定位：LightMem 通关（M0-1~M0-12）花了周额度 ~54%,其中大头是**一次性
> 资产**（框架 bug、协议演进、判据与纪律)和**头一次的路径探索**。本文把
> 可复制的部分蒸馏成流水线,目标:其余 9 个 method 用 ~50% 额度接完。
> 判据模板仍是 `method-integration-checklist.md`（B1-B11）,本文只管
> **怎么走得快**。

## 一、已付清的一次性资产（后续 method 白嫖清单）

接新 method 前先读这个清单,**别为已解决的问题再立卡**：

| 资产 | 出处 | 对后续 method 的意义 |
|---|---|---|
| v3 协议 + registry 声明制（granularity/provenance/protocol） | M0-8/M0-10 | 注册行填字段即可,manifest 盖章并行/串行都对 |
| provenance 全链（external_id→items→evaluator 契约） | M0-7b/M0-9 | 评测侧零工作;method 侧只做 B5+ 改造（预判已有,见下） |
| halumem operation-level runner + probe-scope 容忍变体 | M0-11 | 五个 adapter 已全部替换,**任何 method 上 halumem 不再撞崩** |
| halumem session 捕获样板（force 刷洗+只读旁听+end_session pop） | M0-8 | Mem0 的 end_session 本来就是它的样板源,反向套用极快 |
| B11 五件套判据 + benchmark 级裁决 | ws02.7 | halumem ⑤=N/A（runner 单 worker,benchmark 级,全 method 通用）;memory-type 依赖序（先付费后合成）;@k=单次检索前缀离线评;smoke 精准性=结构保证 |
| 纪律件：worktree 自建（#18)/tee（#19)/派发经济学（#20)/新人卡（#21)/commit hook | playbook | 事故预算已缴,别再交学费 |
| run_id variant 后缀约定 | ws02.7 | lme=`-s-cleaned`、membench=`-0-10k`、beam=`-100k/-10m`、halumem=`-medium` |
| B5+ 无损改造预判（MemoryData 判例库） | `ws02.7/notes/memorydata-recall-retrofit-survey.md` | mem0=id 映射 sidecar、memoryos=文本反查、amem/simplemem=in-band 或 id 映射——**策略已选好,卡里直接引用** |

## 二、方法论泛化（LightMem 判例升格为通则）

1. **B6 flush/update 姿态**：逐 benchmark **镜像官方复现脚本**;官方没跑过
   的 benchmark → 采轻姿态（主管线,不加可选阶段）+ 声明。判例=LightMem
   offline_update（locomo 官方主流程有→跑;lme 官方 readme 称 utility
   script→不跑）。**取证动作:读 method repo 的 experiments/ 或 eval/ 目录,
   每个官方脚本的调用序列列锚。**
2. **B2 注入粒度**：优先抄官方 wrapper 喂法（HaluMem 官方六 wrapper 全
   session 级批量=现成判例源,`ws02.7/notes/m0-5-halumem-harness-feeding.md`）。
3. **B9 模型口径**：answer/judge **模型统一** gpt-4o-mini,参数/prompt
   native;模型 native 只留给一次性"论文数字校准"用途（用户 2026-07-14
   拍板;官方结果非 4o-mini 的实验第一阶段不复现）。
4. **B3 隔离**：物理隔离是兜底默认;method 原生支持逻辑隔离时,须过
   **等价性三项**才准采用——①清得干净（failed-ingest 重试时 namespace 可
   完整擦除,等价于删目录）②漏不出去（跨 namespace 检索零泄漏,要测试钉死）
   ③并行不打架（多 worker 共享同一 store 的写入安全)。任一项不过 → 物理
   兜底,不恋战。

## 三、标准卡序（每 method 目标:架构师亲手动作 ≤ 6 次）

```
M-1 取证卡（actor,零生产代码,产出 notes/m1-<m>-evidence.md）
  → 架构师裁决一次过（B2 粒度/B3 隔离/B5 策略确认/B6 姿态/B9 口径/native 注册面）
M-2 施工卡（actor,adapter 对齐 v3 + registry 声明 + provenance 改造 +
  halumem wrapper + 测试;大卡,允许 1-2 轮往返）
  → 架构师强验收一次（全 diff + 主树全量,不可省——硬规则）
五格 smoke（用户跑付费 predict/evaluate;架构师跑免费评 + 五件套产物检查,
  五格可攒到 1-2 个回合集中看）
frozen note（架构师,短;声明缺口如实列）
```

- **并行政策**：不同 method 的 adapter 文件/实例文档/测试文件天然不相交,
  **允许双线并行派卡**（各自 worktree）;合并永远串行,谁先回谁先合。
- **卡内合并**：LightMem 期取证和施工分了 12 张卡是探路代价;流水线期
  M-1/M-2 各一张为默认,发现意外才拆。

## 四、额度经济学与"二号煎饼"校准

- 预算模型：9 method × 架构师 ~4% ≈ 36%,留 ~14% 意外缓冲（每个 method
  按经验必有 1-2 个 LightMem 没遇过的坑:memoryos 超参三岔口、EverOS
  vendor 去 .git 等已知候选）。
- **mem0 = 二号煎饼 = 流水线校准 run**：全程计量架构师亲手动作数与额度
  消耗,跑完外推 9 method 总账——**超预算先报告用户再继续,不闷头烧**
  （与用户的 API 预算方法论同构:smoke→成本表→批复→全量）。
- 省额度三律：能引用文档路径不复述;能一次裁决不两次往返;验收可以批量
  （两张卡一起读 diff、一次主树全量）。

## 五、维护约定
mem0 校准 run 结束后回填实测数字（架构师动作数/额度百分比/意外清单),
后续 method 偏离流水线的地方记进对应实例文档,不改本文历史。

**mem0 中期校准数（2026-07-14,M3+M0-13 验收合入时点）**
- 卡数 4：M1 取证 / M2 施工 / M3 时间口径 / M0-13（框架债,不计 mem0 本体）。
- 架构师批处理回合 **5**（M1 卡写就→M1 验收+R1-R6+M2 卡→M2 验收合入→
  五格开箱+免费评+M3/M0-13 双卡→双卡验收合入),计划 ≤6 之内。
- 意外清单 **3 件**（0.1 相关性门槛验尸 / B4 时间口径 / op-level manifest
  缺章),全在"每 method 1-2 坑"预估带宽附近;另白捡 upstream issue 候选
  第 3 件（官方 OSS server 静默丢 timestamp）。
- 剩余：s2 五格复跑开箱 + 一次性全套评 + frozen note,预计 +2 回合 →
  **单 method 全程 ≈7 架构师批处理回合**。外推：其余 8 method ≈ 56 回合;
  额度百分比锚点待用户报周面板数字后补,本文不猜。

**mem0 终账（2026-07-14 frozen-v1,二号煎饼收官）**
- 实际架构师批处理回合 **≈10**（中期 5 + s2 开箱免费评 + 用户抓漏机制轮 +
  par2/M4 裁决 + M4 验收/native + M5 验收/frozen),超计划 ≤6 约六成;
  卡数 6（M1/M2/M3/M4/M5 + M0-13 框架债)。用户周额度剩 25%(用户报数),
  **9 method 全接不现实,架构师转移窗口已到**。
- 超额定性:约半数回合产出**一次性资产**——框架债(M0-11/M0-13)、机制
  建设(对表仪式/时刻表/B8+/⑤轨别口径)、native bundle 样板(M4 含 BEAM
  builder 接线判例)、五个用户深度问答落档。**三号煎饼(memoryos)的
  边际预期 ≈5-6 回合**:M-1 取证(超参三岔口+eval/ 代码副本嫁接=已预告
  考点)→裁决→M-2 施工→验收+五格→对表+frozen,native/par2/评测口径
  的裁决全部有现成判例可引。
- 教训入模板（后续 method 生效）:① M-1 取证卡自带 B8+ 调用点清单节
  （mem0 是事后 M5 补的);② native bundle 注册并入 M-2 施工卡（mem0 是
  事后 M4 补的)——两项前置各省约 1 回合/method。
