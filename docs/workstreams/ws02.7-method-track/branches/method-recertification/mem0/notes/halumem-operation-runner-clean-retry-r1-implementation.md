# HaluMem operation runner clean retry R1 — 实现记录

对应任务卡：`cards/actor-prompt-halumem-operation-runner-clean-retry-r1.md`；
裁决锚：`mem0-joint-ruling.md` §4.2。

## 0. 施工环境

隔离 worktree：`/Users/wz/Desktop/mb-actor-halumem-operation-r1`，分支
`actor/halumem-operation-clean-retry-r1`，起点 `35c4322`（main）。

工作树缺 `.env` 与 `data/`（均已 gitignore），已只读软链自 main 工作区
（`ln -s /Users/wz/Desktop/memoryBenchmark/.env .env`、
`ln -s /Users/wz/Desktop/memoryBenchmark/data data`）解除四个既有测试因缺资产
产生的假失败（`Missing OpenAI API key` × 2、`DatasetNotFoundError:
data/halumem/HaluMem-Medium.jsonl` × 2）；未暂存这两个软链（已确认被
`.gitignore`/`.git/info/exclude` 覆盖，`git status --short` 不显示）。

## 1. 改动范围

- `src/memory_benchmark/runners/operation_level.py`：`run_operation_level_predictions()`
  新增可选 `clean_failed_ingest_conversation` 参数；调用点前置一次
  `_prepare_clean_failed_ingest_retries()`（从 `runners.prediction` 复用，未复制逻辑）；
  单 conversation 循环把裸 `state.get("status")` 判断改为
  `_conversation_state_status()`（自动兼容旧 `status="failed"+ingested=False`）；
  新增 failed_ingest fail-closed 分支（显式 retry 但状态仍是
  `failed_ingest`——即没有 clean hook 或 hook 未提供——直接 `ConfigurationError`，
  不重放）；`_run_operation_conversation()` 调用包一层
  `try/except Exception`，在 re-raise 前原子写
  `{status: failed_ingest, stage: operation_conversation, error_type, error,
  ingested: False}` 并写一条 `conversation_failed` 结构化日志事件。
- `src/memory_benchmark/cli/run_prediction.py`：operation-level 分支的
  `run_operation_level_predictions(...)` 调用新增一行
  `clean_failed_ingest_conversation=clean_failed_ingest_conversation`（该
  callback 早已由 `_bind_clean_failed_ingest_conversation()` 在同一函数内为标准
  runner 分支构造好，只是此前没有传给 operation-level 分支）。
- 零 method adapter / provider protocol / retrieval query / evaluator diff：
  未改 `top_k=10`（memory_update_probe）/`top_k=20`（qa）、未改
  `_answer_prompt_record`/`_update_probe_record`/`_session_report_record`、
  未改 `mem0_adapter.py` 或任何其他 method 文件。

## 2. 失败 → 恢复时序（实测，非推导）

以 `tests/test_halumem_registered_prediction.py::
test_halumem_operation_conversation_failure_marks_failed_ingest_without_partial_artifacts`
和 `tests/test_operation_level_runner.py::
test_operation_level_conversation_failure_marks_failed_ingest_and_withholds_partial_artifacts`
为准，用 fake provider 在两 conversation 中的第二个（或单 conversation 的第二个
session）触发 `RuntimeError`：

1. 第一个 conversation（或第一个 session）正常 ingest/extraction/update/QA，
   在 `_run_operation_conversation()` 成功返回后写 `status=completed` 并调用
   `_write_operation_output_artifacts()`——此时磁盘上已有该 conversation 的
   session report / update probe / prediction / answer prompt。
2. 第二个 conversation 的 `_run_operation_conversation()` 在某个 session 的
   `ingest()` 抛出 `RuntimeError`；异常在到达 `_write_operation_output_artifacts()`
   之前就被外层 `try/except` 捕获，`conversation_status.json` 原子写为
   `failed_ingest`，然后原样 re-raise，整个 `run_operation_level_predictions()`
   调用向上抛出（single-worker 串行，不会继续处理该 conversation 之后的问题；
   在两 conversation 数据集里第二个就是最后一个，因此不涉及"后续未处理
   conversation"分支）。
