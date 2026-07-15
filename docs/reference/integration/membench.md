# MemBench 接入实例（A1-A8 逐项）

> 判据模板：`../method-integration-checklist.md` §A；勾选总表：`../integration-status.md`。
> **frozen-v1 暂停（2026-07-15 message 时间语义重开）**；证据主库 =
> `docs/workstreams/ws02.6-first-smoke-hardening/notes/membench-frozen-v1.md`。
> 100k 有 258,000 个无时间 noise step，当前 adapter 却用首个有时 turn 派生
> `session_time` 并扩散给它们；这不是 question-time 泄漏，但同样是伪造时间。Phase A
> 修复卡见 ws02.7 `branches/membench-time-semantics/`，强验收前 A2/A8 暂停。

## A1-A8 逐项

- **A1 来源锁 ✅**：repo `import-myself/Membench`（一手来源=bundled 论文 PDF；actor
  初版编造的 repo 名已纠正留痕）；arXiv 2506.21605；MIT（README badge，无 LICENSE
  文件，如实记录）；8 数据文件+PDF SHA-256 已锁；官方 commit 待溯。
- **A2 数据契约 🟡 时间修复中**：trajectory 700/900/400/1,400（0-10k）+
  140/360/80/280（100k）；
  全部 task type 单字母 MCQ（ground_truth 恒 A-D 均衡）；时间戳带冒号/无冒号双格式
  兼容（D2 修复）；但 MemBench 没有原生 session time，现行首时戳 session fallback
  已裁为错误，待 Phase A 删除；官方数据异常 3 例合法保留（越界 target_step_id ×2、
  空 ×1）。
- **A3 公私边界 ✅**：`answer`/`ground_truth`/`target_step_id` 绝不进公开对象；CLEAN。
- **A4 canonical/GC-1 ✅**：公开 turn id=`str(step_index+1)`（1 基）；官方
  target_step_id 0 基已平移 +1，原值留 metadata 对照。
- **A5 prompt/metric parity ✅**：官方 `INSTRUCTION_FIRST` **逐字**（含官方 typo
  `your'conversation`；THIRD 是死代码——签名默认值≠实际调用点判例）；
  `membench-choice-accuracy` 主指标 + `parse_failed` 分开统计；f1 注册面排除（MCQ）。
- **A6 smoke/resume ✅**：标准 smoke = 0_10k **4 源文件各 1 条**（路径覆盖原则）；
  `--membench-sources` 是调试旋钮非认证口径；formal = tid 级 checkpoint。
- **A7 artifact/efficiency ✅**：evidence 顶层序列化（D5 停工裁决：fixture 必须经
  真实序列化函数）。
- **A8 冻结门 🟡**：D5 时点证据保留；2026-07-15 时间语义修复重新开门，待定向/
  全量回归后恢复 frozen-v1。

## 对 method 接入的含义

1. **1 trajectory = 1 conversation = 1 question**（隔离空间=tid）→ smoke 默认问题
   帽=1 的依据之一。
2. **双人称双格式**：第一人称 1 dict=1 turn；第三人称 1 str=1 turn——adapter 的
   turn 文本形态在两类源文件间不同，smoke 4 源各 1 条就是为逼出这类分叉。
3. **answer LLM 参数不可考**（官方封装在外部 benchutils）：框架定 temp0/
   max_tokens=None 并如实标注——对比论文数字时**不可声称参数对齐**（冻结记录 §7.2）。
4. 官方用 json_schema 强制单字母，框架用自由文本+健壮解析替代：method 输出格式
   混乱会落进 `parse_failed`（判错），格式遵从性影响分数，报告须带 parse_failed 率。
5. recall：session 粒度 N/A（单 session 无结构）；turn provenance 才可评——当前
   全 method provenance=none，全 N/A。
6. **native 格**：仅 SimpleMem。其余 method 在 membench 全部单轨 collapse。
7. 100k variant 只剖面未全链路；capacity/memory-efficiency 维度 Phase 1 未纳入。
8. `QA.time` 只进 retrieval query / answer prompt。message 文本有自己的 time marker 时可
   无损结构化到该 turn；无 marker 保持 None。要求每条 message timestamp 的 method
   必须按真实 variant shape 做兼容性预检，不得拿 question/首条/墙钟造时间。
