# LongMemEval B2 真实数据剖面笔记（C1）

日期：2026-07-10
执行者：Claude（本次会话，模型见系统提示：Claude Opus 4.8）
范围：`docs/workstreams/ws02.6-first-smoke-hardening/plan-b2-longmemeval.md` C1，
两个变体的现场剖面。本笔记只记本次真跑过的扫描与真实输出，不替代 source
identity（以 [longmemeval-source-lock.json](longmemeval-source-lock.json) 为准）。

所有数字来自本次会话对 `data/longmemeval/longmemeval_s_cleaned.json` 与
`data/longmemeval/longmemeval_m_cleaned.json` 的**流式扫描**（`_m` 2.7GB，
禁止 `json.load`，全程用 ijson 逐 instance 读）。扫描脚本见本笔记末附录，
可复算。

## 1. 与架构师预期量级自查（`_s`）

架构师在 plan §2.1 给出的 `_s` 预期：

| 指标 | 预期 | 本次实测 | 一致 |
|------|------|----------|------|
| instance 数 | 500 | 500 | ✅ |
| session 总数 | 23,867 | 23,867 | ✅ |
| turn 总数 | 246,750 | 246,750 | ✅ |
| abstention 题（`_abs`） | 30 | 30 | ✅ |
| has_answer 键出现 | 10,960 | 10,960 | ✅ |
| has_answer=True | 896 | 896 | ✅ |
| 奇数长度 session | 1,940 | 1,940 | ✅ |

七项硬计数全部一致。

**异常 role 分布有子分类口径差异，如实记录**：plan §2.1 记 1,946 个非严格
user-first 交替（“1,280+346+242 个 assistant 先说、65 个纯 assistant、4 个连续
assistant、个别连续 user”）。本次用一套统一的分类函数（见附录 `classify_session`）
得到 `assistant-first=1,871 / pure-assistant=71 / consecutive-same=5`，合计
1,947，与 plan 的 1,946 差 1。差异来源是分类边界不同：

- plan 把“assistant 先说”拆成 1,280+346+242 三个来源记 1,868，把“纯 assistant”
  记 65；本次分类函数把“第一条是 assistant”统一记 `assistant-first`（1,871），
  其中含 plan 口径里部分被记到别的桶的 session；
- plan 的“4 个连续 assistant / 个别连续 user”合并到本次 `consecutive-same`（5），
  且 `pure-assistant`（71）比 plan 的 65 多 6——因为本次只要“全部非 system turn
  都是 assistant”就计 `pure-assistant`，而 plan 可能采用更紧的纯 assistant 定义。

按 plan C1 口径这些差异**属于子分类口径不同、不是数据错误**（合计 1,947 vs
1,946 仅差 1，且单值计数全对）。仍按指令如实记录差异，未改数凑对。

## 2. `longmemeval_s_cleaned.json`（277MB，全量流式）

```
instance_count: 500
session_total: 23867
turn_total: 246750
question_type_distribution: {'single-session-user': 70, 'multi-session': 133,
  'single-session-preference': 30, 'temporal-reasoning': 133,
  'knowledge-update': 78, 'single-session-assistant': 56}
abstention_count: 30
role_pattern_distribution: {'normal-user-first': 21920, 'assistant-first': 1871,
  'pure-assistant': 71, 'consecutive-same': 5}
odd_session_count: 1940
has_answer_key_count: 10960
has_answer_true_count: 896
turn_key_distribution: {'role': 246750, 'content': 246750, 'has_answer': 10960}
```

字段口径：

- question_type 6 类合计 = 70+133+30+133+78+56 = **500**，与 instance 数一致；
  无超类、无空值。`abstention=30` 由 `question_id` 带 `_abs` 后缀判（见 plan
  §2.1），与“knowledge-update 78 含 abs”不互斥——abstention 是 question_id 维度的
  标记，跨在多类型之上。
- 异常 role：`normal-user-first`=21,920（严格 user 先说且无相邻同 role），
  其余 1,947 个非严格交替（assistant-first/pure-assistant/consecutive-same），
  即约 **8.16%** session 非严格交替——与 plan“约 8%”一致。**全部保留不丢弃**
  （haystack 干扰是任务语义，详见 plan §2.1 + 决策 #8）。
- 奇数 session 数 1,940：odd 不等于 assistant-first 数（1,871），二者是正交维度
  （一个 session 可以奇数长度但仍 user 先说，反之亦可）。
