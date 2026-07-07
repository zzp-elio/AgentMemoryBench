---
id: ws02.1
parent: ws02
doc: plan
status: approved
created: 2026-07-07
---
# ws02.1 实施计划：MemBench Adapter（spec 已获用户批准 2026-07-07）

执行者：Codex。依据：[spec.md](spec.md)（approved）、协议 v3、
[MemBench 卡片](../../survey/benchmarks/MemBench.md)。

## 施工纪律

ws01/M-A/M-B 全部纪律照旧（TDD、每 task 一 commit、停工写断点、零真实 API、
不改 third_party、中文 docstring、基线 **771 passed** 不得跌破）。
prompt 文本必须从官方源码摘录并注明行号，不许改写措辞。

## T1 Loader 与数据映射

- [x] 新 `src/memory_benchmark/benchmark_adapters/membench.py`：按 spec §2/§3
  实现 data2test 展开（question_type → scenario → trajectory）；
  conversation_id 构造规则、tid 全局唯一断言（冲突 fail-fast）；单 Session；
  PS dict step → 官方合并文本 `'user': ...; 'agent': ...`（metadata 留
  ps_user/ps_agent 分字段）、OS string step 原样；turn_id=str(step_id) 1-based；
  QA 公开/私有切分照 spec §2.3 表。
- [x] 测试：迷你合成 fixture（复刻 §2.3 JSON 结构，含 PS/OS 各一、含
  target_step_id）+ canonical 抽样测试（读真实 `data/membench/.../0-10k` 一个
  文件首条 trajectory，核对 step_id 与 target_step_id 指向内容对齐——
  spec §8 off-by-one 风险的实证测试）+ 私有键隔离测试。
- 验收：`uv run pytest tests/test_membench_conversation_adapter.py -q` 全绿。

验收输出：

```text
$ uv run pytest tests/test_membench_conversation_adapter.py -q
.....                                                                    [100%]
5 passed in 0.06s
```

```text
$ uv run pytest -q
........................................................................ [  9%]
........................................................................ [ 18%]
........................................................................ [ 27%]
.................................................................... [ 36%]
........................................................................ [ 45%]
........................................................................ [ 55%]
...................................................................... [ 64%]
........................................................................ [ 73%]
........................................................................ [ 82%]
........................................................................ [ 92%]
..............................................................           [100%]
=============================== warnings summary ===============================
tests/test_amem_adapter.py::test_amem_can_import_official_robust_layer_without_calling_api
  /Users/wz/Desktop/memoryBenchmark/third_party/methods/A-mem/memory_layer.py:1: DeprecationWarning: ast.Str is deprecated and will be removed in Python 3.14; use ast.Constant instead
    from ast import Str

tests/test_lightmem_adapter.py::test_lightmem_can_import_official_lightmemory_class
  /Users/wz/Desktop/memoryBenchmark/third_party/methods/LightMem/src/lightmem/configs/logging/base.py:7: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class LoggingConfig(BaseModel):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
776 passed, 3 deselected, 2 warnings, 6 subtests passed in 98.65s (0:01:38)
```

## T2 Registry 注册与 variant/smoke

- [x] benchmark registry 注册 `membench`：variant `0_10k`（默认，4 主文件）/
  `100k`（4 主文件）；根目录 20 条补充样本排除；`prediction_enabled=True`。
- [x] smoke 裁剪：每文件前 N 条 trajectory（`--conversations N`），不裁
  message_list；formal 不裁剪。
- 验收：registry/smoke focused 测试全绿；`uv run memory-benchmark predict
  smoke --help` 可见 membench 选项（离线断言 choices 列表即可）。

实测备注：`100k` 主文件内原始 `tid` 会跨 scenario 复用；T2 采用
`source_stream + level + question_type + scenario + tid` 作为
`conversation_id` 与重复检测边界，variant/formal 以实测唯一 conversation_id
为准。

验收输出：

```text
$ uv run pytest tests/test_benchmark_registry.py tests/test_membench_conversation_adapter.py tests/test_main_cli.py::test_main_accepts_membench_benchmark_choice -q
................................                                         [100%]
32 passed in 19.66s
```

