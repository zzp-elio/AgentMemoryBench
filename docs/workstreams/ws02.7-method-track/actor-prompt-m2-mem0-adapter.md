# Actor 卡 M2-mem0：Mem0 adapter 对齐施工（B2 粒度修正 + B3 清理修复 + B5 sidecar）

> 派发日 2026-07-14。自包含施工卡。证据基础=`notes/m1-mem0-evidence.md`
> （必读,本卡所有"官方口径"锚都在那里,不重复贴）。允许修改：
> `src/memory_benchmark/methods/mem0_adapter.py`、`src/memory_benchmark/
> methods/registry.py`（仅 Mem0 注册行与 clean hook 挂接）、
> `third_party/methods/mem0-main/mem0/memory/storage.py`（仅 §2.2 批准的
> 最小 diff）、tests（mem0 相关测试文件）、新建
> `docs/workstreams/ws02.7-method-track/notes/m2-mem0-adapter.md`。
> **禁改 runners/、benchmark adapters、其他 method;禁真实 API。**

## 0. Git 纪律
```
git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m2mem0 -b actor/m2-mem0-adapter
cd /Users/wz/Desktop/mb-actor-m2mem0 && uv sync
```
禁 push;只跑目标测试 + compileall（worktree 全量 pytest 有 gitignored 资产
假失败,判例见 `docs/reference/architect-playbook.md` #18）。

## 1. 架构师裁决（2026-07-14,基于 M1 取证,方案不可自行变更）

- **R2（B2）**：BEAM 注入 turn→**官方 2-turn chunk**;HaluMem session 内
  2-turn 切块→**整 session 一次 add**（官方 eval_memzero 姿势）。LoCoMo/
  LongMemEval 现状已对齐,**逐字节不动**（现有测试即回归网）;MemBench 无
  官方姿态,保持 turn+在 note 声明。
- **R3（B3）**：**保留 worker 内逻辑隔离**（run_id namespacing 是 Mem0 官方
  复现自身的姿势=方法身份,且 mem0 无本地大模型,物理化收益小）;修复
  "清得干净"缺口走 **B5+ 批准的 third_party 最小 diff**（§2.2）;补生产
  Qdrant 零 API 泄漏测试;并行维持现状（worker 间物理,
  `supports_shared_instance_parallelism=False` 不动）。history 表 tombstone
  保留=声明性无害（extraction 不读 history,只读 recent messages——M1 note
  §3.1 锚）。
- **R4（B5）**：按 M1 note §4 的最小路径逐条实现（原生 id 映射 sidecar,
  持久化,旧 state 无 sidecar fail-fast,禁 rank-index 伪造来源）。
- **R5（B6）**：五格均不新增 flush/finalize。**本卡不加任何整理阶段。**

## 2. 施工内容

### 2.1 B2 粒度修正
1. BEAM 路径:按官方 `CHUNK_SIZE=2` 每 2 turn 一次 add（registry 的 BEAM
   factory 特化从 turn 改为 pair/chunk,消息构建对照官方 `beam/run.py:255-272`
   的 role/content 规范化,差异记 note）。
2. HaluMem 路径:`SessionBatch` → **一次** `Memory.add(整 session 消息列表,
   run_id=isolation_key)`;session report 增量窗口语义不变（单次 add 的
   results 全归本 session）。
3. 回归:LoCoMo 逐 turn、LongMemEval 2-turn chunk 的现有调用序列测试必须
   原样通过。

### 2.2 B3 清理修复（批准的 third_party 最小 diff）
1. `third_party/methods/mem0-main/mem0/memory/storage.py`:SQLiteManager 新增
   `delete_messages(session_scope)`（按 scope 删 `messages` 表行;纯新增
   API,不改任何既有方法行为;风格随 vendored 源码）。
2. adapter 新增 `clean_failed_ingest_state`（对照其他四家的 hook 形态,
   registry 挂接点对照 `methods/registry.py:743,804,835,866`）:实现 =
   `delete_all(run_id=...)` + `delete_messages(session_scope=...)`（scope 值
   与 add 时进入 recent-messages 的 scope 逐字一致——先取证 add 侧 scope
   的构成再写删除,锚进 note）。
3. 测试钉死污染场景:同 run_id 先写入→模拟失败→clean→再 add,断言
   extraction 上下文读不到失败尝试的 messages（fake LLM/本地 backend,
   零 API）。
4. note 增设"upstream PR 素材"节（diff 全文+动机,仿
   `notes/m0-7-lightmem-provenance.md` §6 体例）。

### 2.3 B3 泄漏测试
本地生产 Qdrant backend（`infer=False` 或预置 payload,M1 note §3.2 的建议
路径）:双 namespace 各写各查,断言零跨读。零 API。

### 2.4 B5 provenance sidecar
按 M1 note §4 四条最小路径逐条实现;完成后 Mem0 注册行加
`provenance_granularity="turn"`（M0-10 的注册级声明字段）。测试:单 turn
add→source_turn_ids 恰为该 turn;chunk add→为该 chunk 全部 turn id;旧
state 无 sidecar→fail-fast;检索结果 item_id=官方 id。

## 3. 完成门
目标测试 + compileall 全绿（报数字）;note = 实现锚清单 + MemBench 轻姿态
声明 + tombstone 无害声明 + upstream PR 素材。真实验证（五格 smoke）由
架构师/用户随后跑,不在本卡。

## 4. 停工条件
- `delete_messages` 需要改 storage.py 之外的文件才能接通;
- HaluMem 整 session 单次 add 撞 Mem0 内部消息数上限/截断行为;
- sidecar 与 resume 语义冲突（旧 run 半途 resume 时 sidecar 状态不一致且
  无法 fail-fast 表达）。

## 施工报告（actor 填写）
（待填）
