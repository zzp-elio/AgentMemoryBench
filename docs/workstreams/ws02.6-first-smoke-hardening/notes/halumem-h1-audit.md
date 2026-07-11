# HaluMem B5 H1 一手资产与真实数据审计

> 审计日期：2026-07-11。Medium 与 Long 均按 JSONL 逐行 `json.loads`；Long
> 从未整文件载入内存。字节身份见 `halumem-source-lock.json`。

## 1. 来源与双 variant 剖面

- 官方仓库由 README 的 GitHub issues 链接反推 repository root：
  `https://github.com/MemTensor/HaluMem`（`README.md:8-9`）；本地快照无
  `.git`，commit **来源待溯**，不得把父项目 commit 当第三方 commit。
- 论文 arXiv `2511.03506`（`README.md:11-12,972-979`），数据发布页
  `IAAR-Shanghai/HaluMem`（`README.md:14-15,785`）。本地无 LICENSE 文件；
  README badge 声明 CC-BY-NC-ND-4.0（`README.md:5-6`）。

| variant | user | session | session/user | turn | turn/session | questions | 缺 questions 键 | generated QA session |
|---|---:|---:|---|---:|---|---:|---:|---:|
| Medium | 20 | 1,387 | 58-82 | 60,146 | 8-60 | 3,467 | 491 | 0 |
| Long | 20 | 2,417 | 106-140 | 107,032 | 2-94 | 3,467 | 491 | 1,030 |

Long 比 Medium 多出的 1,030 个 session 全带 `is_generated_qa_session=True`；
两者的非生成 memory points 与问题集合计数相同。六类问题在两个 variant 均为：

| question_type | count |
|---|---:|
| Memory Boundary | 828 |
| Basic Fact Recall | 746 |
| Memory Conflict | 769 |
| Generalization & Application | 746 |
| Multi-hop Inference | 198 |
| Dynamic Update | 180 |

14,948 个 memory point 的必现键为 `index,memory_content,memory_type,is_update,
original_memories,timestamp,importance,memory_source`。可选键频次：`reason /
source_memory_index/reference_memory_content/reference_memory_index/
reference_memory_type` 各 2,648，`event_source` 1,727，`role` 1。类型分布：
Persona 9,116 / Event 4,550 / Relationship 1,282；来源分布：secondary 10,451 /
interference 2,648 / system 1,849。

`is_update` 只出现字符串：`"False"` 11,826、`"True"` 3,122（每 variant；
双文件合计分别 23,652/6,244）。所有 `"True"` 均有非空
`original_memories`，所有 `"False"` 均为空。字符串 truthiness 会把
`"False"` 误判为真，是数据 quirk。

三层时间字段共 170,178 个 turn timestamp、3,804 个 session start_time 和
3,804 个 end_time，全部为非空字符串并匹配 `%b %d, %Y, %H:%M:%S`；官方
Mem0 路径也用该格式解析 session start_time（`eval_memzero.py:184-187`）。

## 2. Q1：is_update 语义

**判定：`is_update="True"` 表示该 gold memory point 更新既有记忆，但官方只在
它同时带非空 `original_memories` 时发起更新检索探针；首 session 的 15 个点实际
全为 `"False"`，属于普通 extraction。**

官方逐 memory point 检查，`"False"` 或空 `original_memories` 直接跳过；否则用
新 `memory_content` 作 query、`top_k=10` 检索，并把结果写入
`memories_from_system`（`eval_memzero.py:210-222`）。聚合端又只把
`is_update=="True"` 且探针有结果者路由到 update，其他点进入 integrity
（`evaluation.py:54-70`）。全量耦合统计没有反例。

## 3. Q2：evidence 形态与 recall 可用性

两个 variant 的 3,467 个 `evidence` 全是原生 list：828 空、2,639 非空。
非空列表合计 4,651 个元素，**全部**是恰含 `{memory_content,memory_type}` 的
dict；无字符串元素、无 index、无 turn id。按同 user 的 memory point 文本全量
对齐：3,354 个命中问题所在 session，1,297 个命中此前 session，未来 session
命中 0，未匹配 0。Medium 与 Long 数字相同。

