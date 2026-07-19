# Artifact-level judge efficiency 共享修复 R1

> **本卡被发送到当前 actor 会话即代表用户已完成选择与授权，直接执行；不要再选择、派发或
> 等待另一个 actor。**你是本卡唯一责任 actor；可以自行组织 subagent，但它不得扩大 scope，
> 且你必须复核全部承重结论并在回报中披露实质分工。

## 0. 目标与工期

在一个 5h 窗口内修复共享 artifact-level API evaluator 的效率观测断链。当前 BEAM rubric
judge 与 HaluMem extraction/update/qa 都能调用真实 LLM 并落分，但
`_run_artifact_level_evaluation()` 没有建立 evaluator collector/scope，也不写 metric 专属的
model inventory / efficiency observations。

本批只补“实际发生的 judge 调用可审计落盘”；**不改任何 score、aggregation、prompt、method、
benchmark adapter、prediction artifact 或真实 run**。全程零真实 API、零模型下载、零 outputs
写入，不读 `.env`。

## 1. 上工读序与隔离

先读且只按此顺序建立上下文：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新当前断点；
3. `docs/workstreams/ws02.7-method-track/branches/evaluator-observability/README.md`；
4. `docs/reference/actor-handbook.md`；
5. 本卡全文；
6. 下列生产/测试文件的相关实现。

从用户提供的 current `main` 创建独立 worktree/branch，建议 branch
`actor/artifact-judge-efficiency-r1`。不得在主树施工，不 push，不 amend 别人的 commit。

## 2. 已裁事实（不得重新做大审计）

1. `run_artifact_evaluation()` 的普通逐题路径已经正确执行：
   `_resolve_evaluator_efficiency_collector` → per-question `judge_scope` →
   `EfficiencyArtifactStore.for_evaluator()`；这一条是参照实现，不得退化。
2. `_run_artifact_level_evaluation()` 当前只调用 `evaluate_run_artifacts()` 并写 score/summary，
   完全不处理 evaluator efficiency；这是根因。
3. `BeamRubricJudgeEvaluator` 与 HaluMem 三个 judge evaluator 都继承
   `LLMJudgeEvaluator.supports_efficiency_observability=True`，真实 `_judge_json()` 会调用
   `_record_judge_llm_call()`；runner 若只注入 collector、却不建立 scope，会 fail-fast，不能只补
   一半。
4. BEAM 的 event-ordering equivalence 真实 API 分支当前绕过 usage recorder；本批必须一并纳入，
   否则 rubric 主调用绿了仍会漏一类真实 judge 调用。
5. 离线 artifact evaluator（Recall/rank/source-accuracy/HaluMem memory-type 等）不声明 support，
   不得生成空的 judge inventory/observation artifact。
6. 既有 BEAM 两个 run 的 score、pair lineage、Recall N/A、Qdrant、prediction efficiency 均已
   通过；本批不得据此重跑或改写它们。

## 3. 公开实现契约

### 3.1 runner 单一入口

让 artifact-level 路径复用普通路径的 collector 与 model-inventory 校验：

- 调用 artifact evaluator **之前**解析/注入 collector；启用时校验 `run_id` 并取得强类型 model
  inventory；
- artifact evaluator payload 增加一个仅供 runner 内部消费的
  `efficiency_observations` 字段，值必须是 `tuple/list[EfficiencyObservation]`；runner 严格校验
  元素类型后用 `EfficiencyArtifactStore.for_evaluator(paths, metric_name)` 写入；
- 这个内部字段不得出现在 score row、summary JSON 或 CLI summary；
- 声明 efficiency support 且 collector enabled 的 artifact evaluator 必须显式返回该字段，哪怕
  本次零真实调用而值为空；缺字段/错误元素 fail-fast，禁止静默当作零调用；
- collector 被显式禁用时不得创建 evaluator efficiency 文件；不声明 support 的离线 evaluator
  行为与现状字节级不变；
- 不新增第二套 collector、全局 mutable drain queue 或粗粒度“整批一个虚构 question”的 scope。

### 3.2 scope 必须对应真实评测单元

artifact evaluator 在自己知道身份的循环内建立 scope，并把退出后的 records 汇入 payload：

- **BEAM rubric**：每个公开 `question_id` 一个 `judge_scope(actual conversation_id,
  actual question_id)`，覆盖该题全部 rubric-item 调用与 event-ordering equivalence 调用；同题多次
  调用靠 collector call index 区分，不拆成伪 question。
- **HaluMem QA**：每个公开问题一个真实 conversation/question scope。
- **HaluMem extraction**：每个 session 一个 scope；conversation id 从 private session label / report
  已有真实字段取得，question id 使用稳定、无碰撞的 evaluator-unit id（含 metric + session id），
  并在实现 note 明示它不是公开 QA id。
- **HaluMem update**：每个被实际 judge 的 update point 一个 scope；使用真实 conversation，稳定
  evaluator-unit id 必须含 metric + session id + gold index。空 retrieval 被官方路由跳过时零调用、
  不造 observation。

同一 scope 应覆盖该真实单元内所有 LLM 调用。不得把所有 session/question 塞进一个 run 级伪
scope，也不得把 observation 归到错误 conversation。

### 3.3 token usage 与 BEAM equivalence

