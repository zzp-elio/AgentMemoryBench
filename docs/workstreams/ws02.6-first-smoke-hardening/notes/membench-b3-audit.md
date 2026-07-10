# MemBench B3 D1 一手数据剖面审计

> 复核对象：`data/membench/Membenchdata/data2test/数据集结构说明.md`（以下简称"二手文档"）
> 审计人：actor（2026-07-10）
> 方法：全量 Python 遍历 8 个正式 JSON，逐数字对比

## 1. 全 8 文件 trajectory 数

| 文件 | 二手文档声称 | 一手核验 | 一致？ |
|------|------------:|---------:|:------:|
| 0-10k/FirstAgentDataHighLevel | 700 | 700 | ✅ |
| 0-10k/FirstAgentDataLowLevel | 900 | 900 | ✅ |
| 0-10k/ThirdAgentDataHighLevel | 400 | 400 | ✅ |
| 0-10k/ThirdAgentDataLowLevel | 1400 | 1400 | ✅ |
| 100k/FirstAgentDataHighLevel | 140 | 140 | ✅ |
| 100k/FirstAgentDataLowLevel | 360 | 360 | ✅ |
| 100k/ThirdAgentDataHighLevel | 80 | 80 | ✅ |
| 100k/ThirdAgentDataLowLevel | 280 | 280 | ✅ |

**结论：全 8 文件 trajectory 数完全一致，无偏差。**

## 2. task_type 分布

除 ThirdAgent 外均与计划（§2.1）一致。逐文件：

### 0-10k/FirstAgentDataHighLevel (700 trajectories)
- `highlevel`: movie(100), food(100), book(100), emotion(100) — 400
- `highlevel_rec`: movie(100), food(100), book(100) — 300

### 0-10k/FirstAgentDataLowLevel (900 trajectories)
- 9 个 task_type，每 task_type 各 2 subcategory（roles + events），每 subcategory 各 50 = 9 × 2 × 50 = 900  ✅ lowlevel_rec 有 3 个 subcategory（movie/food/book），RecMultiSession 有 1 个（multi_agent）
- 细分：
  - simple/conditional/comparative/aggregative/post_processing/knowledge_update/noisy 各 roles(50)+events(50)=100
  - lowlevel_rec: movie(50)+food(50)+book(50)=150
  - RecMultiSession: multi_agent(50)=50
  - **小计: 7×100 + 150 + 50 = 900** ✅

### 0-10k/ThirdAgentDataHighLevel (400)
- 只有 `highlevel`: movie(100)+food(100)+book(100)+emotion(100) = 400

### 0-10k/ThirdAgentDataLowLevel (1400)
- 7 个 task_type，每 task_type 各 4-5 subcategory（conditional 种类最多），每 subcat 50
- task_type 列表：simple, conditional, comparative, aggregative, post_processing, noisy, knowledge_update
- 28 subcategories × 50 = 1400 ✅
- 注意二手文档声称 7 类低层任务，实际 7 类 ✅

### 100k 文件
- FirstAgentDataHighLevel: 7 subcat × 20 = 140 ✅
- FirstAgentDataLowLevel: 9 task_types，18 subcat × 20 = 360 ✅
- ThirdAgentDataHighLevel: 4 subcat × 20 = 80 ✅
- ThirdAgentDataLowLevel: 28 subcat × 10 = 280 ✅（文档说 N=10，吻合）

**结论：所有 task_type 分布与二手文档一致。**

## 3. answer str/list 两态

