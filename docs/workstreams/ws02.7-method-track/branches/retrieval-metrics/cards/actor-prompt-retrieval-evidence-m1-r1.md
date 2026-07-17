# Actor 返工卡：RetrievalEvidence M1 R1（闭合跨层契约与计分优先级）

> **给当前 actor 的执行指令：你就是用户已选中的执行者。** 本卡被发送到当前 actor
> 会话即代表用户已经完成选择与授权，请直接施工；不要再选择、派发或等待另一个 actor。
> 本卡是首轮 `b6c4b32` 的线性返工，必须在原 worktree、原分支上追加 commit，不 amend、
> 不 push。零真实 API。actor 可以自行组织 subagent，但不得扩大范围，且须在报告披露。

## 0. 背景、基线与目标

工作位置固定为：

- worktree：`/Users/wz/Desktop/mb-actor-retrieval-evidence-m1`
- branch：`actor/retrieval-evidence-m1`
- 首轮 HEAD：`b6c4b32`

先依次读：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊；
3. 首轮卡 `actor-prompt-retrieval-evidence-m1.md`；
4. 本卡全文；
5. `docs/reference/actor-handbook.md` §0-§4；
6. 首轮 implementation note；
7. 本卡允许修改的生产文件和对应测试。

开工先核实 branch、HEAD 和 `git status --short`。允许已有未跟踪 `data` 软链，但不得暂存。
若 HEAD 不是 `b6c4b32`、有其他已跟踪改动或本卡事实与源码矛盾，立即停工。

目标不是“让六个测试变绿”，而是闭合三项真实语义：

1. method-neutral `BenchmarkProbeProvider` 也必须诚实产出它自身可证明的 v1 evidence；
2. benchmark 官方排除与 provider eligibility 的先后关系必须稳定；
3. 五个 evaluator 的 retrieval artifact 校验与 summary granularity 必须单源、无漂移。

## 1. 首轮保留项：绝对不得放松

- 保留 manifest `retrieval_evidence_contract_version == "v1"` 严格门；
- 保留全 answer-record evidence preflight 先于任何 `_abs`/no-target/empty-gold 排除；
- 不允许 legacy fallback、从旧 `provenance_granularity` 猜 evidence，或把 missing/null 当 N/A；
- 不通过删测试、改成 `pytest.raises`、跳过测试、放宽断言来“修复”六个失败；
- 不改 runner、registry、provider protocol、Gold Evidence Group schema、method adapter、TOML、
  benchmark adapter、third_party 或真实实验输出。

## 2. R1-1：给 BenchmarkProbeProvider 产出真实 evidence

修改 `src/memory_benchmark/audit/benchmark_probe.py`：

- `retrieve()` 的空命中与非空命中均返回非空 `RetrievalResult.evidence`；
- `semantic_provenance = valid`，`provenance_granularity = "turn"`：probe 每个 item 都由
  一个已 ingest 的公开 canonical turn 构造，并直接返回该 turn id；
- `stable_ranking = valid`：这里只陈述 **probe 自身** 的确定性选择次序与递减 score，绝不
  冒充被 monkeypatch 的 Mem0，也不声称任何真实 method 的排名已审计；
- reason code / reason 必须准确描述 probe 机制，不包含 benchmark 或 method 特判；
- 空命中仍可是 valid：能力链完整但本题零 hit，不等于证据缺失。

在 `tests/test_benchmark_probe_provider.py` 为非空和空命中精确断言三项 evidence。四个
registered offline-probe 测试可以按需增加“answer artifact evidence 非 null”的断言，不能
在 registry/runner 开 probe 特例。

## 3. R1-2：修复 LightMem 手工 artifact fixture

`tests/test_lightmem_adapter.py::test_lightmem_local_retrieval_provenance_scores_locomo_recall`
手工构造的是 M0 之前的 artifact。把它升级为真实 v1 fixture：

- answer record 写入 `retrieval_evidence = asdict(retrieval.evidence)`；
- manifest method 写入 `retrieval_evidence_contract_version = "v1"`；
- 不绕过 evaluator，不把预期改成报错；旧静态 provenance 字段可保留作反向证据。

## 4. R1-3：benchmark-policy 排除优先于逐题 eligibility

固定总顺序：

1. 两道 manifest version gate；
2. 对全部 answer records 严格 evidence preflight；
3. 对每题识别 benchmark-policy 排除；
4. 只有有可评分 gold 的题才计 evidence status、派生 decision、校验 retrieval fields 并计分。

具体裁决：

- LongMemEval `_abs` 与 official no-target 永远是 benchmark 排除，增加
  `exclusion_source="benchmark_policy"`；不能因该题 evidence 是 pending/n_a 而改写成
  provider gap，也不能计入 evidence status counts。
- LongMemEval no-target 必须用 **canonical private turn view** 判定，保持官方主路径分母
  419；不得先按 provider granularity 选 view。canonical turn 有 target、但 provider 所需
  session/turn view 缺失时是 Gold contract 矛盾，应 fail-fast，不得伪装 no-target。
- BEAM / MemBench empty-gold 同理：preflight 后先排除，增加同一 exclusion_source；不得
  先校验 top_k/items，亦不得计入 evidence counts。
