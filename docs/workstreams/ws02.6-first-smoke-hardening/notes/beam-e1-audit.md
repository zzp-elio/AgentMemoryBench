# BEAM B4 E1 一手资产与真实数据审计

> 审计日期：2026-07-11。数据使用 `datasets.load_from_disk` 全量扫描；
> `probing_questions` 仅用 `ast.literal_eval`。位置索引一律为 **0 基**，并同时记录
> `conversation_id`。逐文件身份见 `beam-source-lock.json`。

## 1. 官方资产与四 split 规模

- 官方代码仓库：`https://github.com/mohammadtavakoli78/BEAM`，本地 remote 证据
  `third_party/benchmarks/BEAM/.git/config:8-10`；论文 PDF 也内嵌同一链接。
- 论文：arXiv `2510.27246`，证据 `third_party/benchmarks/BEAM/README.md:7-18,272-282`。
- 数据：`Mohammadta/BEAM` 与 `Mohammadta/BEAM-10M`，证据
  `third_party/benchmarks/BEAM/README.md:10-15,92-100`。
- 代码 LICENSE 为 MIT（`third_party/benchmarks/BEAM/LICENSE:1-20`）；数据卡声明
  CC-BY-SA-4.0（`data/BEAM/beam_dataset/README.md:73`）。二者不可混写。

| split | conv | session/conv 分布 | turn 总数 | turn/conv 分布摘要 | questions |
|---|---:|---|---:|---|---:|
| 100K | 20 | 3×5 conv；5×15 conv | 5,732 | 188-392；268×2，其余 18 个值各×1 | 400 |
| 500K | 35 | 10×35 conv | 38,058 | 772-1,424；1,122×2，其余 33 个值各×1 | 700 |
| 1M | 35 | 10×35 conv | 74,630 | 1,556-3,008；2,356×2，其余 33 个值各×1 | 700 |
| 10M | 10 | 顶层 10 个 plan group；每个 `plans[]` 均 10 sessions | 208,696 | 18,760-23,716（按顶层聚合 chat） | 200 |

前三个 split 的 turn 键形态恒为
`{content,id,index,question_type,role,time_anchor}`。10M 顶层 `chat` **不是**
`list[list[turn]]`，而是 10 个单有效键字典组成的 `list[dict]`：位置 `i` 的有效键
为 `plan-{i+1}`，值为 batch 列表，每个 batch 再含 `turns` 分组。证据代码按同一
形态取 `chat[first_plan_number-1][f'plan-{first_plan_number}']`：
`third_party/benchmarks/BEAM/src/beam/ten_milion_pipeline.py:1436-1440`。

四 split 每个 conversation 均恰有 10 类、每类 2 题，合计 2,000 题。rubric 条数
分布：`1:712, 2:428, 3:160, 4:306, 5:149, 6:60, 7:37, 8:52,
9:27, 10:52, 11:6, 12:6, 13:1, 20:4`。

Difficulty 全库分布（值域也由此完整列出）：abstention=`easy 34/hard 60/medium
106`；contradiction_resolution=`clear 200`；event_ordering=`easy 36/hard 79/
medium 85`；information_extraction=`easy 93/hard 53/medium 54`；
instruction_following=`medium 200`；knowledge_update=`easy 181/moderate 19`；
multi_session_reasoning=`easy 125/hard 47/medium 28`；preference_following=
`medium 200`；summarization=`空串 1/easy 42/hard 51/medium 106`；
temporal_reasoning=`easy 160/hard 1/medium 39`。

## 2. 私有字段黑名单与时间格式

以下逐类列出 `question` 之外的**全部**真实键，均按私有 gold 处理：

