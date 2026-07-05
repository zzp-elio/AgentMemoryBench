---
id: ws02
doc: plan (Track B0)
status: approved
created: 2026-07-06
---
# ws02 Track B0 实施计划：benchmark 调研卡片补全（5/5）

执行者：Codex。目的：把 benchmark 侧调研资产补齐到 5 张统一深度的卡片。
LoCoMo 和 LongMemEval 虽已接入代码，但**从未有过调研卡片**——它们的评测知识
散落在 adapter 实现和旧 handoff 里；HaluMem/BEAM/MemBench 三张卡片是旧模板
产出，缺协议设计需要的两节。与 Track A2 并列，共同支撑架构师的粒度需求矩阵。

## 施工纪律

1. 零真实 API；结论必须有 paper/code/dataset 三方交叉验证，冲突记入"未确认项"。
2. 使用 `/Users/wz/.codex/skills/benchmark-survey/SKILL.md`（2026-07-05 已更新：
   输出路径 `docs/survey/benchmarks/`、第 5/6 节协议中立口径、成本画像要求）。
3. 每完成一张立即 commit（`docs: add locomo survey card` 等）。
4. 遇模板与本 plan 冲突以本 plan 为准；遇 plan 未覆盖情况停工写断点。

## 任务清单

### 新做两张（完整 7 节，按 skill 模板）