- **turn 字段键只有三个**：`role`、`content`、`has_answer`。没有 `text`、
  `speaker`、`timestamp`、`img_*` 等。即：
  - 跨 benchmark 差异：LoCoMo 有 `img_url`/`blip_caption`/时间戳，LongMemEval
    turn 扁平到只剩 role+content+（私有）has_answer。adapter 的
    `_message_content` 回退 `text` 在本数据上不触发。
  - 私有边界：`has_answer` 出现 10,960 次，其中 True 896。这三键里只有
    `has_answer` 是私有（已在 adapter `PRIVATE_MESSAGE_KEYS` 中，见
    `longmemeval.py:47-59`）；`role`/`content` 是公开核心字段。
- 时间戳只在 session 级（`haystack_dates`，格式 `2023/05/30 (Tue) 23:40`），
  turn 无时间戳——turn 时间继承 session 时间（同 LoCoMo 先例，见 plan §2.1）。

## 3. `longmemeval_m_cleaned.json`（2.7GB，ijson 流式，未 json.load）

```
instance_count: 500
session_total: 237655
turn_total: 2446993
question_type_distribution: {'single-session-assistant': 56, 'single-session-user': 70,
  'multi-session': 133, 'knowledge-update': 78, 'temporal-reasoning': 133,
  'single-session-preference': 30}
abstention_count: 30
role_pattern_distribution: {'normal-user-first': 218185, 'assistant-first': 18822,
  'pure-assistant': 609, 'consecutive-same': 39}
odd_session_count: 19395
has_answer_key_count: 10960
has_answer_true_count: 896
turn_key_distribution: {'role': 2446993, 'content': 2446993, 'has_answer': 10960}
```

`_m` vs `_s` 关键观察：

- **instance/question 维度两变体相同**：都是 500 instance、30 abstention、
  question_type 6 类相同分布、has_answer 键 10,960/True 896 完全一致——
  即 `_m` 和 `_s` 用的是**同一批 500 个 question**，只是每题的 haystack 干扰量
  不同。这与 README“Each chat history contains roughly 500 sessions”一致
  （`_s`~40-80 session/题，`_m`~500 session/题）。
- session/turn 量级差异巨大：session 23,867 → 237,655（约 9.95×），turn
  246,750 → 2,446,993（约 9.92×）。即可见 `_m` 实测约 475 session/题、
  4,894 turn/题，与 README“roughly 500 sessions”量级一致。
- 异常 role 比例略降：`_m` 非严格交替 = 18,822+609+39 = **19,470**
  （约 8.19%），与 `_s` 的 8.16% 基本同量级——异常不是 `_m` 特有放大。
- turn 字段键集合与 `_s` 完全一致（role/content/has_answer），无私有字段形态
  差异。
- `_m` 奇数 session 数 19,395，约 8.16%，与 `_s` 比例一致。
- **`_m` 未做全链路，只做数据剖面**（plan §4 / frozen-v1 known limitation）：
  本轮不跑 `_m` 的 ingest→retrieve→answer，只锁其源身份与契约形态。

## 4. 私有边界确认

- `answer`、`answer_session_ids`（instance 级 evidence session id 列表）、turn 级
  `has_answer` 三个私有字段在 adapter 中已全部隔离：
  - `answer` → `GoldAnswerInfo.answer`，不进公开 `Question`；
  - `answer_session_ids` → `GoldAnswerInfo.evidence`，不进公开对象；
  - turn 级 `has_answer` → `PRIVATE_MESSAGE_KEYS` 拦截（`_public_message_metadata`
    跳过，见 `longmemeval.py:460-476`）。
- 本次扫描确认 turn 键集合 = {role, content, has_answer}，无其他疑似私有键
  漏网。公私边界与官方 `run_generation.py:182-183`（pop 掉 `has_answer` 再进 prompt）
  一致（plan §2.1 已核实）。

## 5. 结论

- 七项硬计数与 plan §2.1 预期逐项一致；异常 role 子分类有 ≈1 的口径差，如实记录，
  未改数。
- 两个变体共享同一批 500 question，差异只在 haystack 干扰量；`_m` 约 10× `_s`。
- turn 字段极简（role/content/+私有 has_answer），无时间戳（session 级才有）。
- 无 plan 停工条件触发：数据可加载、计数自洽、私有边界清晰。adapter metadata
  补 source identity + 实际计数见 `longmemeval.py` 本次改动（对齐 locomo T1）。