- API usage 存在时继续以 `api_usage` 为权威；缺 usage 时沿用现有 tokenizer fallback，不写 0
  冒充精确值。
- BEAM `_judge_equivalence()` 的 Responses API 分支必须走一个返回
  `JudgeModelResponse` 的共享调用/计量路径，并恰好调用一次 `_record_judge_llm_call()`；不得因
  rubric helper 与 equivalence helper 叠套而双计。
- role-tagged messages 的 fallback token 输入要有确定性、可测试的文本化；不得改变发送给 API
  的原始 messages 或官方 equivalence prompt。
- 测试专用 `client.judge_json()` / `client.judge_equivalence()` 无真实 usage 时可以产生零
  observation，不能伪造 token；另用带 Responses API usage 的 fake client 锁真实路径。

### 3.4 幂等与并发边界

- 保留 `EfficiencyArtifactStore.merge_observations()` 的 observation-id 冲突语义；不放宽为覆盖。
- 当前 artifact evaluators 的执行拓扑不在本批改变；不要顺手实现 `max_workers` 并发。
- 不更改普通逐题 judge 的 observation id 或已有测试期望。

## 4. 必须有的强反例

至少覆盖：

1. 一个最小 artifact-level API evaluator 经 runner 后写出 metric 专属 model inventory 与一条
   judge LLM observation，run/conversation/question/model/token/stage 全精确；
2. support evaluator 缺 `efficiency_observations`、字段类型错误、元素类型错误均 fail-fast；
3. 显式 disabled collector 不写文件；离线 artifact evaluator 仍不写空 judge 文件；
4. BEAM 一题两个 rubric items → 同真实 question 下两条不同 observation id；score/official-int
   结果不变；
5. BEAM event-ordering equivalence 的真实 fake-Responses 分支额外落一条 usage observation，发送
   messages 字节/结构不变且不双计；
6. HaluMem extraction/update/qa 各至少一条真实 fake-Responses usage 路径，验证 scope identity、
   跳过分支不造 observation，原聚合结果不变；
7. 同一 evaluator 有两个 question/session 时 observation 不串 conversation，确定性排序/merge
   仍成立；
8. 内部 `efficiency_observations` 不泄漏进 summary/score artifact。

所有 Python 新 helper/类/测试 helper 都要有中文 docstring，包括嵌套 helper。

## 5. 允许文件

只允许修改：

- `src/memory_benchmark/runners/evaluation.py`
- `src/memory_benchmark/evaluators/llm_judge.py`
- `src/memory_benchmark/evaluators/beam_rubric_judge.py`
- `src/memory_benchmark/evaluators/halumem_common.py`
- `src/memory_benchmark/evaluators/halumem_extraction.py`
- `src/memory_benchmark/evaluators/halumem_update.py`
- `src/memory_benchmark/evaluators/halumem_qa.py`
- `tests/test_artifact_evaluation_runner.py`
- `tests/test_judge_efficiency_observations.py`
- `tests/test_beam_rubric_judge.py`
- `tests/test_halumem_evaluators.py`
- 新建
  `docs/workstreams/ws02.7-method-track/branches/evaluator-observability/notes/artifact-judge-efficiency-r1-implementation.md`

不必为了“用满 allowlist”制造空改动。禁止修改 registry、CLI、method adapter、benchmark adapter、
TOML、third_party、outputs、既有 run、README/checklist/policy/handbook 或其他测试。

## 6. 停工条件

遇到以下任一项，保留现场、写进 implementation note 后停止，不自行扩 scope：

1. 修复必须改变 metric score/summary 公式、prompt 或真实 API 请求语义；
2. 发现除 BEAM/HaluMem 三 judge 外还有**声明 support 且走 artifact-level**的 API evaluator，且
   无法在本 allowlist 内无损纳入；
3. 必须修改 efficiency entity/storage schema 或 prediction runner；
4. 强类型 observation 无法表达 session/update evaluator unit，需新增公开 schema；
5. 需要真实 API、私有数据、下载模型或修改既有 outputs 才能验证；
6. 直接相关失败在 15 分钟内无法区分本批回归与环境问题；
7. 需要触碰允许清单外文件。

## 7. 定向自检

只跑一次直接相关集合，禁止全量 pytest、compileall、真实 API：

```bash
OPENAI_KEY=dummy BASE_URL=http://127.0.0.1:9 \
uv run pytest -q \
  tests/test_artifact_evaluation_runner.py \
  tests/test_judge_efficiency_observations.py \
  tests/test_beam_rubric_judge.py \
  tests/test_halumem_evaluators.py \
  tests/test_documentation_standards.py
git diff --check
```

只显式 `git add` 实际改动路径，禁止 `git add -A`/`.`；commit 前看
`git status --short`。建议 commit：

```text
fix(evaluation): observe artifact-level judge calls
```

## 8. 回报格式

按 `actor-handbook.md §4` 回报：

1. commit hash；
2. 定向测试尾行原文与 `git diff --check`；
3. 实际改动文件；
4. 偏差/停工点；
5. subagent 分工；
6. 实际模型/入口及切换情况。

另用三句话分别说明：runner 内部 payload 契约、BEAM equivalence 是否纳入、HaluMem 三类 scope
identity。未获架构师验收前不 push、不清 worktree、不改父线状态。