抽样：`{"memory_content":"Martin Mark's birth date is 1996-08-02",
"memory_type":"Persona Memory"}`。官方 QA judge 将每个 evidence dict 的
`memory_content` 换行拼接为 Key Memory Points（`evaluation.py:176-185`）。

**结论：evidence 是结构化 memory-point gold，可直接供 QA judge；它没有公开
turn-id/provenance 映射，不能直接作为现行 turn-level retrieval recall gold。**
若 H4 需要 recall，应记 N/A/known limitation，不能凭文本相似度自行制造 turn id。

## 4. Q3：canonical QA prompt

实际调用点而非常量数量决定语义：

| 脚本 | 实际 prompt | 证据 |
|---|---|---|
| Mem0 | `PROMPT_MEMZERO` | `eval_memzero.py:21,244-247` |
| Memobase | `PROMPT_MEMZERO` | `eval_memobase.py:24,305-308` |
| MemOS | `PROMPT_MEMOS` | `eval_memos.py:22,237-240` |
| Supermemory | `PROMPT_MEMOS` | `eval_supermemory.py:23,254-257` |
| Zep | `PROMPT_ZEP` | `eval_zep.py:24,403-406` |

严格记忆族为 MEMZERO×2 + ZEP（3/5）；宽松族 MEMOS×2 在第 4 条允许 general
world knowledge（`prompts.py:89,100`）。架构师裁定 unified canonical 为
`PROMPT_MEMZERO`：多数派严格语义与 hallucination 测量目标一致。框架当前
`HALUMEM_MEMZERO_PROMPT` 与官方常量 AST 值逐字相等（2,104 字符，差异 0）；
H3 仍负责运行时 parity 测试。`PROMPT_MEMOBASE`（`prompts.py:111-142`）无调用方，
因为 Memobase 实际 import MEMZERO，是官方死代码。已知偏差：官方 MemOS/
Supermemory 数字使用宽松 prompt，框架统一数字与其不可直接视作 prompt-parity。

## 5. 论文指标覆盖清单

论文把 extraction、update、QA 三阶段定义在 PDF 第 9 页；README 表头列出同一
12 项（`README.md:88-99,107-123`）。以下公式按**实际聚合调用点**
`evaluation.py:214-362` 核对，而非函数签名推断；judge prompt 本体分别在
`eval_tools.py:4-65,68-158,161-215,218-283`，调用点在
`evaluation.py:104-197`。

| 阶段/指标 | all 分母与公式 | 现有 evaluator |
|---|---|---|
| Extraction R | 非 interference 应抽 gold 数；score==2 数/总数 | 已覆盖 |
| Extraction Weighted R | `sum(0.5*score*importance)/sum(importance)` | 已覆盖 |
| Target P | included candidate 的 `sum(0.5*accuracy_score)/count` | 已覆盖 |
| Accuracy | 全 candidate 的 `sum(0.5*accuracy_score)/count` | 已覆盖 |
| FMR | interference gold 中 integrity score==0 数/总数 | 已覆盖 |
| Extraction F1 | `2*TargetP*R/(TargetP+R)` | 已覆盖 |
| Update Correct | Correct/全部 update probe | 已覆盖 |
| Update Hallucination | Hallucination/全部 update probe | 已覆盖 |
| Update Omission | Omission/全部 update probe | 已覆盖 |
| QA Correct | Correct/全部 QA | 已覆盖 |
| QA Hallucination | Hallucination/全部 QA | 已覆盖 |
| QA Omission | Omission/全部 QA | 已覆盖 |