| ability | question 之外的键 |
|---|---|
| abstention | `abstention_type, difficulty, ideal_response, plan_reference, rubric, why_unanswerable` |
| contradiction_resolution | `contradiction_type, conversation_references, difficulty, ideal_answer, plan_reference, rubric, source_chat_ids, tests_for, topic_questioned` |
| event_ordering | `answer, complexity_factors, conversation_references, difficulty, ordering_tested, ordering_type, plan_reference, rubric, source_chat_ids, total_mentions` |
| information_extraction | `answer, conversation_reference, difficulty, extraction_challenge, key_facts_tested, plan_reference, question_type, rubric, source_chat_ids` |
| instruction_following | `compliance_indicators, difficulty, expected_compliance, instruction_being_tested, instruction_type, non_compliance_signs, plan_reference, rubric, source_chat_ids` |
| knowledge_update | `answer, conversation_references, difficulty, plan_reference, potential_confusion, rubric, source_chat_ids, tests_retention_of, update_type` |
| multi_session_reasoning | `answer, conversation_references, difficulty, plan_reference, reasoning_steps, reasoning_type, rubric, sessions_required, source_chat_ids` |
| preference_following | `compliance_indicators, difficulty, expected_compliance, non_compliance_signs, plan_reference, preference_being_tested, preference_type, rubric, source_chat_ids` |
| summarization | `bullet_points_covered, conversation_sessions, difficulty, ideal_summary, key_elements_tested, plan_reference, rubric, source_chat_ids, summarization_type, synthesis_required` |
| temporal_reasoning | `answer, calculation_required, complexity_factors, conversation_references, difficulty, plan_reference, rubric, source_chat_ids, temporal_type, time_points` |

`plan_reference` 只出现在 10M；`complexity_factors` 只在部分 split/type 出现。不能
从单条样本推导黑名单。

所有非空 `time_anchor` 均匹配 `Month-DD-YYYY`。前三 split chat turn 非空数分别
90/350/350，`user_questions` 非空数完全相同；其余 turn 为 `None`。10M 顶层 chat
与 `plans[].chat` 都是 999 个非空、207,697 个 `None`；plan 级 user_questions
为 999 个合法日期、1 个 `None`。10M 顶层 `user_questions` 是空列表。

## 3. Q1：10M 官方消费方式

**判定：官方 answer 评测消费 conversation 根目录的一份顶层聚合
`chat.json`（存在时优先 `chat_trunecated.json`）和一份全局
`probing_questions/probing_questions.json`；不是逐个独立评测 `plans[].chat`。E2
应按 plan 顺序展开顶层聚合结构。**

证据链：

1. batch runner 为每个数字 conversation 目录选择根部 chat 文件，并选择根部单份
   probing 文件：`answer_generation.py:142-161,180-203`。
2. 二者原样传入 `answer_generation`，后者只加载一份 probing dict，再把同一个
   `chat_address` 传给所有问题：`answer_generation.py:39-40,51-80`。
3. 10M 生成代码读取根部聚合 chat，并按 `chat[i]['plan-{i+1}']` 访问 plan：
   `ten_milion_pipeline.py:1385-1440`。

真实 Arrow 中顶层 chat 与 `plans[].chat` 每条 conversation 的 turn 总数相等，且
全量 content/role 序列逐项相等，但 turn dict/id 序列不等：顶层 id 在整条
conversation 内连续且唯一，plan 视图的 id 会在每个 plan 重启。两者承载相同 plan
对话，身份空间不同。

| 10M 位置 / conversation_id | 顶层 turns | plans 0..9 turns（每 plan 均 10 sessions） |
|---|---:|---|
| 0 / 1 | 19,895 | 1832,2164,2070,1816,1968,2030,1895,1900,2356,1864 |
| 1 / 2 | 19,057 | 1860,1976,1780,1894,1880,1974,2023,1892,1868,1910 |
| 2 / 3 | 20,192 | 2162,2254,1834,1914,1756,1982,1896,1996,2380,2018 |
| 3 / 4 | 19,202 | 1600,1614,2024,1954,1720,1790,2214,1964,2100,2222 |
| 4 / 5 | 18,760 | 1978,1566,1798,1726,1950,1876,2014,1752,1942,2158 |
| 5 / 6 | 19,958 | 2024,1948,1942,1902,1950,2038,2038,1958,1982,2176 |
| 6 / 7 | 22,652 | 2306,2496,2180,2636,2078,2226,2012,2030,2276,2412 |
| 7 / 8 | 22,560 | 2542,2538,2426,2044,2074,1986,2048,2400,2268,2234 |
| 8 / 9 | 22,704 | 2816,2242,2032,2044,2314,2208,2080,2580,2212,2176 |
| 9 / 10 | 23,716 | 2710,2182,2354,2250,2348,2394,2202,2544,2516,2216 |