```text
$ uv run memory-benchmark predict smoke --help
usage: memory-benchmark predict [-h] [--root ROOT]
                                [--method {amem,lightmem,mem0,memoryos}]
                                [--method-class METHOD_CLASS]
                                [--allow-unsafe-custom-parallel] --benchmark
                                {locomo,longmemeval,membench}
                                [--profile {smoke,official-full}]
                                [--variant VARIANT] [--run-id RUN_ID]
                                [--resume] [--allow-api] [--confirm-full]
                                [--rounds ROUNDS]
                                [--smoke-turn-limit SMOKE_TURN_LIMIT]
                                [--conversations CONVERSATIONS]
                                [--smoke-conversation-limit SMOKE_CONVERSATION_LIMIT]
                                [--workers WORKERS]
                                [--smoke-max-workers SMOKE_MAX_WORKERS]
                                [--enable-efficiency-observability | --disable-efficiency-observability]
                                [--max-new-conversations MAX_NEW_CONVERSATIONS]
                                [--conversation-budget CONVERSATION_BUDGET]
                                [--retry-failed]
                                [--questions-per-conversation QUESTIONS_PER_CONVERSATION]
                                [--question-limit-per-conversation QUESTION_LIMIT_PER_CONVERSATION]
                                [--answer-prompt-file ANSWER_PROMPT_FILE]
                                [--answer-prompt-profile ANSWER_PROMPT_PROFILE]
                                [{smoke,formal}]

positional arguments:
  {smoke,formal}        CLI v2 mode: smoke for tiny connectivity tests, formal
                        for official-profile runs.

options:
  -h, --help            show this help message and exit
  --root ROOT           Project root containing configs/, data/, third_party/
                        and outputs/.
  --method {amem,lightmem,mem0,memoryos}
  --method-class METHOD_CLASS
                        Custom user method class in module:ClassName format.
  --allow-unsafe-custom-parallel
                        Allow workers>1 for a custom --method-class. The user
                        is responsible for run, benchmark, worker and
                        conversation isolation.
  --benchmark {locomo,longmemeval,membench}
  --profile {smoke,official-full}
  --variant VARIANT
  --run-id RUN_ID
  --resume
  --allow-api, --confirm-api
  --confirm-full
  --rounds ROUNDS
  --smoke-turn-limit SMOKE_TURN_LIMIT
  --conversations CONVERSATIONS
  --smoke-conversation-limit SMOKE_CONVERSATION_LIMIT
  --workers WORKERS
  --smoke-max-workers SMOKE_MAX_WORKERS
                        Override smoke conversation worker count; validated by
                        method profile.
  --enable-efficiency-observability
                        Write raw token/latency observations for this
                        prediction run (default).
  --disable-efficiency-observability
                        Disable prediction efficiency observation for this
                        run.
  --max-new-conversations MAX_NEW_CONVERSATIONS
                        per-command budget: advance at most this many
                        unfinished conversations in this invocation. It does
                        not become experiment identity and does not affect
                        resume compatibility.
  --conversation-budget CONVERSATION_BUDGET
                        formal mode only: advance at most this many unfinished
                        conversations in this invocation.
  --retry-failed        Retry failed conversations recorded in checkpoints. By
                        default, failed conversations stay quarantined during
                        resume to avoid repeated API burn.
  --questions-per-conversation QUESTIONS_PER_CONVERSATION
                        smoke mode only: maximum questions per selected
                        conversation.
  --question-limit-per-conversation QUESTION_LIMIT_PER_CONVERSATION
                        Per-command question budget for each selected
                        conversation. It is not experiment identity, so a
                        later resume can increase it.
  --answer-prompt-file ANSWER_PROMPT_FILE
                        Path to a custom framework answer prompt template
                        containing {question} and {memory_context}.
  --answer-prompt-profile ANSWER_PROMPT_PROFILE
                        Answer prompt profile name written to framework-reader
                        metadata.
```