代码同时输出各项 `valid` 分母版本，update 还输出 `Other`；它们是官方代码的
诊断字段，但不是论文表头新增主指标。**覆盖统计：12/12 主指标已有实现，缺失 0；
12 项都依赖的四套 judge prompt 在现有 evaluator 中被缩写，属于 prompt-parity
偏差，须由 H4 逐字修正后才能宣称官方 parity。**此外，官方按 memory_type 的
聚合使用 extraction/update 共同 `total_num` 作两项分母（`evaluation.py:364-383`），
现有 extraction 仅报 integrity recall breakdown，故该论文附加分析维度尚未覆盖；
它不计入表 3 的 12 项主指标，但 H4 应处理或冻结为限制。

## 5.1 H4 三阶段 metric parity 补录

### Recall 冻结裁定

HaluMem retrieval recall 记为 N/A，不注册 recall evaluator。数据的
evidence 只有 memory point 文本和类型，无公开 turn id；官方调用点仅将
`qa["evidence"]` 中的 `memory_content` 拼为 QA judge 的 Key Memory Points
（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:178-185`）。用文本相似度
反推 turn gold 会制造官方不存在的映射，故作为 frozen-v1 known limitation。

### Judge prompt parity

| prompt | 缩写版长度 | 官方逐字版长度 | 运行时锁定 |
|---|---:|---:|---|
| Memory Integrity | 214 | 2,568 | `test_halumem_judge_prompt_matches_official_ast_value` |
| Memory Accuracy | 267 | 4,891 | 同上 |
| Update Memory | 325 | 2,259 | 同上 |
| Question Answering | 339 | 3,834 | 同上 |

四套模板现由 `halumem_prompts.py` 保存，测试每次现场 AST 读取
`eval/eval_tools.py:4-283` 的官方常量并比对长度与全文。结果解析保持
官方调用点语义：integrity/accuracy 分数转 int，update/QA 直接消费
`evaluation_result`（`evaluation.py:119-197`）。

### 聚合复审

| 项目 | H4 结论 | 官方调用点 |
|---|---|---|
| Extraction R / valid R | 一致；排除 interference，score==2 计中 | `evaluation.py:214-246` |
| Weighted R / valid | 一致；`0.5*score*importance` | `evaluation.py:228-244` |
| FMR all / valid | 一致；interference score==0 计中 | `evaluation.py:234-250` |
| Target P all / valid | 一致；仅 included candidate，`0.5*score` | `evaluation.py:252-282` |
| Accuracy all / valid | 一致；全 candidate，`0.5*score` | `evaluation.py:263-286` |
| Extraction F1 | 一致；用 all Target P 与 all R | `evaluation.py:288-292` |
| Update | 一致；保留 all/valid 与 Other 诊断类 | `evaluation.py:294-330` |
| QA | 一致；保留 all/valid 三分类 | `evaluation.py:332-362` |
| memory_type | H4 新增离线合成指标，integrity/update 共用 `total_num`，两贡献相加 | `evaluation.py:364-383` |

`valid` 与 update `Other` 是官方诊断字段，不冒充论文 12 项主指标。
`halumem-memory-type` 只读真实 extraction/update score artifacts，不调 judge；
任一上游文件缺失时 fail-fast。阶段内 per-type breakdown 保留，并显式标注
与官方共享分母不同。

### 0 分母契约

| 阶段 | 空分母输出 | 显式计数 |
|---|---|---|
| Extraction | 所有比率与 F1 为 `None` | `memory_num` / `memory_valid_num` 等为 0 |
| Update | all/valid 四类比率为 `None` | `update_memory_num` / `update_memory_valid_num` 为 0 |
| QA | all/valid 三类比率为 `None` | `qa_num` / `qa_valid_num` 为 0 |

顶层 runner `mean_score` 因现有数值 schema 保留兼容值 `0.0`；官方比率语义在
`overall_score` 中用 `None + count` 无歧义表达。

## 6. 可复算脚本

```python
import hashlib, json, re
from collections import Counter
from pathlib import Path

