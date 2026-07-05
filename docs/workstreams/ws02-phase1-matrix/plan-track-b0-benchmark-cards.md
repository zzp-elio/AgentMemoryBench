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

- [x] `HaluMem.md`、`BEAM.md`、`MemBench.md` 各做一次增补 pass：对照更新后
  skill 的第 5/6 节要求检查，若缺则补：
  - **原生粒度与喂入方式**：数据的自然单位（message/turn/session/operation/
    trajectory）、官方评测按什么顺序什么粒度喂给被测系统、需要哪些边界信号。
  - **成本画像**：官方流程每 sample 的 LLM/embedding/judge 调用量级。
  增补内容追加为独立小节并标注"2026-07-06 增补"，不改动原有结论。

  验收输出（2026-07-05，HaluMem）：

  ```bash
  $ python3 - <<'PY'
  import json
  from pathlib import Path
  for name in ['HaluMem-Medium.jsonl','HaluMem-Long.jsonl']:
      p=Path('data/halumem')/name
      users=sessions=turns=memories=questions=qa_sessions=0
      for line in p.read_text().splitlines():
          if not line.strip():
              continue
          users += 1
          obj=json.loads(line)
          for s in obj['sessions']:
              sessions += 1
              turns += len(s.get('dialogue',[]))
              memories += len(s.get('memory_points',[]))
              questions += len(s.get('questions',[]))
              qa_sessions += int(bool(s.get('questions')))
      print(name, 'users', users, 'sessions', sessions, 'turns', turns, 'memory_points', memories, 'questions', questions, 'qa_sessions', qa_sessions)
  PY
  HaluMem-Medium.jsonl users 20 sessions 1387 turns 60146 memory_points 14948 questions 3467 qa_sessions 896
  HaluMem-Long.jsonl users 20 sessions 2417 turns 107032 memory_points 14948 questions 3467 qa_sessions 896
  ```

  ```bash
  $ rg -n '2026-07-06 增补：原生粒度与喂入方式|2026-07-06 增补：成本画像|add\(conversation\)|get_dialogue_memory|top_k=10|3,467 QA' docs/survey/benchmarks/HaluMem.md
  406:### 6.4 2026-07-06 增补：原生粒度与喂入方式
  412:完整 HaluMem 需要三种输出/查询边界：add 后立刻记录本 session 新 `extracted_memories`；update eval 用 gold `memory_content` 检索当前 user 全局 state，`top_k=10`；QA eval 用 `qa.question` 检索，wrapper 传入的 `top_k` 默认来自脚本参数，已有说明中 Mem0 QA 默认为 20。证据：`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:204-219`、`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:231-247`。
  414:因此 `add(conversation)` 若只返回成功状态，最多覆盖 QA 子集；要覆盖 operation-level 评测，adapter 需要把 session-specific extracted memories 暴露给 scorer，或提供 `get_dialogue_memory(user_id, session_id)` 等价接口。官方 README 也说明各 wrapper 应遵循相同 artifact contract，Zep 因缺 Get Dialogue Memory API 无法准确评估 extraction。证据：`third_party/benchmarks/HaluMem-main/eval/README.md:81-92`、`third_party/benchmarks/HaluMem-main/eval/README.md:137-141`。
  416:### 6.5 2026-07-06 增补：成本画像
  418:本地最终数据规模为 Medium 20 users / 1,387 sessions / 60,146 dialogue turns / 14,948 memory points / 3,467 QA pairs，Long 20 users / 2,417 sessions / 107,032 dialogue turns / 14,948 memory points / 3,467 QA pairs。证据：本轮验收命令读取 `data/halumem/HaluMem-Medium.jsonl` 与 `data/halumem/HaluMem-Long.jsonl`。
  420:单 session 的 method 成本至少包含一次 add dialogue；若 session 含 update memory points，则每个 update point 触发一次 `top_k=10` retrieval；若 session 含 QA，则每个 question 触发一次 retrieval、一次 answer LLM。证据：`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:189-194`、`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:215-220`、`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:233-252`。
  ```

	  ```bash
	  $ git diff --check -- docs/survey/benchmarks/HaluMem.md docs/workstreams/ws02-phase1-matrix/plan-track-b0-benchmark-cards.md && git status --short -- pyproject.toml uv.lock .venv package.json bun.lock node_modules
	  ```

	  验收输出（2026-07-05，BEAM）：

	  ```bash
	  $ uv run python - <<'PY'
	  from datasets import load_from_disk
	  from ast import literal_eval
	  for path in ['data/BEAM/beam_dataset','data/BEAM/beam_10M_dataset']:
	      ds = load_from_disk(path)
	      print(path)
	      print(ds)
	      for split in ds:
	          d=ds[split]
	          print(split, 'rows', len(d), 'columns', sorted(d.column_names))
	          row=d[0]
	          pq=row.get('probing_questions')
	          if isinstance(pq, str):
	              parsed=literal_eval(pq)
	          else:
	              parsed=pq
	          q_counts={k: len(v) for k,v in parsed.items()} if isinstance(parsed, dict) else {}
	          print(' first_id', row.get('conversation_id'))
	          print(' probing_counts', q_counts, 'total', sum(q_counts.values()))
	          chat=row.get('chat')
	          print(' chat_type', type(chat).__name__, 'len', len(chat) if hasattr(chat,'__len__') else None)
	          if chat:
	              print(' chat0_type', type(chat[0]).__name__)
	              if isinstance(chat[0], dict):
	                  print(' chat0_keys', sorted(chat[0].keys()))
	                  turns=chat[0].get('turns')
	                  print(' chat0_turns', len(turns) if turns is not None else None)
	                  if turns:
	                      print(' first_turn_messages', len(turns[0]))
	                      print(' first_message_keys', sorted(turns[0][0].keys()))
	              elif isinstance(chat[0], list):
	                  print(' chat0_len', len(chat[0]))
	          plans=row.get('plans')
	          if plans is not None:
	              print(' plans_type', type(plans).__name__, 'len', len(plans) if hasattr(plans,'__len__') else None)
	  PY
	  data/BEAM/beam_dataset
	  DatasetDict({
	      100K: Dataset({
	          features: ['conversation_id', 'conversation_seed', 'narratives', 'user_profile', 'conversation_plan', 'user_questions', 'chat', 'probing_questions'],
	          num_rows: 20
	      })
	      500K: Dataset({
	          features: ['conversation_id', 'conversation_seed', 'narratives', 'user_profile', 'conversation_plan', 'user_questions', 'chat', 'probing_questions'],
	          num_rows: 35
	      })
	      1M: Dataset({
	          features: ['conversation_id', 'conversation_seed', 'narratives', 'user_profile', 'conversation_plan', 'user_questions', 'chat', 'probing_questions'],
	          num_rows: 35
	      })
	  })
	  100K rows 20 columns ['chat', 'conversation_id', 'conversation_plan', 'conversation_seed', 'narratives', 'probing_questions', 'user_profile', 'user_questions']
	   first_id 1
	   probing_counts {'abstention': 2, 'contradiction_resolution': 2, 'event_ordering': 2, 'information_extraction': 2, 'instruction_following': 2, 'knowledge_update': 2, 'multi_session_reasoning': 2, 'preference_following': 2, 'summarization': 2, 'temporal_reasoning': 2} total 20
	   chat_type list len 3
	   chat0_type list
	   chat0_len 60
	  500K rows 35 columns ['chat', 'conversation_id', 'conversation_plan', 'conversation_seed', 'narratives', 'probing_questions', 'user_profile', 'user_questions']
	   first_id 1
	   probing_counts {'abstention': 2, 'contradiction_resolution': 2, 'event_ordering': 2, 'information_extraction': 2, 'instruction_following': 2, 'knowledge_update': 2, 'multi_session_reasoning': 2, 'preference_following': 2, 'summarization': 2, 'temporal_reasoning': 2} total 20
	   chat_type list len 10
	   chat0_type list
	   chat0_len 82
	  1M rows 35 columns ['chat', 'conversation_id', 'conversation_plan', 'conversation_seed', 'narratives', 'probing_questions', 'user_profile', 'user_questions']
	   first_id 1
	   probing_counts {'abstention': 2, 'contradiction_resolution': 2, 'event_ordering': 2, 'information_extraction': 2, 'instruction_following': 2, 'knowledge_update': 2, 'multi_session_reasoning': 2, 'preference_following': 2, 'summarization': 2, 'temporal_reasoning': 2} total 20
	   chat_type list len 10
	   chat0_type list
	   chat0_len 160
	  data/BEAM/beam_10M_dataset
	  DatasetDict({
	      10M: Dataset({
	          features: ['conversation_id', 'conversation_seed', 'narratives', 'user_profile', 'conversation_plan', 'user_questions', 'chat', 'probing_questions', 'plans'],
	          num_rows: 10
	      })
	  })
	  10M rows 10 columns ['chat', 'conversation_id', 'conversation_plan', 'conversation_seed', 'narratives', 'plans', 'probing_questions', 'user_profile', 'user_questions']
	   first_id 1
	   probing_counts {'abstention': 2, 'contradiction_resolution': 2, 'event_ordering': 2, 'information_extraction': 2, 'instruction_following': 2, 'knowledge_update': 2, 'multi_session_reasoning': 2, 'preference_following': 2, 'summarization': 2, 'temporal_reasoning': 2} total 20
	   chat_type list len 10
	   chat0_type dict
	   chat0_keys ['plan-1', 'plan-10', 'plan-2', 'plan-3', 'plan-4', 'plan-5', 'plan-6', 'plan-7', 'plan-8', 'plan-9']
	   chat0_turns None
	   plans_type list len 10
	  ```

	  ```bash
	  $ rg -n '2026-07-06 增补：原生粒度与喂入方式|2026-07-06 增补：成本画像|add\(conversation\)|add_turn|2,000 validated questions|LLM equivalence' docs/survey/benchmarks/BEAM.md
	  29:- method 侧第一版仍可维持 `add(conversation) + retrieve(question)`。
	  33:- 1M / 10M 会对一次性 `add(conversation)` 造成工程压力，未来可能需要框架内部支持
	  416:LLM equivalence detector 对齐 reference / system events
	  554:add(conversation)
	  560:- `add(conversation)` 写入完整 BEAM conversation。
	  600:| `add(conversation)` | 需要 | 每个 sample 是一条完整超长 conversation |
	  617:- event-ordering metric：Kendall tau-b + LLM equivalence alignment。
	  622:### 6.6 2026-07-06 增补：原生粒度与喂入方式
	  639:对当前 retrieve-first 协议，BEAM 仍可映射为 `add(conversation)` 一次写入完整
	  643:引入 `add_turn(...)`，BEAM 应按原始生成顺序流式喂入：普通 split 为
	  647:### 6.7 2026-07-06 增补：成本画像
	  649:完整 BEAM 规模是 100 conversations、2,000 validated questions：`128K/100K` 20
	  667:event ordering 还会做 LLM equivalence 对齐和 Kendall tau-b/F1 组合分。官方本地
	  ```

	  ```bash
	  $ git diff --check -- docs/survey/benchmarks/BEAM.md docs/workstreams/ws02-phase1-matrix/plan-track-b0-benchmark-cards.md && git status --short -- pyproject.toml uv.lock .venv package.json bun.lock node_modules
	  ```

	  验收输出（2026-07-05，MemBench）：

	  ```bash
	  $ uv run python - <<'PY'
	  import json, collections
	  from pathlib import Path
	  base=Path('data/membench/Membenchdata/data2test')
	  files=[
	   '0-10k/FirstAgentDataHighLevel_multiple_0.json',
	   '0-10k/FirstAgentDataLowLevel_multiple_0.json',
	   '0-10k/ThirdAgentDataHighLevel_multiple_0.json',
	   '0-10k/ThirdAgentDataLowLevel_multiple_0.json',
	   '100k/FirstAgentDataHighLevel_multiple_100.json',
	   '100k/FirstAgentDataLowLevel_multiple_100.json',
	   '100k/ThirdAgentDataHighLevel_multiple_100.json',
	   '100k/ThirdAgentDataLowLevel_multiple_100.json',
	  ]
	  for rel in files:
	      path=base/rel
	      data=json.loads(path.read_text())
	      trajs=[]; qt=collections.Counter(); scen=collections.Counter(); msg_types=collections.Counter(); target_lens=[]
	      for qtype, scenarios in data.items():
	          for scenario, arr in scenarios.items():
	              for traj in arr:
	                  trajs.append(traj); qt[qtype]+=1; scen[scenario]+=1
	                  ml=traj.get('message_list') or []
	                  if ml:
	                      msg_types[type(ml[0]).__name__]+=1
	                  target_lens.append(len(traj.get('QA',{}).get('target_step_id') or []))
	      msg_counts=[len(t.get('message_list') or []) for t in trajs]
	      print(rel)
	      print(' trajectories', len(trajs), 'question_types', dict(sorted(qt.items())), 'scenarios', dict(sorted(scen.items())))
	      print(' message_count_range', min(msg_counts), max(msg_counts), 'total_messages', sum(msg_counts), 'first_message_types', dict(sorted(msg_types.items())))
	      print(' target_step_id_len_range', min(target_lens), max(target_lens), 'qa_fields', sorted(trajs[0]['QA'].keys()))
	      print(' sample_fields', sorted(trajs[0].keys()))
	  PY
	  0-10k/FirstAgentDataHighLevel_multiple_0.json
	   trajectories 700 question_types {'highlevel': 400, 'highlevel_rec': 300} scenarios {'book': 200, 'emotion': 100, 'food': 200, 'movie': 200}
	   message_count_range 8 44 total_messages 15450 first_message_types {'dict': 700}
	   target_step_id_len_range 0 5 qa_fields ['answer', 'choices', 'ground_truth', 'qid', 'question', 'target_step_id', 'time']
	   sample_fields ['QA', 'message_list', 'tid']
	  0-10k/FirstAgentDataLowLevel_multiple_0.json
	   trajectories 900 question_types {'RecMultiSession': 50, 'aggregative': 100, 'comparative': 100, 'conditional': 100, 'knowledge_update': 100, 'lowlevel_rec': 150, 'noisy': 100, 'post_processing': 100, 'simple': 100} scenarios {'book': 50, 'events': 350, 'food': 50, 'movie': 50, 'multi_agent': 50, 'roles': 350}
	   message_count_range 13 193 total_messages 104470 first_message_types {'dict': 900}
	   target_step_id_len_range 1 10 qa_fields ['answer', 'choices', 'ground_truth', 'qid', 'question', 'target_step_id', 'time']
	   sample_fields ['QA', 'message_list', 'tid']
	  0-10k/ThirdAgentDataHighLevel_multiple_0.json
	   trajectories 400 question_types {'highlevel': 400} scenarios {'book': 100, 'emotion': 100, 'food': 100, 'movie': 100}
	   message_count_range 6 23 total_messages 5302 first_message_types {'str': 400}
	   target_step_id_len_range 2 5 qa_fields ['answer', 'choices', 'ground_truth', 'qid', 'question', 'target_step_id', 'time']
	   sample_fields ['QA', 'message_list', 'tid']
	  0-10k/ThirdAgentDataLowLevel_multiple_0.json
	   trajectories 1400 question_types {'aggregative': 150, 'comparative': 150, 'conditional': 250, 'knowledge_update': 100, 'noisy': 250, 'post_processing': 250, 'simple': 250} scenarios {'events': 350, 'hybrid': 300, 'items': 200, 'places': 200, 'roles': 350}
	   message_count_range 4 36 total_messages 19285 first_message_types {'str': 1400}
	   target_step_id_len_range 1 18 qa_fields ['answer', 'choices', 'ground_truth', 'qid', 'question', 'target_step_id', 'time']
	   sample_fields ['QA', 'message_list', 'tid']
	  100k/FirstAgentDataHighLevel_multiple_100.json
	   trajectories 140 question_types {'highlevel': 80, 'highlevel_rec': 60} scenarios {'book': 40, 'emotion': 20, 'food': 40, 'movie': 40}
	   message_count_range 309 341 total_messages 45133 first_message_types {'dict': 140}
	   target_step_id_len_range 1 5 qa_fields ['answer', 'choices', 'ground_truth', 'qid', 'question', 'target_step_id', 'time']
	   sample_fields ['QA', 'message_list', 'tid']
	  100k/FirstAgentDataLowLevel_multiple_100.json
	   trajectories 360 question_types {'RecMultiSession': 20, 'aggregative': 40, 'comparative': 40, 'conditional': 40, 'knowledge_update': 40, 'lowlevel_rec': 60, 'noisy': 40, 'post_processing': 40, 'simple': 40} scenarios {'book': 20, 'events': 140, 'food': 20, 'movie': 20, 'multi_agent': 20, 'roles': 140}
	   message_count_range 313 491 total_messages 149777 first_message_types {'dict': 360}
	   target_step_id_len_range 1 10 qa_fields ['answer', 'choices', 'ground_truth', 'qid', 'question', 'target_step_id', 'time']
	   sample_fields ['QA', 'message_list', 'tid']
	  100k/ThirdAgentDataHighLevel_multiple_100.json
	   trajectories 80 question_types {'highlevel': 80} scenarios {'book': 20, 'emotion': 20, 'food': 20, 'movie': 20}
	   message_count_range 307 321 total_messages 25049 first_message_types {'str': 80}
	   target_step_id_len_range 2 5 qa_fields ['answer', 'choices', 'ground_truth', 'qid', 'question', 'target_step_id', 'time']
	   sample_fields ['QA', 'message_list', 'tid']
	  100k/ThirdAgentDataLowLevel_multiple_100.json
	   trajectories 280 question_types {'aggregative': 30, 'comparative': 30, 'conditional': 50, 'knowledge_update': 20, 'noisy': 50, 'post_processing': 50, 'simple': 50} scenarios {'events': 70, 'hybrid': 60, 'items': 40, 'places': 40, 'roles': 70}
	   message_count_range 303 336 total_messages 87779 first_message_types {'str': 280}
	   target_step_id_len_range 1 18 qa_fields ['answer', 'choices', 'ground_truth', 'qid', 'question', 'target_step_id', 'time']
	   sample_fields ['QA', 'message_list', 'tid']
	  ```

	  ```bash
	  $ rg -n '2026-07-06 增补：原生粒度与喂入方式|2026-07-06 增补：成本画像|trajectory|message_list|store latency|3,400 trajectories|307,738 message store' docs/survey/benchmarks/MemBench.md
	  9:它比 LoCoMo 更接近“trajectory 环境”：每个 `tid` 是一条独立评测样本，`message_list` 是需要逐步写入的 memory stream，`QA` 是最终测试问题。当前 `add + retrieve` 架构可以覆盖它，但必须保证 **tid namespace 隔离** 和 **retrieved source step id provenance**；否则 Recall 无法计算，且不同 trajectory 会互相污染。
	  25:本地 `data2test` 是评测层 trajectory 数据。直接统计如下：
	  403:### 6.4 2026-07-06 增补：原生粒度与喂入方式
	  405:MemBench 的自然单位不是一整段静态 conversation，而是一条独立 trajectory：
	  406:`trajectory -> message_list step -> final QA`。官方 `MemBenchEnv.reset(traj_i)` 会选择一条
	  418:官方喂入方式是每条 trajectory 开始前 `memory.reset()`，每个 message step 调用一次
	  432:### 6.5 2026-07-06 增补：成本画像
	  434:本地 `data2test` 主评文件分两档：`0-10k` 四个文件合计 3,400 trajectories / 144,507
	  435:message store steps，`100k` 四个文件合计 860 trajectories / 307,738 message store
	  457:MemBench 成本时不能只写 answer LLM 次数，还要分开记录 store latency、read latency、
	  ```

	  ```bash
	  $ git diff --check -- docs/survey/benchmarks/MemBench.md docs/workstreams/ws02-phase1-matrix/plan-track-b0-benchmark-cards.md && git status --short -- pyproject.toml uv.lock .venv package.json bun.lock node_modules
	  ```