```text
$ uv run pytest -q
........................................................................ [  9%]
........................................................................ [ 18%]
........................................................................ [ 27%]
.................................................................... [ 36%]
........................................................................ [ 45%]
........................................................................ [ 54%]
........................................................................ [ 63%]
........................................................................ [ 73%]
........................................................................ [ 82%]
........................................................................ [ 91%]
.................................................................        [100%]
=============================== warnings summary ===============================
tests/test_amem_adapter.py::test_amem_can_import_official_robust_layer_without_calling_api
  /Users/wz/Desktop/memoryBenchmark/third_party/methods/A-mem/memory_layer.py:1: DeprecationWarning: ast.Str is deprecated and will be removed in Python 3.14; use ast.Constant instead
    from ast import Str

tests/test_lightmem_adapter.py::test_lightmem_can_import_official_lightmemory_class
  /Users/wz/Desktop/memoryBenchmark/third_party/methods/LightMem/src/lightmem/configs/logging/base.py:7: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class LoggingConfig(BaseModel):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
779 passed, 3 deselected, 2 warnings, 6 subtests passed in 97.41s (0:01:37)
```

## T3 Unified reader（本项目第一条 unified prompt 链路）

- [x] 新 benchmark 级 prompt profile `membench_instruction_first_v1`：
  文本照抄官方 `third_party/benchmarks/Membench-main/benchmark/MembenchAgent.py`
  的 INSTRUCTION_FIRST 与 question/time/choices 拼接形态（plan 执行时注明
  精确行号）；输入 = `RetrievalResult.formatted_memory` + question +
  question_time + choices。
- [x] runner/registered service：membench 声明 `prompt_track="unified"`——
  reader 不再取 `prompt_messages`，改用 formatted_memory + 上述 profile 构造
  messages；manifest `prompt_track` 记 `unified`。实现为**最小机制**：
  benchmark registration 可携带 unified prompt builder，未携带的 benchmark
  维持现状 native 路径，不要顺手改 LoCoMo/LongMemEval。
- [x] 答案解析：输出提取 A/B/C/D（容忍大小写/句号/前后缀文本）；解析失败记
  prediction=`invalid_choice`（计错不重试）。
- 验收：reader/prompt focused 测试全绿（含解析容错表格测试）；
  fake provider 下 membench answer prompt 的 messages 结构断言。

官方源码行号实测：

```text
$ nl -ba third_party/benchmarks/Membench-main/benchmark/MembenchAgent.py | sed -n '21,31p;89,92p'
    21	INSTRUCTION_FIRST = """Please answer the following question based on past memories of your'conversation with the user.
    22	Past memory: {memory}
    23	Question: (current time is {time}) {question}
    24	Choices:
    25	A. {choice_A}
    26	B. {choice_B}
    27	C. {choice_C}
    28	D. {choice_D}
    29	Please output the correct option for the question, only one corresponding letter, without any other messages.
    30	Example: D
    31	"""
    89	            prompt = PromptTemplate(
    90	                    input_variables=['memory', 'question', 'time' 'choice_A', 'choice_B', 'choice_C', 'choice_D'],
    91	                    template=INSTRUCTION_FIRST
    92	                ).format(memory = memory_context, question = question, time = time_, choice_A = choices['A'], choice_B = choices['B'], choice_C = choices['C'], choice_D = choices['D'])
```

验收输出：

```text
$ uv run pytest tests/test_benchmark_registry.py::test_membench_registration_declares_variants_and_prediction_enabled tests/test_benchmark_registry.py::test_membench_unified_prompt_builder_uses_official_instruction_first tests/test_benchmark_registry.py::test_membench_choice_parser_accepts_common_reader_outputs tests/test_prediction_runner.py::test_runner_uses_membench_unified_prompt_builder_and_choice_parser -q
........                                                                 [100%]
8 passed in 0.35s
```

```text
$ uv run pytest tests/test_benchmark_registry.py tests/test_prediction_runner.py::test_runner_uses_retrieve_first_provider_and_framework_reader tests/test_prediction_runner.py::test_runner_ingests_native_v3_provider_with_event_stream_and_reports tests/test_prediction_runner.py::test_runner_uses_membench_unified_prompt_builder_and_choice_parser tests/test_prediction_cli.py::test_registered_prediction_builds_framework_answer_reader -q
....................................                                     [100%]
36 passed in 16.79s
```