TIME = re.compile(r"^[A-Z][a-z]{2} \\d{2}, \\d{4}, \\d{2}:\\d{2}:\\d{2}$")
for path in map(Path, ["data/halumem/HaluMem-Medium.jsonl",
                       "data/halumem/HaluMem-Long.jsonl"]):
    count = Counter(); qtypes = Counter(); evidence = Counter()
    for line in path.open(encoding="utf-8"):  # Long 逐行流式
        if not line.strip():
            continue
        user = json.loads(line); count["users"] += 1
        all_contents = {m.get("memory_content") for s in user["sessions"]
                        for m in s.get("memory_points", [])}
        seen = set()
        for session in user["sessions"]:
            count["sessions"] += 1; count["turns"] += len(session["dialogue"])
            count["missing_questions"] += "questions" not in session
            assert all(TIME.match(t["timestamp"]) for t in session["dialogue"])
            current = {m.get("memory_content") for m in session.get("memory_points", [])}
            for m in session.get("memory_points", []):
                count[f"update:{m['is_update']}"] += 1
                assert (m["is_update"] == "True") == bool(m["original_memories"])
            for q in session.get("questions", []):
                count["questions"] += 1; qtypes[q["question_type"]] += 1
                assert isinstance(q["evidence"], list)
                evidence["empty" if not q["evidence"] else "nonempty"] += 1
                for item in q["evidence"]:
                    assert set(item) == {"memory_content", "memory_type"}
                    if item["memory_content"] in current:
                        evidence["same"] += 1
                    elif item["memory_content"] in seen:
                        evidence["prior"] += 1
                    assert item["memory_content"] in all_contents
            seen.update(current)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024): digest.update(chunk)
    print(path, count, qtypes, evidence, path.stat().st_size, digest.hexdigest())
```

## 7. H3：unified prompt parity 与 answer 归一

运行时 parity 测试落在 `tests/test_halumem_unified_prompt.py`：每次测试现场读取
官方 `eval/prompts.py`，经 AST 提取 `PROMPT_MEMZERO`，同时锁定 2,104 字符
长度与全文逐字相等。builder 测试以超长、含原始换行的 `formatted_memory`
断言只作 `{context}` 原样替换，不重排、不截断，也不二次拼装官方 Mem0
检索路径的 `{timestamp}: {memory}` 排版。canonical 与原样代入均采用 H1
架构师裁决；官方 Mem0 的排版发生在 `eval_memzero.py:115-130`，不属于统一
reader 的职责。

| 参数 | 官方值 | 框架值 | 一手出处 |
|---|---|---|---|
| model | 环境变量 `OPENAI_MODEL`，无固定模型名 | `gpt-4o-mini`（Phase 1 统一政策） | `llms.py:20-22,60-62` |
| message role | `user` | `user` | `llms.py:60-68` |
| temperature | 仅 `OPENAI_TEMPERATURE` 存在时注入，否则 API 默认 | `None`（不传，API 默认） | `llms.py:25-31,60-69` |
| max_tokens | 仅 `OPENAI_MAX_TOKENS` 存在时注入，否则 API 默认 | `None`（不传，API 默认） | `llms.py:25-31,60-69` |
| top_p | 未设置 | `None`（不传，API 默认） | `llms.py:25-35,60-69` |
| n | 未设置 | SDK 默认（框架 `AnswerLLMSettings` 无显式 n 字段） | `llms.py:60-69` |
| timeout | 仅 `OPENAI_TIMEOUT` 存在时注入，否则 SDK 默认 | 60 秒（框架统一网络政策，非官方值） | `llms.py:33-34,60-69` |
| retry | `RETRY_TIMES` 环境变量控制 tenacity 尝试次数 | 8（框架统一网络政策，非官方值） | `llms.py:15-18,43-47` |

QA 实际调用点只执行 `PROMPT_MEMZERO.format(context=..., question=...)` 后调用
`llm_request(prompt)`，没有局部采样参数覆盖（`eval_memzero.py:244-250`）。因此
HaluMem 的 answer 配置按 benchmark 单键归一，跨 method 一致；官方未设置的
采样项按 API 默认处理，不把框架选择冒充官方值。
