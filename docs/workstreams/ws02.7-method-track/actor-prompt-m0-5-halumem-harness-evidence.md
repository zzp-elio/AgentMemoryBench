# Actor 卡 M0-5：HaluMem 官方 harness 喂法取证（无 session 概念 method 怎么办）

> 派发日 2026-07-13。自包含卡。**纯取证卡：只允许新建
> `docs/workstreams/ws02.7-method-track/notes/m0-5-halumem-harness-feeding.md`
> 一个文件**；禁改任何代码；禁真实 API。

## 0. Git 纪律
独立 worktree + 分支 `actor/m0-5-halumem-harness`（用户建）。只 commit 本分支、
禁 push、禁碰其他分支。先 `uv sync`。引用行号现场核实，禁编造。
（与 M0-4 卡可并行：两卡各自只新建自己的 note 文件，零交集。）

## 1. 背景与裁决判据（本卡为它供证）

HaluMem 的记忆评测需要"**每个 session 结束时，method 本次新增的 memory points**"。
LightMem `add_memory` 既不返回 entries 也无 session 概念（lightmem.md §0.5 实锤），
我们拟的方案 = session 级注入 + session 末 force 刷洗 + wrapper 捕获存储增量。
用户质疑这是否"太牵强、过度介入算法核心"。架构师已定裁决判据（lightmem.md B2）：

> **取证 HaluMem 官方 harness 对"无 session 概念 / add 不返回 entries"的 method
> 是怎么喂、怎么收 memory points 的。官方做得到同姿势 = 我们的方案公平；官方
> 也做不到 / 只支持原生带此能力的 method = 我们对 LightMem 诚实记 N/A。**

本卡只取证，不裁决。裁决 = 架构师拿你的证据做。

## 2. 取证对象
- `third_party/benchmarks/HaluMem/`（官方 eval 代码全部；若目录名不同，以
  `third_party/benchmarks/` 下实际 HaluMem 目录为准）
- 参考对照（非必需）：`第三方框架参考/MemoryData/` 是否接了 HaluMem（应该没有，
  确认一句话即可）

## 3. 施工内容（逐项硬答案）

1. **官方支持的 method 名单**：HaluMem 官方 harness 实际接入了哪些 memory
   method（目录/适配文件逐个列）。
2. **逐 method 喂法表**：每家一行——注入粒度（逐 turn / 逐 session batch /
   整 conversation）、调的 method 官方接口签名、session 边界怎么告知 method
   （显式 session id 参数？靠调用顺序？没有边界概念？）。全部带 `文件:行号`。
3. **memory points 收集口径**（本卡核心）：官方从哪拿"本 session 新增的记忆"？
   逐 method 答：add 返回值？检索/导出全库做前后 diff？method 专门的 dump
   接口？**有没有任何一家是"session 末强制触发抽取/flush 再收集"的姿势？**
4. **无此能力 method 的处理**：官方名单里有没有"add 不返回 entries / 无 session
   概念"的 method？官方对它怎么办（wrapper？跳过该指标？改 method 源码？）。
   若官方名单全是原生带能力的 method，明确写"**官方未处理过此情形**"。
5. **评测指标与 memory points 的耦合面**：官方 memory 侧指标（存在性/幻觉类）
   的输入正好是上述收集产物吗？收集不到时官方管线的行为（报错/跳过/记 0）？
6. **结论小表**（只写事实不写裁决）：三列——"官方存在 session 级批量注入姿势？
   / 官方存在事后 diff 收集姿势？ / 官方存在 force-flush 姿势？"各答 有(锚)/无。

## 4. 硬规则
- 一手证据 `文件:行号`；查不到写"来源待溯"；推断必须标注为推断。
- 只读 third_party 与参考目录，禁改；只新建那一个 note 文件。

## 5. 停工条件
- HaluMem 官方 harness 根本不含 method 接入代码（只有数据与打分）→ 停工，
  写明官方 eval 输入契约是什么（拿什么文件打分），这本身就是关键证据。

## 施工报告（actor 填写）
（待填）