### 收尾

- [x] 在 `docs/survey/benchmarks/README.md` 索引中登记两张新卡片。
- [x] 更新 ws02 README 断点，通知架构师做粒度矩阵。

  验收输出（2026-07-05，收尾）：

  ```bash
  $ ls docs/survey/benchmarks/*.md
  docs/survey/benchmarks/BEAM.md
  docs/survey/benchmarks/HaluMem.md
  docs/survey/benchmarks/LoCoMo.md
  docs/survey/benchmarks/LongMemEval.md
  docs/survey/benchmarks/MemBench.md
  docs/survey/benchmarks/MemoryAgentBench.md
  docs/survey/benchmarks/MemoryArena.md
  docs/survey/benchmarks/MemoryBench.md
  docs/survey/benchmarks/PersonaMem.md
  docs/survey/benchmarks/README.md
  docs/survey/benchmarks/meeting-brief-7-benchmarks.md
  ```

  ```bash
  $ rg -n '原生粒度|成本画像' docs/survey/benchmarks/LoCoMo.md docs/survey/benchmarks/LongMemEval.md docs/survey/benchmarks/HaluMem.md docs/survey/benchmarks/BEAM.md docs/survey/benchmarks/MemBench.md
  docs/survey/benchmarks/HaluMem.md:406:### 6.4 2026-07-06 增补：原生粒度与喂入方式
  docs/survey/benchmarks/HaluMem.md:416:### 6.5 2026-07-06 增补：成本画像
  docs/survey/benchmarks/MemBench.md:403:### 6.4 2026-07-06 增补：原生粒度与喂入方式
  docs/survey/benchmarks/MemBench.md:432:### 6.5 2026-07-06 增补：成本画像
  docs/survey/benchmarks/LoCoMo.md:53:原生粒度是 `conversation -> session -> turn -> question`。`add(conversation)` 能一次性传入完整历史，当前 adapter 已按 sample 构造 `Conversation`，并把 session 时间、turn id、speaker、图片 caption/URL 转成统一模型；这适合 retrieve-first 主协议。证据：`src/memory_benchmark/benchmark_adapters/locomo.py:94`、`src/memory_benchmark/benchmark_adapters/locomo.py:134`、`src/memory_benchmark/benchmark_adapters/locomo.py:448`。
  docs/survey/benchmarks/LoCoMo.md:59:成本画像：完整当前 adapter 口径为 1,540 个非 adversarial 问题，每题至少一次 reader LLM 调用；method 侧成本取决于 `add(conversation)` 的 ingest 和 `retrieve(question)` 的检索。官方 RAG 口径还包含建库 context embeddings、question embeddings 和每题 answer LLM；非 RAG 官方批量模式会减少 answer 调用次数，但把更长上下文塞给 reader。证据：本卡验收命令的 category 5 差值；`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:97`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:122`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:225`。
  docs/survey/benchmarks/BEAM.md:622:### 6.6 2026-07-06 增补：原生粒度与喂入方式
  docs/survey/benchmarks/BEAM.md:647:### 6.7 2026-07-06 增补：成本画像
  docs/survey/benchmarks/LongMemEval.md:57:原生粒度是 `evaluation instance -> haystack session -> user/assistant turn -> single question`。`add(conversation)` 可以完整承载一个 instance 的历史，要求每个 question_id 对应独立 method state，避免不同用户/世界串扰。证据：`third_party/benchmarks/LongMemEval-main/README.md:79`、`src/memory_benchmark/benchmark_adapters/longmemeval.py:198`。
  docs/survey/benchmarks/LongMemEval.md:63:成本画像：完整 S variant 是 500 conversation / 500 question；当前框架每题至少 1 次 method retrieve、1 次 framework answer LLM、1 次 LongMemEval judge LLM。method ingest 成本随 S/M history 长度和 method 机制剧烈变化。证据：`third_party/benchmarks/LongMemEval-main/README.md:79`、`src/memory_benchmark/evaluators/longmemeval_judge.py:117`。
  ```

  ```bash
  $ git status --short -- pyproject.toml uv.lock .venv package.json bun.lock node_modules
  ```

  ```bash
  $ git status --short
   M docs/survey/benchmarks/README.md
   D docs/survey/benchmarks/meeting-brief-5-benchmarks.md
   M docs/workstreams/ws02-phase1-matrix/README.md
  ?? docs/survey/benchmarks/meeting-brief-7-benchmarks.md
  ```

## 验收

- `ls docs/survey/benchmarks/*.md` 含 LoCoMo、LongMemEval 且 5 张目标 benchmark
  卡片全部具备"原生粒度与喂入方式 + 成本画像"内容。
- 新卡片每个结论有 文件/行号 或 dataset 字段证据；paper/code/dataset 冲突
  如实记录。
- 全程零 API；`git status` 干净（逐张 commit）。

## 明确不做

- 不改 adapter 代码；不重写三张已有卡片的既有结论；
- 不调研 Phase 1 之外的 benchmark（PersonaMem/MemoryArena 卡片已存在，不动）。
