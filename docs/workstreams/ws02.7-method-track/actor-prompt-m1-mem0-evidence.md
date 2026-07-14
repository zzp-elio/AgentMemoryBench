# Actor 卡 M1-mem0：Mem0 接入取证（流水线二号煎饼,零生产代码）

> 派发日 2026-07-14。自包含取证卡。**只允许新建
> `docs/workstreams/ws02.7-method-track/notes/m1-mem0-evidence.md`**,禁改
> 任何生产代码/测试/third_party,禁真实 API。
> 流水线定义见 `docs/reference/method-onboarding-assembly-line.md`（必读,
> §一 的"白嫖清单"里已解决的问题不要重复取证）。
> 判据模板：`docs/reference/method-integration-checklist.md` B1-B11。
> 现有证据基础：`docs/reference/integration/mem0.md`（实例文档,先读,
> 已有的锚不用重挖,只补缺）。

## 0. Git 纪律
```
git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m1mem0 -b actor/m1-mem0-evidence
cd /Users/wz/Desktop/mb-actor-m1mem0 && uv sync
```
禁 push。纯文档卡,不跑测试;交付前 `git status` 确认只有一个新 note 文件。

## 1. 取证任务（每项给 `文件:行号` 一手锚,禁凭记忆）

1. **B1 来源与 native 注册面**：读 `third_party/methods/mem0-main` 的
   README 与 examples/evaluation 目录——官方提供哪些 benchmark 的复现
   代码？（mem0 论文主打 LoCoMo;native 注册面=仓库有啥算啥,用户拍板的
   原则）列出每个复现脚本的路径与调用序列锚。
2. **B2 注入粒度**：我们 adapter 当前的 ingest 粒度声明与消息构建点
   （`src/memory_benchmark/methods/mem0_adapter.py`,列锚）;对照官方复现
   脚本与 HaluMem 官方 `eval_memzero.py:168-194`（整 session 一次 add）的
   喂法,判断当前粒度是否与官方口径一致,不一致处列差异表。
3. **B3 逻辑隔离等价性三项（本卡核心,用户点名）**：Mem0 是当前唯一
   逻辑隔离的 method（integration-status 横向事实）。逐项取证:
   (a) **清得干净**：namespace（user_id/agent_id/run_id?）在我们 adapter
   的定义处;Mem0 官方有没有按 namespace 删除的 API（delete_all? 按
   filter 删?）,锚到 third_party 源码;已知缺口=Mem0 没挂
   `clean_failed_ingest_state`（registry 里其他四家有,mem0 无——找到
   其他四家的挂接处作对照锚）;
   (b) **漏不出去**：检索路径上 namespace filter 的实现处（adapter 侧+
   third_party 侧各一锚）;现有测试里有没有跨 namespace 泄漏测试,没有
   则记 gap;
   (c) **并行不打架**：多 worker 时 Mem0 共享的是什么存储（本地 qdrant?
   远端?）,写入并发安全的证据或反证。
   **产出:三项各"证据/gap/建议动作"一行结论,供架构师裁决逻辑隔离
   保留还是回落物理。**
4. **B5 provenance 改造落点**：判例库已预判 mem0=**原生 id 映射 sidecar**
   （`ws02.7/notes/memorydata-recall-retrofit-survey.md` 策略②）。取证:
   `add()` 的返回结构里记忆条目 id 是什么形态（third_party 锚）;检索
   返回里带不带同一 id;adapter 里建 sidecar（我们的 turn id ↔ mem0 记忆
   id）的最小落点。**只取证不实现。**
5. **B6 flush/update 姿态**：官方复现脚本有没有 post-build 整理步骤
   （类比 LightMem 的 offline_update 判例,方法论见流水线 §二.1）;逐
   benchmark 给"跑/不跑/无官方姿态采轻姿态"预判表。
6. **B9 模型口径**：官方复现/论文用的 answer/judge 模型与参数;是否
   gpt-4o-mini（决定第一阶段要不要做它的校准复现）。
7. **halumem 能力现状**：我们 adapter 的 `end_session` 现状（它是 M0-8
   的样板源）——离 SessionMemoryReport 契约还差什么（能力旗?registry
   halumem 行?）,列最小差距清单。

## 2. 完成门
note 含七节硬答案 + 每节锚;差距/gap 如实列,不猜不补。**本卡零代码,
完成门没有测试项。**

## 3. 停工条件
- third_party/methods/mem0-main 缺关键源码（如 evaluation 目录不在 vendor
  范围内）→ 停工列缺失清单,由用户决定是否补 vendor;
- 发现 adapter 现状与实例文档 `integration/mem0.md` 重大矛盾 → 停工报差异,
  不擅自改文档。

## 施工报告（actor 填写）
（待填）
