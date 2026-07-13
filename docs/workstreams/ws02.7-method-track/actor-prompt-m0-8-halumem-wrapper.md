# Actor 卡 M0-8：LightMem × HaluMem 接入（session 级注入 + force 刷洗 + 只读捕获）

> 派发日 2026-07-13。自包含代码卡。允许修改：
> `src/memory_benchmark/methods/lightmem_adapter.py`、`src/memory_benchmark/
> methods/registry.py`（仅 LightMem 注册行）、tests（lightmem 相关测试文件）、
> 新建 `docs/workstreams/ws02.7-method-track/notes/m0-8-halumem-wrapper.md`。
> **禁改 third_party、禁改 halumem benchmark adapter/evaluator、禁真实 API。**
> **与 M0-9 卡都动 adapter，必须串行**（本卡开工前确认 M0-9 已合入 main 或未派）。

## 0. Git 纪律
```
git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m08 -b actor/m0-8-halumem
cd /Users/wz/Desktop/mb-actor-m08 && uv sync
```
禁 push。**只跑目标测试文件 + compileall**（worktree 全量假失败判例 playbook #18）。

## 1. 背景与已裁决方案（必读，方案不可自行变更）

架构师裁决（lightmem.md B2，已过"牵强"质疑，官方对齐证据 =
`notes/m0-5-halumem-harness-feeding.md`：HaluMem 官方 Memobase wrapper 就是
force `flush(sync=True)` + 事后增量收集姿势）：
1. **session 级注入**：HaluMem 每个 session 的全部消息作一次（或分批）
   `add_memory(messages)`（LightMem 原生收 list）；
2. **session 末强制刷洗**：`force_segment=True, force_extract=True`（官方公开
   API 旋钮）；
3. **只读捕获增量**：捕获"该 session 调用窗口内"新建的记忆条目 →
   `end_session(ref)` 返回 `SessionMemoryReport`
   （`core/provider_protocol.py:199,289`；能力旗 `session_memory_report:275`；
   现成样板 = Mem0 adapter 的 end_session，见 `integration/mem0.md` §0）。
**红线**：不改 LightMem 抽取逻辑/存储结构；捕获必须只读观察。
**报告义务**：逐 session 强制刷洗改变自然分段节奏——语义代价照 B2 措辞写进
note 与实例文档，报告须声明（官方同姿势=公平，但不掩饰）。

## 2. 施工内容

### Phase A：契约与捕获点取证（先写进 note）
1. **框架侧契约**：halumem benchmark 注册要求的 capabilities / task family
   （`benchmark_adapters/registry.py` halumem 行）；runner 何时调 `end_session`、
   `SessionMemoryReport` 各字段谁消费（`core/provider_protocol.py:199` 起 +
   halumem evaluator 输入链）；LightMem 注册行现状
   （`methods/registry.py:770` task_families={CONVERSATION_QA}）需要加什么。
2. **捕获点选型（硬答案）**：offline 模式下 entries 的流向一手锚
   （lightmem.py:382-385 → offline_update:407-434 → `embedding_retriever.insert`
   :418-434）。候选捕获点按侵入度排序评估：
   (a) adapter 包装 `embedding_retriever.insert`（只读旁听 payloads，M0-7b 后
   payload 已含 memory 文本 + source_external_id + 时间戳）；
   (b) 时间窗后查 qdrant 增量（官方 Memobase 姿势）。
   选一个，给理由与锚；任一都不许改 LightMem 代码。
3. HaluMem 数据侧：session 边界/序 id 在我们 Dataset 的形态
   （`integration/halumem.md` + `benchmark_adapters/halumem.py`），确认 adapter
   的 session 循环与 `SessionRef` 对齐。

### Phase B：实现
- adapter 增加 HaluMem 路径：session 批注入 + session 末 force 刷洗 +
  捕获窗口 → `end_session` 返回 `SessionMemoryReport`（memory 文本列表按
  协议字段填；捕获为空 = 如实空列表 + metadata 留痕，学官方 Zep 先例：跑但
  声明，不造）；能力旗 `session_memory_report=True`；registry 注册行补
  halumem 所需 task family / capabilities。
- **不影响既有 benchmark 路径**：locomo/lme/membench/beam 的注入与检索行为
  逐字节不变（现有测试就是回归网）。

### Phase C：测试（无 API）
- 合成 session 消息 → mock/本地路径验证：捕获窗口只含本 session 新增条目
  （两个 session 连跑,第二个 session 的报告不含第一个的条目——增量语义
  是 HaluMem 的核心要求,必须有测试钉死）；end_session 在无 halumem 场景
  返回 None/不激活；registry 兼容性校验通过（validate_compatibility）。

### Phase D：完成门
- 目标测试 + compileall 全绿（报数字）；note 含 Phase A 硬答案 + 捕获点
  选型理由 + 语义代价声明 + "五件套 smoke 命令建议"（predict smoke halumem +
  各指标 evaluate,免费/付费分开列：memory-type 免费；extraction/update/qa
  付费）。

## 3. 停工条件
- 捕获必须改 third_party 才可行；SessionMemoryReport 字段与 halumem evaluator
  实际输入对不上；halumem 注册面需要动 benchmark 侧代码。

## 施工报告（actor 填写）
（待填）