- [x] `docs/survey/benchmarks/LoCoMo.md`。材料：
  `third_party/benchmarks/` 下 LoCoMo 官方仓库、`data/locomo/locomo10.json`、
  论文 PDF（若 third_party 内无 PDF，停工问用户要）。额外要求：
  - 我们已有实现可作"用法实证"：`src/memory_benchmark/benchmark_adapters/`
    的 LoCoMo adapter 与 4 个 method 的官方 LoCoMo eval 脚本；卡片中注明
    "官方口径 vs 我们当前实现"的差异（如 category 5 adversarial 处理、
    smoke 裁剪语义）。
  - 重点写清：session/turn 结构与时间字段、双真人说话者形态、evidence 标注、
    F1 与 LLM judge 两套 metric 的官方定义、每 method 官方 prompt 差异。

  验收输出（2026-07-05，LoCoMo）：

  ```bash
  $ python3 - <<'PY'
  import json, collections
  from pathlib import Path
  data=json.loads(Path('data/locomo/locomo10.json').read_text())
  cat=collections.Counter(q['category'] for d in data for q in d['qa'])
  turn_counts=[]
  session_counts=[]
  for d in data:
      conv=d['conversation']
      sessions=[k for k in conv if k.startswith('session_') and not k.endswith('_date_time')]
      session_counts.append(len(sessions))
      turn_counts.append(sum(len(conv[k]) for k in sessions))
  print('samples', len(data))
  print('qa_total', sum(len(d['qa']) for d in data))
  print('category_counts', dict(sorted(cat.items())))
  print('non_adversarial_qa', sum(v for k,v in cat.items() if k != 5))
  print('session_counts', sorted(set(session_counts)))
  print('turn_count_range', min(turn_counts), max(turn_counts))
  print('top_fields', sorted(data[0].keys()))
  print('conversation_fields_prefix', sorted([k for k in data[0]['conversation'] if k in ('speaker_a','speaker_b') or k.startswith('session_1')])[:5])
  print('turn_fields', sorted(data[0]['conversation']['session_1'][0].keys()))
  print('qa_fields', sorted(data[0]['qa'][0].keys()))
  PY
  samples 10
  qa_total 1986
  category_counts {1: 282, 2: 321, 3: 96, 4: 841, 5: 446}
  non_adversarial_qa 1540
  session_counts [19, 25, 28, 29, 30, 31, 32]
  turn_count_range 369 689
  top_fields ['conversation', 'event_summary', 'observation', 'qa', 'sample_id', 'session_summary']
  conversation_fields_prefix ['session_1', 'session_10', 'session_10_date_time', 'session_11', 'session_11_date_time']
  turn_fields ['dia_id', 'speaker', 'text']
  qa_fields ['answer', 'category', 'evidence', 'question']
  ```

  ```bash
  $ test -f docs/survey/benchmarks/LoCoMo.md && rg -n '^## [1-7]\. ' docs/survey/benchmarks/LoCoMo.md && rg -n '未找到 QA 的独立 LLM judge|category 5|add\(conversation\)|add_turn' docs/survey/benchmarks/LoCoMo.md
  5:## 1. 定位与适用边界
  11:## 2. 数据结构与规模
  21:## 3. 官方评测流程
  31:## 4. 指标与聚合
  41:## 5. Answer / Judge Prompt 与运行参数
  51:## 6. Method Adapter 接口需求
  61:## 7. 未确认项
  13:本地 Phase 1 使用 `data/locomo/locomo10.json`，顶层为 10 个 conversation sample，总计 1,986 个 QA；类别分布为 category 1: 282、category 2: 321、category 3: 96、category 4: 841、category 5: 446。证据：本卡验收命令读取 `data/locomo/locomo10.json` 的 `qa[*].category` 字段；论文附录页列出同样的五类数量和总数：`third_party/benchmarks/locomo-main/static/paper/locomo.pdf:p.15`。
  29:当前 framework adapter 与官方流程的主要形变：当前 `load_dataset` 从 `data/locomo/locomo10.json` 构建统一 `Dataset`；category 5 adversarial 问题被跳过，完整 1,986 QA 在当前 adapter 中会变为 1,540 个非 adversarial QA；smoke 会按 turn 截断并只保留 evidence 被覆盖的问题。证据：`src/memory_benchmark/benchmark_adapters/locomo.py:36`、`src/memory_benchmark/benchmark_adapters/locomo.py:177`、`src/memory_benchmark/benchmark_adapters/locomo.py:259`、`src/memory_benchmark/benchmark_adapters/locomo.py:343`。
  37:category 2 temporal、category 3 open-domain、category 4 single-hop 使用普通 F1；category 3 的 gold answer 会先按分号截断；category 1 multi-hop 先用逗号拆分 prediction 和 gold，再对每个 gold 取最大子答案 F1 的均值；category 5 adversarial 只检查输出是否包含 `no information available` 或 `not mentioned`。证据：`third_party/benchmarks/locomo-main/task_eval/evaluation.py:203`、`third_party/benchmarks/locomo-main/task_eval/evaluation.py:209`、`third_party/benchmarks/locomo-main/task_eval/evaluation.py:213`、`third_party/benchmarks/locomo-main/task_eval/evaluation.py:217`。
  45:category 2 问题会额外追加 “Use DATE of CONVERSATION...” 的日期提示；category 5 会把 gold answer 和 “Not mentioned in the conversation” 随机排列成二选一选项，这与普通 QA 存在协议差异。证据：`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:243`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:245`。
  53:原生粒度是 `conversation -> session -> turn -> question`。`add(conversation)` 能一次性传入完整历史，当前 adapter 已按 sample 构造 `Conversation`，并把 session 时间、turn id、speaker、图片 caption/URL 转成统一模型；这适合 retrieve-first 主协议。证据：`src/memory_benchmark/benchmark_adapters/locomo.py:94`、`src/memory_benchmark/benchmark_adapters/locomo.py:134`、`src/memory_benchmark/benchmark_adapters/locomo.py:448`。
  55:若未来引入 `add_turn(...)`，LoCoMo 应按原始 session/turn 时间顺序调用：每个 turn 至少传 `conversation_id`、`session_id`、`session_time`、`turn_id/dia_id`、`speaker`、`text`、可选图片 caption；session 边界需要保留，因为 temporal 题依赖 `session_<n>_date_time`，RAG recall 也可能按 dialog id 或 session id 对齐。证据：`third_party/benchmarks/locomo-main/README.MD:15`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:88`、`third_party/benchmarks/locomo-main/task_eval/evaluation.py:228`。
  57:查询阶段应只传 `Question.question_text` 与公开 metadata；不得把 `answer`、`evidence` 交给 method。官方 category 5 prompt 会使用 gold answer 形成二选一选项，因此当前 adapter 跳过 category 5 是一种防止 reader 侧协议污染 method 接入的形变，但会使 Phase 1 分数不可直接等同官方 1,986 QA 总分。证据：`src/memory_benchmark/benchmark_adapters/locomo.py:181`、`src/memory_benchmark/benchmark_adapters/locomo.py:216`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:245`。
  59:成本画像：完整当前 adapter 口径为 1,540 个非 adversarial 问题，每题至少一次 reader LLM 调用；method 侧成本取决于 `add(conversation)` 的 ingest 和 `retrieve(question)` 的检索。官方 RAG 口径还包含建库 context embeddings、question embeddings 和每题 answer LLM；非 RAG 官方批量模式会减少 answer 调用次数，但把更长上下文塞给 reader。证据：本卡验收命令的 category 5 差值；`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:97`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:122`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:225`。
  67:当前 adapter 跳过 category 5 是合理的隐私/协议折中，但如果后续要复现官方 adversarial 分数，需要单独设计 reader-only 的 category 5 二选一 prompt，且保证 gold answer 仍不可达 method。证据：`src/memory_benchmark/benchmark_adapters/locomo.py:177`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:245`。
  ```

  ```bash
  $ git diff --check -- docs/survey/benchmarks/LoCoMo.md docs/workstreams/ws02-phase1-matrix/plan-track-b0-benchmark-cards.md && git status --short -- pyproject.toml uv.lock .venv package.json bun.lock node_modules
  ```
