# Actor 卡 M0-7：LightMem source_id 透传 → recall@k 无损改造（B5+ 已批）

> 派发日 2026-07-13。自包含卡。**代码卡（含经批准的 third_party 最小 diff）**。
> 允许修改：`third_party/methods/LightMem/src/lightmem/memory/utils.py`、
> `third_party/methods/LightMem/src/lightmem/memory/lightmem.py`（仅 payload 写入
> 处）、`src/memory_benchmark/methods/lightmem_adapter.py`、
> `tests/test_lightmem_adapter.py`（或新测试文件）、新建
> `docs/workstreams/ws02.7-method-track/notes/m0-7-lightmem-provenance.md`。
> 其余一律禁改。禁真实 API（LLM 抽取路径只做无 API 单元测试；本地
> sentence-transformers embedding 可用）。

## 0. Git 纪律（actor 自建 worktree）
```
git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m07 -b actor/m0-7-lightmem-provenance
cd /Users/wz/Desktop/mb-actor-m07 && uv sync
```
只 commit 本分支、禁 push。**worktree 缺 gitignored 资产（SimpleMem/MemOS/data
等），全量 pytest 会出现大量与你无关的假失败（M0-6 判例）**：你只需跑
`uv run pytest -q tests/test_lightmem_adapter.py`（及你新增的测试文件）+
`uv run python -m compileall -q src/memory_benchmark tests` 全绿；全量回归由
架构师合并后在主树权威复跑。LightMem 目录在 git 追踪内，可正常 commit。

## 1. 背景与已批红线（先读，必须逐字遵守）

LightMem 五 adapter 中唯一需要 third_party diff 才能支持 recall@k 的一家：
上游抽取 LLM **本就逐 fact 返回 `source_id`**（batch 内 user 消息索引），构造
`MemoryEntry` 时只用于解析时间/说话人/topic 后**丢弃**（utils.py:313-351）。
MemoryData 框架宁可绕过抽取管线也没解决此事（
`notes/memorydata-recall-retrofit-survey.md` §3）——本改造是我们的差异化
upstream PR 候选。**架构师已批的改造边界**：
1. **只做透传**：把构造过程中已解析的来源信息存为 MemoryEntry **可选字段
   （默认 None）**并条件写入 payload——**仿照本仓库副本已有的 `bam_tags`
   可选字段先例**（utils.py:32 字段声明、:158-160 条件入 dict）。
2. **零行为变化**：不改抽取 prompt/逻辑/存储流程/检索排序；字段不用时行为与
   改造前逐字节一致。
3. **完整 diff 留档**：third_party 改动的逐行 diff 原文贴进 note（upstream PR
   打包材料）。
4. 超出以上边界的任何改动 → 停工等裁决。

## 2. 施工内容

### Phase A：sid 语义一手取证（写进 note，先于实现）
- `source_id` 的语义链：抽取返回 sid → `seq_candidate = sid*2` → 查
  `topic_id_map` / `timestamps_list`（utils.py:241-281、lightmem.py:342,369）。
  **硬答案 A1**：sid 是 batch 内局部索引还是整次 add_memory 调用的全局 user
  消息索引？sequence number 由谁在哪里赋（MessageNormalizer？）、与 adapter
  提交的消息顺序是什么对应关系？全部 `文件:行号`。
- **硬答案 A2**：据 A1，MemoryEntry 应存哪个值最可靠——原始 sid、解析后的
  sequence number、还是两者？（判据：adapter 侧能否用"自己提交的消息顺序"
  无歧义映射回公开 turn id。）
- 停工条件：sid→输入消息的映射存在配置分叉或无法唯一确定 → 停工列证据。

### Phase B：third_party 最小 diff（按 A2 结论）
- `MemoryEntry` 加可选来源字段（命名建议 `source_sequence` 或经 A2 论证的
  等价物；默认 None）+ 构造处赋值 + payload 条件写入（lightmem.py:418-431
  一带）。目标 ≤ ~10 行。
- 无 API 单元测试：合成 `extracted_results` 直调
  `convert_extraction_results_to_memory_entries`，断言字段透传正确、以及
  **不给字段时序列化结果与改造前逐键一致**（零行为变化的可测表达）。

### Phase C：adapter 侧 provenance 出口
- ingest 时记录"本次 add_memory 提交的消息顺序 → 公开 turn id"映射（随
  现有 per-conversation 状态存放）；retrieve 时从 payload 读来源字段 →
  映射回公开 turn id → 填 `RetrievalResult` 的 items/provenance 通道，
  `provenance_granularity="turn"`（替换现 `"none"`，adapter:304）。
- **评测契约锚定**：先读 `evaluators/locomo_recall.py`（及其测试）确认它吃的
  id 空间与键名，adapter 发出的 id 必须与 locomo 公开 canonical turn id 一致
  （GC-1）；note 里写明对齐证据。membench/lme 的接线**不在本卡**，但 provenance
  出口实现须 benchmark 无关（只发公开 turn id，不写 benchmark 分支）。
- 无 API 端到端测试：手工构造带来源字段的 MemoryEntry → `offline_update` →
  本地 embedding 检索 → 断言 RetrievalResult 携带正确公开 turn id；再喂
  locomo-recall evaluator 断言 n>0 且分数符合构造预期（fixture 走真实序列化）。

### Phase D：完成门
- 目标测试文件 + compileall 全绿（报数字）；note 含：A1/A2 硬答案、third_party
  完整 diff、评测契约对齐证据、"真实 API smoke 验证（locomo-recall n>0）待
  用户跑"的遗留声明、upstream PR 素材小节（动机/diff/零行为变化论证）。

## 3. 硬规则
- 禁真实 API;禁改抽取 prompt/逻辑;禁动 frozen benchmark adapter;每陈述带锚。
- provenance 拿不到的路径（如旧库无该字段）必须优雅回落 `"none"`，不许报错。

## 4. 停工条件
- Phase A 歧义；diff 超边界；payload 写入路径随配置分叉到无法条件写入。

## 施工报告（actor 填写）
（待填）