3. 该失败 conversation 在内存中已累积的 partial 记录（若失败发生在
   session≥2，第一个 session 的 report/update probe 已 append 进
   `session_report_records`/`update_probe_records`）**从未被写盘**——因为
   `_write_operation_output_artifacts()` 只在 `_run_operation_conversation()`
   成功返回后调用，进程随异常终止，内存态被丢弃。实测断言：单 conversation
   数据集失败后 `session_memory_reports.jsonl`/`update_probe_results.jsonl`/
   `method_predictions.jsonl` 全部为空；双 conversation 数据集失败后三类
   artifact 只含第一个 conversation 的记录。
4. resume（`policy.resume=True`，`retry_failed_conversations` 默认 `False`）：
   循环内 `_conversation_state_status(state) == "failed_ingest"` 直接
   `continue`，新 provider 实例 `calls == []`——零新调用，`summary.
   completed_conversations` 不包含该 conversation。
5. 显式 retry（`retry_failed_conversations=True`）且**有** clean hook：
   `_prepare_clean_failed_ingest_retries()` 在循环开始前调用 hook 恰一次
   （`RecordingCleanHook`/本地 `_clean` 记录 `len(calls) == 1`），并把状态原地
   改写为 `{status: pending, ingested: False, retry_cleaned: True,
   previous_status: <旧 failed_ingest 状态>}`；随后循环把该 conversation 当作
   全新 pending conversation 处理，`_run_operation_conversation()` 从 session 1
   开始重新 `ingest()`（实测 `provider.calls[0] == ("ingest", "s1", ...)`  /
   `("ingest", "s-halu-user-2")`），成功后写 `completed` 并生成**单份**完整
   artifact（`method_predictions.jsonl` 里两个 conversation 各恰一条，无重复）。
6. 显式 retry 但**无** clean hook（`clean_failed_ingest_conversation=None`）：
   `_prepare_clean_failed_ingest_retries()` 因 hook 为 `None` 直接返回空 tuple，
   状态仍是 `failed_ingest`；循环内 `policy.retry_failed_conversations=True` 分支
   立即 `raise ConfigurationError(...)`，早于任何新 provider 调用（实测
   `retry_provider.calls == []`）。

## 3. 公开状态 schema 变化

`conversation_status.json` 每个 conversation 的失败态从此前"从不写入"变为：

```json
{
  "status": "failed_ingest",
  "stage": "operation_conversation",
  "error_type": "RuntimeError",
  "error": "<str(exc)>",
  "ingested": false
}
```

`stage` 恒为 `"operation_conversation"`——按 §2.2.5 裁决，operation-level
runner 的安全恢复单元是整个 conversation（ingest/extraction/update/QA/
end_conversation 任一阶段失败都必须从 session 1 完整重建，不做分阶段
resume），因此不需要（也不应该）区分是哪个子阶段失败；`error_type`/`error`
已经携带定位信息。成功路径的 `{"status": "completed", "ingested": true}`
未变。`_conversation_state_status()`（复用自 `runners.prediction`）保证旧版
`{"status": "failed", "ingested": false}` checkpoint 也归一到
`failed_ingest`，见
`test_operation_level_resume_treats_legacy_failed_status_as_failed_ingest`。

## 4. 定向自检（唯一授权命令，原样尾行）

```
uv run pytest -q \
  tests/test_operation_level_runner.py \
  tests/test_halumem_registered_prediction.py \
  tests/test_prediction_cli.py
```

```
...................................................................      [100%]
67 passed in 3.08s
```

## 5. retrieval artifacts 字节未改 / 零 method adapter diff

- `git diff --stat` 只涉及 `src/memory_benchmark/runners/operation_level.py`、
  `src/memory_benchmark/cli/run_prediction.py` 与三个允许清单内测试文件；无
  `mem0_adapter.py`、无 provider protocol、无 evaluator、无 TOML 改动。
- `_ingest_and_probe_session()`/`_answer_operation_question()` 内的
  `RetrievalQuery(top_k=10, purpose="memory_update_probe")` 与
  `RetrievalQuery(top_k=20, purpose="qa")` 逐行未动；`_update_probe_record()`/
  `_answer_prompt_record()`/`_session_report_record()` 输出字段与旧版逐字节
  相同（既有断言 `test_operation_level_runner_drives_three_stages_and_writes_artifacts`
  的 `provider.calls`/artifact 内容断言未改，且本轮仍全绿）。

## 6. 既有测试的显式偏差（必须披露）