## 4. Q2：evidence id 空间与裁决落法

`source_chat_ids` 有三种结构：contradiction_resolution/knowledge_update/
temporal_reasoning 为带标签 dict 分组，event_ordering 为嵌套 list 分组，其余类型为
平铺 list。递归打平后全库 **10,534 个原子**；10,533 个整数原子均属于同 conversation
顶层 chat turn 的 `id` 值域，0 个属于字符串 `index` 值域。唯一非法原子是字符串
`"--"`：10M 位置 5 / `conversation_id="6"` / event_ordering 题位置 0。

缺 evidence 统计：abstention 200/200 恒无；此外 summarization 12、
preference_following 2、knowledge_update 1 也为空，故“其他类型恒有”不成立。

跨 session 唯一性：100K/500K/10M 顶层 id 均唯一；1M 有四条重复：位置 4 / conv 5
重复 150 个 id，位置 25 / conv 26 重复 424，位置 32 / conv 33 重复 206，位置 33 /
conv 34 重复 940。它们均由后续 session 的 id 从 0 重启造成。

**架构师裁决后的映射契约：** recall 匹配键使用公开 turn-id 空间
`{session_id}:t{turn_index}`（`beam.py:432`），raw integer id 映射到所有匹配位置；
重复 raw id 全收，any-match 即 hit，并记录 `ambiguous_gold_id_count`。官方三种
`source_chat_ids` 结构原样留私有 metadata；`"--"` 不进入匹配键，记录 unmatched，
不崩。recall 只打平原子集合；标签和顺序语义留给 rubric/event-ordering metric。

## 5. 可复算脚本

```python
import ast, hashlib, re
from collections import Counter, defaultdict
from pathlib import Path
from datasets import load_from_disk

SPLITS = {
    "100K": Path("data/BEAM/beam_dataset/100K"),
    "500K": Path("data/BEAM/beam_dataset/500K"),
    "1M": Path("data/BEAM/beam_dataset/1M"),
    "10M": Path("data/BEAM/beam_10M_dataset/10M"),
}

def atoms(value):
    if isinstance(value, dict):
        for nested in value.values(): yield from atoms(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value: yield from atoms(nested)
    elif value is not None:
        yield value

def top_10m_turns(chat):
    result = []
    for plan_slot in chat:
        for batches in plan_slot.values():
            if batches:
                for batch in batches:
                    for turn_group in batch["turns"]:
                        result.extend(turn_group)
    return result

for split, path in SPLITS.items():
    ds = load_from_disk(str(path))
    category = Counter(); rubric = Counter(); missing = Counter()
    evidence_total = evidence_miss = 0
    for row_pos, row in enumerate(ds):
        turns = top_10m_turns(row["chat"]) if split == "10M" else [
            turn for session in row["chat"] for turn in session
        ]
        ids = [turn["id"] for turn in turns]
        for ability, questions in ast.literal_eval(row["probing_questions"]).items():
            category[ability] += len(questions)
            for question_pos, question in enumerate(questions):
                rubric[len(question.get("rubric") or [])] += 1
                values = list(atoms(question.get("source_chat_ids")))
                if not values: missing[ability] += 1
                for value in values:
                    evidence_total += 1
                    if value not in ids:
                        evidence_miss += 1
                        print("BAD", split, row_pos, row["conversation_id"],
                              ability, question_pos, value)
        duplicate_ids = {value for value, count in Counter(ids).items() if count > 1}
        if duplicate_ids:
            print("DUP", split, row_pos, row["conversation_id"], len(duplicate_ids))
    print(split, len(ds), category, rubric, missing, evidence_total, evidence_miss)

for path in SPLITS.values():
    digest = hashlib.sha256(); size = 0
    for member in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(member.relative_to(path).as_posix().encode()); digest.update(b"\0")
        with member.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk); size += len(chunk)
    print(path, size, digest.hexdigest())
```
