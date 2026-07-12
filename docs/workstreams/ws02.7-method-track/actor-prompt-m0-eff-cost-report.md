# M0-eff 卡：per-run 成本报告聚合器（合并两个效率 store + ohmygpt 计价）

> ws02.7 M0 并行批次（与 M0-1b 同时施工，**文件不重叠**），2026-07-12 架构师
> （Opus 4.8）开卡。**纯离线聚合 + 计价，零真实 API，不碰采集层/reader/评测
> wiring**（那是 M0-1b）。目标：把已有效率产物变成可信的**每-run 成本报告**，
> 作为 5×10 预算表（ws05 组装）的单元格来源。用户强调：预算不准是大问题。

## 先读（按序）
1. `AGENTS.md`
2. `docs/reference/actor-handbook.md`
3. `docs/workstreams/ws02.7-method-track/notes/lightmem-efficiency-audit.md`
   （**采集层已完整可信**的一手结论 + 两个 gotcha）
4. 现有资产（**复用，不重写**）：`src/memory_benchmark/analysis/cost.py`
   （`calculate_cost`/`CostReport`/`APILLMPrice`/`APIEmbeddingPrice`）、
   `src/memory_benchmark/analysis/efficiency.py`（`aggregate_efficiency`/
   `EfficiencySummary`）、`src/memory_benchmark/observability/efficiency/storage.py`
   （`EfficiencyArtifactStore.for_prediction` / `.for_evaluator`）。
5. 本卡

## 背景（架构师一手核过，别重复怀疑）
- 采集层**无缺口**：build/answer/judge 三角色 token+call 都已插桩、优先真实
  `api_usage`（见 audit note §1）。**本卡不动采集层。**
- 缺的是**聚合层**：目前无任何生产代码把 `for_prediction`（build+answer）与
  `for_evaluator`（judge）**两个 store 合并**后计价；`calculate_cost` 只有测试在
  调用；**没有 ohmygpt 价格表**（测试里硬构造）。
- 边界：**5×10 申请表是 ws05 的活**；本卡只做**每-run 成本报告原语**（method-
  agnostic 共享基建，LightMem 首个消费者，pull-forward）。别做矩阵表。

## 施工纪律
- TDD；每 task 一 commit（一行英文）；本地 commit 不 push。
- **零真实 API**；中文 docstring；不改 third_party；不改采集层/reader/评测 wiring。
- **禁止编造外部价格**：ohmygpt 真实单价你手里没有，架构师也没有——**不许
  发明数字**。价格来源 = 用户提供的 ohmygpt rate card；本卡只建**加载器+schema+
  模板**，模板里价格填占位并标 `# 来源待溯: 填 ohmygpt 实价`，真实数字用户后填。
- 遇本卡未覆盖 / 需要真实价格才能继续 → **停工写断点**，不猜。

## Task 1：ohmygpt 价格表 config + 加载器（价格值留占位）
- 新 `configs/pricing/ohmygpt.toml`：按 model_id 列 `APILLMPrice`（input/output
  per-million-tokens）与 `APIEmbeddingPrice`；本阶段涉及的模型 = `gpt-4o-mini`
  （answer+judge backbone）；**价格数值填 `0.0` 占位 + 注释 `# 来源待溯: ohmygpt
  实价`**，currency 标 `USD`（roadmap 全局约束：ohmygpt 实价、不绑 OpenAI 官价）。
- 本地/零成本模型（`all-MiniLM-L6-v2` huggingface 本地 embedding）标记为 **local**
  （复用 `calculate_cost` 的 `skipped_local_model_ids` 语义，不进价格表）。
- 加载器 `load_pricing(path) -> Mapping[str, APIPrice]`：解析 TOML → 强类型 price；
  缺字段 fail-fast。单测覆盖解析 + 本地标记。

## Task 2：per-run 成本报告聚合器（合并两个 store）
新文件 `src/memory_benchmark/analysis/run_cost_report.py`：
- `build_run_cost_report(run_dir, prices, model_inventory) -> RunCostReport`：
  1. 读 **`EfficiencyArtifactStore.for_prediction`** + **`.for_evaluator`** 两个 store
     的 observation（缺任一 store 优雅处理：标记该角色缺失，不静默当 0）；
  2. `aggregate_efficiency(union)` 得 stage/model 汇总；
  3. `calculate_cost(union, model_inventory, prices)` 得 `CostReport`；
  4. 组装 `RunCostReport`：`total_cost` + **按角色/stage 拆分**（build/answer/judge）
     + **token-source 混比**（api_usage vs tokenizer_estimate 的 token 占比，来自
     observation 的 `token_measurement_source`）+ `complete`/`missing_price_model_ids`
     （沿用 calculate_cost 的 fail-loud，不静默零）。
- `config_track` 维度：从 run manifest 读 `config_track`（M0-1b 会写该字段）；
  **读不到就填 `"unified"`/`"unknown"` 优雅降级**——本卡不依赖 M0-1b 先落地。
- **不臆造**：所有数字来自 observation + 价格表；价格缺失 → `complete=False` +
  列出 `missing_price_model_ids`，绝不静默记 0。

## Task 3：token-source 混比与置信标注
- `RunCostReport` 暴露 `token_source_mix`（api_usage token 数 / estimate token 数 /
  占比）；audit note §3 要求：全真实→高置信，含估算→标注。
- 单测：构造含混合 source 的 fake observation，断言混比与 total_cost 正确。

## Task 4：fake-observation 测试（无真实 API、无真实 run）
`tests/test_run_cost_report.py`：
- 用**真实序列化路径**构造两个 store 的 fake observation（build+answer 进
  prediction store、judge 进 evaluator store；D4/D5 判例：fixture 必须经真实
  `EfficiencyArtifactStore` 写入函数，不手搓 JSON）；
- 断言：合并后 total_cost = 三角色之和（不漏 judge）；缺价格→complete=False +
  missing 列表；本地 embedding→skipped_local；token-source 混比正确；
  config_track 缺失→优雅降级。
- **负空间**：只读 prediction store（漏 evaluator）会漏 judge 成本——加一条断言
  证明"合并"确实纳入了 judge（防未来回归成只读一个 store）。

## 唯一自检命令
```bash
uv run pytest -q tests/test_run_cost_report.py tests/test_cost_analysis.py
```
（后者是"没碰坏既有 calculate_cost"哨兵。）全量回归架构师验收时跑。

## 明确不做
- 不做 5×10 申请表组装（ws05）。
- 不改采集层（adapter/evaluator 的 record_*）、reader/评测 wiring（M0-1b）、third_party。
- 不发明 ohmygpt 价格数字（占位 + 来源待溯，用户后填）。
- 不跑真实 API、不跑真实 run。

## 停点
Task 1-4 完成 + 自检通过 + 各 commit 就停，报告（实际模型名自查系统提示）。
需要真实价格才能推进的部分 → 停工标注，交架构师/用户。