- [x] `docs/survey/benchmarks/LongMemEval.md`。材料：官方仓库、
  `data/longmemeval/`（s_cleaned/m_cleaned variants）、论文 PDF。额外要求：
  - 写清 haystack session 结构、`question_time` 语义、variant 差异、
    500 instance 规模与成本含义（对照我们 1-conv cost pilot 实测）、
    官方 yes/no judge 流程（我们已按 LightMem 流程实现，注明对齐情况）。

  验收输出（2026-07-05，LongMemEval）：

  ```bash
  $ uv run python - <<'PY'
  import ijson, collections
  from pathlib import Path
  for name in ['longmemeval_s_cleaned.json','longmemeval_m_cleaned.json']:
      p=Path('data/longmemeval')/name
      count=0; qtypes=collections.Counter(); session_counts=[]; turn_counts=[]; abst=0; fields=None
      with p.open('rb') as f:
          for item in ijson.items(f,'item'):
              count += 1
              fields = fields or sorted(item.keys())
              qtypes[item.get('question_type')] += 1
              abst += int(str(item.get('question_id','')).endswith('_abs'))
              sessions=item.get('haystack_sessions') or []
              session_counts.append(len(sessions))
              turn_counts.append(sum(len(s) for s in sessions if isinstance(s,list)))
      print(name)
      print(' instances', count)
      print(' question_type_counts', dict(sorted(qtypes.items())))
      print(' abstention_by_id_suffix', abst)
      print(' session_count_range', min(session_counts), max(session_counts))
      print(' turn_count_range', min(turn_counts), max(turn_counts))
      print(' fields', fields)
  PY
  longmemeval_s_cleaned.json
   instances 500
   question_type_counts {'knowledge-update': 78, 'multi-session': 133, 'single-session-assistant': 56, 'single-session-preference': 30, 'single-session-user': 70, 'temporal-reasoning': 133}
   abstention_by_id_suffix 30
   session_count_range 38 62
   turn_count_range 396 616
   fields ['answer', 'answer_session_ids', 'haystack_dates', 'haystack_session_ids', 'haystack_sessions', 'question', 'question_date', 'question_id', 'question_type']
  longmemeval_m_cleaned.json
   instances 500
   question_type_counts {'knowledge-update': 78, 'multi-session': 133, 'single-session-assistant': 56, 'single-session-preference': 30, 'single-session-user': 70, 'temporal-reasoning': 133}
   abstention_by_id_suffix 30
   session_count_range 460 490
   turn_count_range 4586 5229
   fields ['answer', 'answer_session_ids', 'haystack_dates', 'haystack_session_ids', 'haystack_sessions', 'question', 'question_date', 'question_id', 'question_type']
  ```

  ```bash
  $ test -f docs/survey/benchmarks/LongMemEval.md && rg -n '^## [1-7]\. ' docs/survey/benchmarks/LongMemEval.md && rg -n 'question_date|question_time|LLM judge|1-conv cost pilot|add\(conversation\)|add_turn|s_cleaned|m_cleaned' docs/survey/benchmarks/LongMemEval.md
  5:## 1. 定位与适用边界
  13:## 2. 数据结构与规模
  25:## 3. 官方评测流程
  35:## 4. 指标与聚合
  45:## 5. Answer / Judge Prompt 与运行参数
  55:## 6. Method Adapter 接口需求
  67:## 7. 未确认项
  ```

  ```bash
  $ rg -n 'static/paper\?|TODO|待确认|不存在' docs/survey/benchmarks/LongMemEval.md || true
  ```

  ```bash
  $ git diff --check -- docs/survey/benchmarks/LongMemEval.md docs/workstreams/ws02-phase1-matrix/plan-track-b0-benchmark-cards.md && git status --short -- pyproject.toml uv.lock .venv package.json bun.lock node_modules
  ```

### 增补三张（不重写，只补节）

- [ ] `HaluMem.md`、`BEAM.md`、`MemBench.md` 各做一次增补 pass：对照更新后
  skill 的第 5/6 节要求检查，若缺则补：
  - **原生粒度与喂入方式**：数据的自然单位（message/turn/session/operation/
    trajectory）、官方评测按什么顺序什么粒度喂给被测系统、需要哪些边界信号。
  - **成本画像**：官方流程每 sample 的 LLM/embedding/judge 调用量级。
  增补内容追加为独立小节并标注"2026-07-06 增补"，不改动原有结论。

### 收尾

- [ ] 在 `docs/survey/benchmarks/README.md` 索引中登记两张新卡片。
- [ ] 更新 ws02 README 断点，通知架构师做粒度矩阵。

## 验收

- `ls docs/survey/benchmarks/*.md` 含 LoCoMo、LongMemEval 且 5 张目标 benchmark
  卡片全部具备"原生粒度与喂入方式 + 成本画像"内容。
- 新卡片每个结论有 文件/行号 或 dataset 字段证据；paper/code/dataset 冲突
  如实记录。
- 全程零 API；`git status` 干净（逐张 commit）。

## 明确不做

- 不改 adapter 代码；不重写三张已有卡片的既有结论；
- 不调研 Phase 1 之外的 benchmark（PersonaMem/MemoryArena 卡片已存在，不动）。