- LoCoMo 没有本卡新增的 benchmark-policy 空 gold 排除，保留既有官方公式。

必须补强反例：empty/no-target 题分别携带 valid、n_a、pending evidence 时都仍为 benchmark
排除；坏 evidence 即使在排除题里仍在全量 preflight 阶段 fail-fast；summary evidence counts
只统计有可评分 gold 的题。

## 5. R1-4：共享 retrieval artifact 校验

在 `src/memory_benchmark/evaluators/retrieval_evidence.py` 单源新增内部 helper，五个
evaluator 删除各自漂移的 `_validated_retrieval_fields`。固定规则：

- `retrieval_query_top_k` 必须是 `int`、不能是 `bool`、且 `> 0`；
- `retrieved_items` 必须是 list，每项必须是 object/dict；
- 只校验实际进入 top-k 的 items；每个 top-k item 的 `source_turn_ids` 必须是非空 list，
  每个元素必须是去除首尾空白后仍非空、且原值本身无首尾空白的字符串；
- `retrieved_items=[]` 合法并记 0 hit；
- helper 只在“非 benchmark 排除且 decision valid”后调用；n_a/pending 不二次报 lineage 错。

补 `bool top_k`、字符串 top_k、空白 source id、非 dict item、0 hit 强反例；至少覆盖曾经
规则最宽松的 LoCoMo 和一条共享调用路径，确认五家均改用同一个 helper。

同时把 strict object key parser 对非字符串 key 的错误稳定转成 `ConfigurationError`，不得
泄漏排序 `TypeError`。

## 6. R1-5：summary granularity 必须真实

首轮 `summary_provenance_granularity()` 取“第一条 valid”会把 mixed run 误报为单一粒度，
且可能采到 benchmark-excluded 题。改为只从 **实际 scored 的 decisions** 聚合：

- 无 scored question：`None`；
- scored 只有一种 granularity：写该值；
- scored 同时有多种：写稳定值 `"mixed"`。

现有 `summary_provenance_granularity` 字段保留，但不得参与资格或计分。补 mixed、只有
excluded valid、valid 但未 scored 的强反例。

订正 `RetrievalEligibilityDecision` docstring：非 valid decision 的 granularity 不保证是
`none`；granularity mismatch 和 rank pending 可以保留原始逐题粒度。

## 7. 允许修改文件

生产：

- `src/memory_benchmark/audit/benchmark_probe.py`
- `src/memory_benchmark/evaluators/retrieval_evidence.py`
- `src/memory_benchmark/evaluators/locomo_recall.py`
- `src/memory_benchmark/evaluators/longmemeval_recall.py`
- `src/memory_benchmark/evaluators/longmemeval_retrieval_rank.py`
- `src/memory_benchmark/evaluators/membench_recall.py`
- `src/memory_benchmark/evaluators/beam_recall.py`

测试：

- `tests/test_benchmark_probe_provider.py`
- `tests/test_beam_registered_prediction.py`
- `tests/test_locomo_registered_prediction.py`
- `tests/test_longmemeval_registered_prediction.py`
- `tests/test_membench_registered_prediction.py`
- `tests/test_lightmem_adapter.py`
- 首轮五个 retrieval evaluator 测试文件。

文档：

- 本卡；
- 首轮 `retrieval-evidence-m1-implementation.md`（只追加 R1，不改写首轮历史）。

`tests/test_documentation_standards.py` 只运行、不修改。允许文件不等于必须制造改动；无必要
就不暂存。若正确修复必须触碰表外文件，停工交回架构师。

## 8. 定向自检

只跑一次以下集合，不跑全量；架构师负责最终全量：

```bash
uv run pytest -q \
  tests/test_benchmark_probe_provider.py \
  tests/test_beam_registered_prediction.py \
  tests/test_locomo_registered_prediction.py \
  tests/test_longmemeval_registered_prediction.py \
  tests/test_membench_registered_prediction.py \
  tests/test_lightmem_adapter.py \
  tests/test_locomo_retrieval_recall.py \
  tests/test_longmemeval_retrieval_recall.py \
  tests/test_longmemeval_retrieval_rank.py \
  tests/test_membench_retrieval_recall.py \
  tests/test_beam_recall.py \
  tests/test_documentation_standards.py
git diff --check
```

测试或 docstring 失败先定位真实原因；禁止靠删除覆盖或降低断言恢复绿色。

## 9. 施工记录、commit 与报告

在首轮 implementation note 追加：架构师复现的 `6 failed, 147 passed, 1 warning`、R1 根因
裁决、逐项实现、真实自检尾行。首轮 note 原有 actor 尾行与历史不得改写；若用户报告、磁盘
note、R1 实跑时长不同，分开如实记录。

提交前执行 `git status --short`，只用显式路径 `git add`，禁止 `-A`/`.`，不得暂存 `data`。
追加一个本地 commit，不 amend `b6c4b32`，不 push。按 actor-handbook §4 回报 hash、测试
尾行、实际改动文件、偏差/停工点、subagent 使用与入口模型；然后停止等待架构师强验收。