## 附录：本次使用的扫描脚本

脚本 `tmp_longmemeval_scan.py`（临时，跑完删）：

```python
"""一次性 LongMemEval 现场剖面扫描脚本（C1 用，跑完即删）。

对 `_s` 做全量计数，对 `_m` 用 ijson 流式扫描（文件 2.7GB，禁止 json.load）。
统计 instance/session/turn、question_type 分布、abstention 题、异常 role 序列、
奇数长度 session、has_answer 键分布、turn 字段键形态。
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import ijson


def classify_session(turns: list) -> tuple[str, bool]:
    """返回 (role_pattern, is_odd)。

    role_pattern 取值：
      - "assistant-first": 第一条 turn 是 assistant（含 assistant 先说的情况）
      - "pure-assistant": 所有非 system turn 都是 assistant
      - "consecutive-same": 相邻两条同 role（非 system）
      - "normal-user-first": user 先说且严格交替
      - "other": 其他异常
    is_odd: turn 数是否奇数。
    """

    roles_in_order = [t.get("role") for t in turns if isinstance(t, dict)]
    non_system = [r for r in roles_in_order if r in ("user", "assistant")]
    is_odd = len(roles_in_order) % 2 == 1

    if not non_system:
        return ("empty", is_odd)

    pure_assistant = all(r == "assistant" for r in non_system) and "assistant" in non_system
    if pure_assistant:
        return ("pure-assistant", is_odd)

    if non_system[0] == "assistant":
        return ("assistant-first", is_odd)

    consecutive = any(
        non_system[i] == non_system[i + 1] for i in range(len(non_system) - 1)
    )
    if consecutive:
        return ("consecutive-same", is_odd)

    if non_system[0] == "user":
        return ("normal-user-first", is_odd)

    return ("other", is_odd)


def scan(path: Path) -> dict:
    """ijson 流式扫描一个 LongMemEval 数据文件。"""

    instance_count = 0
    session_total = 0
    turn_total = 0
    question_type_counter: Counter = Counter()
    abstention_count = 0
    role_pattern_counter: Counter = Counter()
    odd_session_count = 0
    has_answer_key_count = 0
    has_answer_true_count = 0
    turn_key_set: Counter = Counter()

    with path.open("rb") as handle:
        for instance in ijson.items(handle, "item"):
            instance_count += 1
            qt = instance.get("question_type")
            if qt is not None:
                question_type_counter[str(qt)] += 1
            qid = instance.get("question_id", "")
            if "_abs" in str(qid):
                abstention_count += 1

            sessions_raw = instance.get("haystack_sessions", [])
            session_total += len(sessions_raw)
            for turns in sessions_raw:
                if not isinstance(turns, list):
                    continue
                turn_total += len(turns)
                pattern, is_odd = classify_session(turns)
                role_pattern_counter[pattern] += 1
                if is_odd:
                    odd_session_count += 1
                for t in turns:
                    if not isinstance(t, dict):
                        continue
                    for k in t.keys():
                        turn_key_set[str(k)] += 1
                    if "has_answer" in t:
                        has_answer_key_count += 1
                        if t.get("has_answer") is True:
                            has_answer_true_count += 1

    return {
        "instance_count": instance_count,
        "session_total": session_total,
        "turn_total": turn_total,
        "question_type_distribution": dict(question_type_counter),
        "abstention_count": abstention_count,
        "role_pattern_distribution": dict(role_pattern_counter),
        "odd_session_count": odd_session_count,
        "has_answer_key_count": has_answer_key_count,
        "has_answer_true_count": has_answer_true_count,
        "turn_key_distribution": dict(turn_key_set),
    }


def main() -> None:
    for label, fname in [
        ("_s", "data/longmemeval/longmemeval_s_cleaned.json"),
        ("_m", "data/longmemeval/longmemeval_m_cleaned.json"),
    ]:
        path = Path(fname)
        print(f"=== {label} : {fname} ===", flush=True)
        result = scan(path)
        for k, v in result.items():
            print(f"{k}: {v}", flush=True)
        print(flush=True)


if __name__ == "__main__":
    main()
```

真实运行（本次会话）：

```bash
uv run python tmp_longmemeval_scan.py
```
（输出见上文 §2/§3 的两个代码块，原样照录。）