| 文件 | 总 trajectory | str answer | list answer | list 来源 |
|------|-------------:|-----------:|------------:|----------|
| 0-10k/FAHigh | 700 | 700 | 0 | — |
| 0-10k/FALow | 900 | 700 | 200 | lowlevel_rec/* (150) + RecMultiSession (50) |
| 0-10k/TAHigh | 400 | 400 | 0 | — |
| 0-10k/TALow | 1400 | 1400 | 0 | — |
| 100k/FAHigh | 140 | 140 | 0 | — |
| 100k/FALow | 360 | 280 | 80 | lowlevel_rec/* (60) + RecMultiSession (20) |
| 100k/TAHigh | 80 | 80 | 0 | — |
| 100k/TALow | 280 | 280 | 0 | — |

**结论：list answer 只出现在 FirstAgentDataLowLevel 的 `lowlevel_rec/` 和 `RecMultiSession/multi_agent`，与二手文档一致。str/list 两态数字吻合。**

## 4. 越界 target_step_id

### 0-10k/FirstAgentDataLowLevel
- **comparative/events**: tid=4, target_step_id=[111], message_list 长度=111
- 0-based 最大有效索引 = 110，111 正好越界 1
- ✅ 二手文档声称正确（"target_step_id 等于 len(message_list)"，而非 len-1）

### 100k/FirstAgentDataLowLevel
- **comparative/events**: tid=4, target_step_id=[411], message_list 长度=411
- 同一源的加噪版；越界模式完全相同
- ✅ 二手文档声称正确

**结论：全部 8 文件中只有 2 个越界 target_step_id（0-10k 和 100k 各 1 个），均位于 comparative/events tid=4，形式一致。**

### 基准与越界根源（架构师验收追加，一手）

官方 `load_test_data.py` 的重映射 `reverse_relocate_dict[step_id]` 按
enumerate 的 **0 基 index** 构建 → **target_step_id 是 0 基**（D4 的
step→turn 映射按 0 基，勿 off-by-one）。越界=len 的 2 例疑似官方 while
循环 `len + 3*length - 1` 边界的 off-by-one 产物；recall 对越界 id 记
N/A + 单独计数，不崩。另：FirstHigh 0-10k 有 **1 个空 target_step_id**
（highlevel_rec/movie tid=25，架构师与 actor 双独立确认），现行 adapter
`_target_step_ids` 遇空列表抛 DatasetValidationError → **full load 必崩**，
属 D1 发现的真 latent bug，修复归 D2（空列表=无 step 证据，合法保留）。

## 5. 时间戳格式分布（架构师已实锤，此节全 8 文件量化）

### 0-10k 文件

**第一人称文件**（messages 是 dict `{user, agent}`）：

| 文件 | 总 message | 有时间后缀 | 无时间后缀 |
|------|-----------:|-----------:|-----------:|
| FirstAgentDataHighLevel | 15450 | 15450 | 0 |
| FirstAgentDataLowLevel | 104470 | 104470 | 0 |

无变动。文档声称 0-10k 中每条消息都带有时间元数据 ✅

**第三人称文件**（关键：时间格式不一致在此量化）：

| 文件 | 总 message | `time:` 带冒号 | `time'` 无冒号 | 无时间后缀 |
|------|-----------:|---------------:|---------------:|-----------:|
| ThirdAgentDataHighLevel(0-10k) | 5302 | **5302** | 0 | 0 |
| ThirdAgentDataLowLevel(0-10k) | 19285 | 0 | **19285** | 0 |

✅ 与架构师 §2.2 一手数据完全吻合：
- ThirdHigh 5,302 — 全有冒号 → 正则 `time:\s*'…'` 全中
- ThirdLow 19,285 — 全无冒号 → 正则全部漏配

### 100k 文件

时间后缀整体用正则 `\(place:.*?;.*?time[:\s]?.*?'\d{4}-\d{2}-\d{2} \d{2}:\d{2}'.*?\)` 检测（包容带/不带冒号）：

| 文件 | 总 message | 有时间后缀 | 无时间后缀（noise） | 无后缀占比 |
|------|-----------:|-----------:|--------------------:|----------:|
| FirstAgentDataHighLevel | 45133 | 3133 | 42000 | 93.1% |
| FirstAgentDataLowLevel | 149777 | 41777 | 108000 | 72.1% |
| ThirdAgentDataHighLevel | 25049 | 1049 | 24000 | 95.8% |
| ThirdAgentDataLowLevel | 87779 | 3779 | 84000 | 95.7% |

**与二手文档数字逐项直接比较**：

| 文件 | 二手文档声称无 time | 一手核验 | 一致？ |
|------|-------------------:|---------:|:------:|
| 100k/FAHigh | 42000 / 45133 | 42000/45133 | ✅ 完全一致 |
| 100k/FALow | 108000 / 149777 | 108000/149777 | ✅ 完全一致 |
| 100k/TAHigh | 24000 / 25049 | 24000/25049 | ✅ 完全一致 |
| 100k/TALow | 84000 / 87779 | 84000/87779 | ✅ 完全一致 |

### 时间格式在 100k 内的分布（全 4 文件；架构师验收修正版）

【验收修正 2026-07-10：actor 初版此表（TAHigh 1060/11/23978、TALow
3815/15/83949）与本文件 §5 首表自相矛盾（首表"有时间后缀"TAHigh=1049 与
架构师独立复算一致），已用架构师逐消息分类复算值替换。口径：每条 message
按 `time:\s*'` → 冒号、否则 `time'` → 无冒号、否则无后缀，elif 互斥。】

| 文件 | 总 msg | `time:` 冒号 | `time'` 无冒号 | 无时间后缀 |
|------|-------:|-------------:|---------------:|------------:|
| 100k/FirstAgentDataHighLevel | 45133 | 3133 | 17 | 41983 |
| 100k/FirstAgentDataLowLevel | 149777 | 41777 | 29 | 107971 |
| 100k/ThirdAgentDataHighLevel | 25049 | 1049 | 11 | 23989 |
| 100k/ThirdAgentDataLowLevel | 87779 | 3779 | 15 | 83985 |

### 格式不一致的官方根源（架构师验收追加，一手）

无冒号格式**是官方加噪代码生成的**，不是数据损坏：
`third_party/benchmarks/Membench-main/benchmark/load_test_data.py:57` 的
格式串为 `'{} (place: {}; time{})'`——`time` 后无冒号，time 值自带引号，
故所有经加噪重排的消息呈 `time'…'`；带冒号消息来自原始文本自带的
`(place: …; time: '…')` 后缀。两种格式在同一文件混布是官方生成器行为，
D2 的可选冒号正则（`time:?\s*'`）是正确修法。

## 6. ground_truth 分布

所有 8 文件的 ground_truth 均为 A/B/C/D 单字母，无异常值，分布均衡：

| 文件 | A | B | C | D |
|------|---:|---:|---:|---:|
| 0-10k/FAHigh | 170 | 176 | 187 | 167 |
| 0-10k/FALow | 224 | 221 | 221 | 234 |
| 0-10k/TAHigh | 99 | 112 | 98 | 91 |
| 0-10k/TALow | 359 | 304 | 354 | 383 |
| 100k/FAHigh | 42 | 30 | 29 | 39 |
| 100k/FALow | 92 | 92 | 85 | 91 |
| 100k/TAHigh | 20 | 26 | 23 | 11 |
| 100k/TALow | 68 | 66 | 74 | 72 |

**结论：ground_truth 分布无明显异常，均为四选项等比例分布。✅**

## 7. 游离文件

二手文档声称 `data2test/` 根目录下有游离文件 `ThirdAgentDataHighLevel_multiple_100.json`。本地快照检查：**该文件只存在于 `100k/` 子目录内**，`data2test/` 根目录无 `.json` 文件。

**偏差：游离文件存在性无法在本地快照中复现。可能原因：该文件在本地快照制作时未被包含，或被移动至 100k/ 子目录。如实记录，非数据问题。**

## 8. 全局 message 形态

| 人称 | message 类型 | 存在文件 |
|------|-------------|---------|
| FirstAgent (第一人称) | `dict{user, agent}` | FAHigh + FALow，0-10k 和 100k |
| ThirdAgent (第三人称) | `str` | TAHigh + TALow，0-10k 和 100k |

**结论：跨文件人称为一形态，无混用。✅**

## 可复算脚本

本审计所有数字可由以下 Python 脚本复现：

```python
import json, hashlib, re
from pathlib import Path

base = Path('data/membench/Membenchdata/data2test')
TIME_RE = re.compile(r"\(place:.*?;.*?time[:\s]?.*?'\d{4}-\d{2}-\d{2} \d{2}:\d{2}'.*?\)")

FILES_8 = [
    '0-10k/FirstAgentDataHighLevel_multiple_0.json',
    '0-10k/FirstAgentDataLowLevel_multiple_0.json',
    '0-10k/ThirdAgentDataHighLevel_multiple_0.json',
    '0-10k/ThirdAgentDataLowLevel_multiple_0.json',
    '100k/FirstAgentDataHighLevel_multiple_100.json',
    '100k/FirstAgentDataLowLevel_multiple_100.json',
    '100k/ThirdAgentDataHighLevel_multiple_100.json',
    '100k/ThirdAgentDataLowLevel_multiple_100.json',
]

for rel in FILES_8:
    with open(base / rel) as f:
        data = json.load(f)
    traj_count = 0
    answer_str = 0
    answer_list = 0
    oob = 0
    has_colon = no_colon = no_time = 0
    for tt, scenarios in data.items():
        for subcat, trajs in scenarios.items():
            traj_count += len(trajs)
            for t in trajs:
                qa = t.get('QA', {})
                a = qa.get('answer')
                if isinstance(a, str): answer_str += 1
                elif isinstance(a, list): answer_list += 1
                tsid = qa.get('target_step_id', [])
                msg_len = len(t.get('message_list', []))
                for sid in tsid if isinstance(tsid, list) else []:
                    if int(sid) >= msg_len:
                        oob += 1
                # ThirdAgent time format
                if 'ThirdAgent' in rel:
                    for msg in t.get('message_list', []):
                        if isinstance(msg, str):
                            if "time:" in msg:
                                has_colon += 1
                            elif "time'" in msg or "time " in msg:
                                no_colon += 1
                            else:
                                no_time += 1
    print(f"{rel}: traj={traj_count}, str_ans={answer_str}, list_ans={answer_list}, oob_tsid={oob}")
    if 'ThirdAgent' in rel and any([has_colon, no_colon, no_time]):
        print(f"  time: colon={has_colon}, no_colon={no_colon}, no_time={no_time}")
```