`tests/test_halumem_registered_prediction.py` 原
`test_halumem_operation_resume_skips_completed_and_runs_pending_user` 依赖的
正是本卡要修的 bug：它用 `FailingSecondUserProvider` 制造第二个 conversation
中途失败，但断言**默认 resume**（未传 `retry_failed_conversations=True`）会让
第二个 provider 重新对失败 conversation 调用 `ingest()`、并把它计入
`completed_conversations == 2`。这与 `mem0-joint-ruling.md` §4.2
的裁决直接冲突（"resume 默认跳过失败 conversation"），裁决文本本身就是本卡的
唯一依据，因此判定为"验证已被裁决判定为 bug 的旧行为"，未再单独停工请示，
按裁决更新测试语义。已将其拆分为四个测试，覆盖面严格增加、无断言被削弱：
- `test_halumem_operation_conversation_failure_marks_failed_ingest_without_partial_artifacts`
  （新增：失败态落盘 + partial artifact 不落盘）
- `test_halumem_operation_resume_default_skips_failed_ingest_conversation`
  （保留原"resume 跳过已完成/失败 conversation"精神，断言改为零新调用）
- `test_halumem_operation_retry_with_clean_hook_cleans_once_then_reruns_from_session_one`
  （新增：clean hook 恰一次 + 从 session 1 完整重建单份 artifact）
- `test_halumem_operation_retry_without_clean_hook_fails_closed`（新增：无 hook
  fail-closed）

`HALUMEM_RESUME_POLICY` 的四条静态断言原样保留在
`test_halumem_operation_resume_default_skips_failed_ingest_conversation` 尾部，
未删除任何既有覆盖点。

## 7. 其他偏差

- 编码期间对本卡两个允许清单内的生产文件单独跑过一次窄范围
  `uv run python -m compileall -q src/memory_benchmark/runners/operation_level.py
  src/memory_benchmark/cli/run_prediction.py` 用于快速语法自检，早于最终定向
  pytest；未跑过 `src+tests` 全量 compileall，未跑全量 pytest，未调用真实 API。
- 未使用 subagent；本卡全部由主 actor 会话直接完成。
- 未改动 `runners/prediction.py`、任何 method adapter、provider protocol、
  evaluator 或 TOML。
- 未 push；未 amend；单个本地 commit。

## 8. 架构师 R1 follow-up（2026-07-20）

基线 commit：`40ca6da`。R1 复核确认首轮把所有异常的 `stage` 固定写成
`operation_conversation`，不满足任务卡 §2.2.5 的“可定位 stage”要求。本轮不改首轮
记录，在其上追加修复：

- `run_operation_level_predictions()` 为当前 conversation 调用链创建仅含公开字段的
  `failure_context`；`_run_operation_conversation()` 与既有 session helper 在实际调用前
  就地更新它，不包装异常，外层仍用裸 `raise` 原样抛出。
- 失败状态和 `conversation_failed` structured log 现在稳定区分
  `session_ingest`、`session_extraction`、`memory_update_probe`、
  `question_answer`、`end_conversation`、`provider_cleanup`。session 阶段可附公开
  `session_id`，QA 可再附公开 `question_id`；未记录 gold、evidence、memory point 或
  private metadata。
- `error_type` 与 `error` 在状态和 structured log 中保持原异常类名与消息；测试以自定义
  `PlannedOperationFailure` 断言调用方收到的仍是同一异常类型和消息。
- 参数化强反例覆盖卡列出的五个阶段，并额外覆盖 cleanup；每个阶段都断言失败
  conversation 的 session report、update probe、prediction、answer prompt partial
  artifacts 均不落盘。首轮 clean retry、状态机、artifact 成功提交时机、效率观测、
  retrieve query/top_k 均未改。
- R1 实际改动仅为 `src/memory_benchmark/runners/operation_level.py`、
  `tests/test_operation_level_runner.py`、
  `tests/test_halumem_registered_prediction.py` 与本 note；零 CLI、prediction.py、method
  adapter、协议或 evaluator diff。

R1 首次定向 pytest 尾行（原样）：

```text
73 passed in 3.78s
```

首次定向测试通过后，架构师补充指出 registered clean retry 用例原先分别检查
`clean_hook.calls` 与 `provider.calls`，不能直接证明二者先后。本轮随即让 clean hook 与
retry provider 写同一条 `order_trace`，并断言其前两项严格为
`["clean", "ingest:s-halu-user-2"]`；因此必要复跑同一授权测试组一次，尾行（原样）：

```text
73 passed in 2.68s
```

R1 无停工点；未使用 subagent，未调用真实 API，未下载模型，未改或写入 outputs，未
amend，未 push。