```text
$ uv run pytest tests/test_memoryos_registered_prediction.py::test_memoryos_registered_prediction_uses_generic_runner_with_smoke_crop_resume_and_workload_manifest -q
.                                                                        [100%]
1 passed in 0.34s
```

```text
$ uv run pytest -q
........................................................................ [  9%]
........................................................................ [ 18%]
........................................................................ [ 27%]
.................................................................... [ 36%]
........................................................................ [ 45%]
........................................................................ [ 54%]
...................................................................... [ 63%]
........................................................................ [ 72%]
........................................................................ [ 81%]
........................................................................ [ 90%]
........................................................................ [100%]
=============================== warnings summary ===============================
tests/test_amem_adapter.py::test_amem_can_import_official_robust_layer_without_calling_api
  /Users/wz/Desktop/memoryBenchmark/third_party/methods/A-mem/memory_layer.py:1: DeprecationWarning: ast.Str is deprecated and will be removed in Python 3.14; use ast.Constant instead
    from ast import Str

tests/test_lightmem_adapter.py::test_lightmem_can_import_official_lightmemory_class
  /Users/wz/Desktop/memoryBenchmark/third_party/methods/LightMem/src/lightmem/configs/logging/base.py:7: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class LoggingConfig(BaseModel):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
786 passed, 3 deselected, 2 warnings, 6 subtests passed in 88.76s (0:01:28)
```

## T4 Evaluator

- [x] `membench_choice_accuracy`：deterministic exact match
  （prediction letter == ground_truth），`requires_api=False`；复用
  `category_breakdown` 按 question_type 聚合；evaluator registry 注册。
- 验收：evaluator focused 测试全绿（正确/错误/invalid_choice 三态 +
  category 聚合断言）。

验收输出：

```text
$ uv run pytest tests/test_membench_choice_accuracy.py tests/test_evaluator_registry.py -q
.........                                                                [100%]
9 passed in 1.19s
```

```text
$ uv run pytest -q
........................................................................ [  9%]
........................................................................ [ 18%]
........................................................................ [ 27%]
.................................................................... [ 35%]
........................................................................ [ 45%]
........................................................................ [ 54%]
...................................................................... [ 63%]
........................................................................ [ 72%]
........................................................................ [ 81%]
........................................................................ [ 90%]
........................................................................ [ 99%]
...                                                                      [100%]
=============================== warnings summary ===============================
tests/test_amem_adapter.py::test_amem_can_import_official_robust_layer_without_calling_api
  /Users/wz/Desktop/memoryBenchmark/third_party/methods/A-mem/memory_layer.py:1: DeprecationWarning: ast.Str is deprecated and will be removed in Python 3.14; use ast.Constant instead
    from ast import Str

tests/test_lightmem_adapter.py::test_lightmem_can_import_official_lightmemory_class
  /Users/wz/Desktop/memoryBenchmark/third_party/methods/LightMem/src/lightmem/configs/logging/base.py:7: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class LoggingConfig(BaseModel):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
789 passed, 3 deselected, 2 warnings, 6 subtests passed in 93.47s (0:01:33)
```

## T5 Fake 全链路

- [ ] Mock v3 provider（turn 粒度）跑通 membench registered prediction →
  evaluation：artifact 齐全（predictions/answer_prompts 含 formatted_memory/
  private labels/summary + `membench_choice_accuracy` summary）；
  manifest `prompt_track=unified`、`protocol_version=v3`。
- [ ] resume 语义：trajectory 级 completed/pending 回归测试（复用既有机制，
  membench 无特殊 resume 需求）。
- 验收：端到端 fake 测试全绿；`uv run pytest -q` ≥771；compileall 通过。

## T6 收尾

- [ ] 更新 ws02.1 README 断点与勾选、ws02 README 矩阵现状表（MemBench 列
  标注"adapter 就绪待 smoke"）、`docs/reference/method-interface-inventory.md`
  不涉及（method 侧无改动）。
- 验收：`git status` 干净；全部 commit 按 task 切分。

## 明确不做

- 不实现 evidence recall metric（turn_id 落盘即可）；不做 capacity/efficiency
  模式；不动 LoCoMo/LongMemEval 的 prompt_track；不跑真实 API；
  根目录 20 条补充样本不进 loader。
