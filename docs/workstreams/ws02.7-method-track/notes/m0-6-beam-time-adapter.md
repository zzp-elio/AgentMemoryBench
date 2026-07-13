# M0-6 BEAM x LightMem 时间适配与 smoke 风险核查

> 日期：2026-07-13。代码范围仅为 LightMem adapter 的通用时间适配层与直接测试；
> 数据从主树 `/Users/wz/Desktop/memoryBenchmark/data/BEAM/` 只读，未复制；全程零真实
> API。Arrow 二进制数据没有文本行号，因此数据结论附可复算脚本与实际输出。

## 1. 问题与修复边界

M0-4 已证明 BEAM 100k/10m 的非空 anchor 是 `March-15-2024`、
`July-01-2024` 一类月名日期，而旧 LightMem 路径原样透传后会被官方
`MessageNormalizer` 拒绝
（`docs/workstreams/ws02.7-method-track/notes/m0-4-membench-beam-lightmem-compat.md:115-128,408-415`）。
官方 normalizer 只接受带 weekday 的数字日期格式或 ISO fallback
（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:28-57`）。

本卡在 `_turn_timestamp` 中保持既有顺序：先尝试 LoCoMo 特化，再尝试通用
`[English month name]-[1 or 2 digit day]-[4 digit year]`，成功时输出午夜 ISO，
其余值继续透传；完全缺时仍抛 `ConfigurationError`
（`src/memory_benchmark/methods/lightmem_adapter.py:1410-1471`）。转换发生在构造
LightMem message 副本时（`lightmem_adapter.py:1126-1155`），不会改写 canonical
`Turn.turn_time`/`Session.session_time`；v3 事件还在既有 metadata 中保存
`original_session_time` 与 `original_turn_time`
（`src/memory_benchmark/runners/event_stream.py:35-59`）。因此原始值仍可从公开
conversation/事件审计，转换不是破坏性覆盖。

**结论：修复不依赖 benchmark 名称，不触碰 frozen `beam.py` 或 third_party；
`April-02-2024` 会变为 `2024-04-02T00:00:00`，非法月名维持旧透传行为，完全缺时
维持 fail-fast。**

## 2. 真实 anchor 形态复扫

扫描直接读取两个 HuggingFace Arrow 目录的所有 shard；10m 严格按 frozen adapter
的 `chat[i]['plan-{i+1}'] -> batch['turns']` 顺序展开
（`src/memory_benchmark/benchmark_adapters/beam.py:464-509`）。核心扫描代码：

```python
from pathlib import Path
import pyarrow as pa
import pyarrow.ipc as ipc
import re

root = Path("/Users/wz/Desktop/memoryBenchmark/data/BEAM")

def rows(pattern):
    for path in sorted(root.glob(pattern)):
        with pa.memory_map(str(path), "r") as source:
            yield from ipc.open_stream(source).read_all().to_pylist()

def sessions(row, variant):
    if variant == "100k":
        yield from row["chat"]
        return
    for plan_index, slot in enumerate(row["chat"], 1):
        for batch in slot[f"plan-{plan_index}"]:
            yield [turn for group in batch["turns"] for turn in group]

for variant, pattern in (
    ("100k", "beam_dataset/100K/*.arrow"),
    ("10m", "beam_10M_dataset/10M/*.arrow"),
):
    anchors = [
        turn["time_anchor"]
        for row in rows(pattern)
        for session in sessions(row, variant)
        for turn in session
        if turn.get("time_anchor")
    ]
    forms = {
        "month-dd-yyyy": sum(
            re.fullmatch(r"[A-Za-z]+-\d{2}-\d{4}", value) is not None
            for value in anchors
        ),
        "other": sum(
            re.fullmatch(r"[A-Za-z]+-\d{2}-\d{4}", value) is None
            for value in anchors
        ),
    }
    print(variant, len(anchors), forms)
```

实际输出：

```text
100k 90 {'month-dd-yyyy': 90, 'other': 0}
10m 999 {'month-dd-yyyy': 999, 'other': 0}
```

另对全部 unique 值检查了单数日正则 `[A-Za-z]+-\d-\d{4}`，命中数为 0；因此测试
没有虚构 `July-1-2024` fixture。**未发现 `%B-%d-%Y` 之外的第三种真实非空 anchor
形态，未触发任务卡停工条件。**

## 3. 转换与官方 normalizer 离线核验

adapter 的真实样本测试同时覆盖 `March-15-2024`、`July-01-2024`、非法月名、既有
LoCoMo 与 ISO 路径，并断言原 canonical 时间字段不变；另把两条真实 anchor 的转换
结果直接交给 vendored `MessageNormalizer.normalize_messages()`
（`tests/test_lightmem_adapter.py` 中
`test_lightmem_turn_timestamp_adapts_month_name_dates_without_mutating_source`、
`test_lightmem_month_name_timestamp_is_accepted_by_official_normalizer`、
`test_lightmem_turn_timestamp_keeps_missing_time_fail_fast`）。官方 normalizer 会深拷贝
消息、把解析值写成毫秒 ISO，并保留输入时间为 `session_time`
（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:79-102`）。

离线实测输出：

```text
100k: anchor=March-15-2024 converted=2024-03-15T00:00:00 official_normalized=2024-03-15T00:00:00.000
10m: anchor=July-01-2024 converted=2024-07-01T00:00:00 official_normalized=2024-07-01T00:00:00.000
```

**结论：真实 BEAM anchor 经 adapter 转换后可以被官方 normalizer 接受；无时间的
既有异常路径没有放宽。**

## 4. 声明式 smoke 的实际切片

BEAM policy 定义单 variant smoke 为 1 conversation、1 round、1 question，双结构
认证由 100k 与显式 10m 两个独立 run 组成
（`src/memory_benchmark/benchmark_adapters/beam.py:77-90`）。prepare 在 smoke scope
先按 conversation limit 加载，再把 round limit 传给专属裁剪器
（`beam.py:260-280`）；裁剪器把 1 round 换算成 2 turns，并按公开 session/turn 顺序
消费（`beam.py:647-686`）。

以下脚本从真实 Arrow 首 row 读取、使用生产 `strip_tail_marker()`，并以
`cl100k_base` 给出可复算的近似 token 数；该 token 数不是 LightMem 本地 tokenizer
的权威值：

```python
import tiktoken
from memory_benchmark.benchmark_adapters.beam import strip_tail_marker

encoder = tiktoken.get_encoding("cl100k_base")
# row/sessions 的读取与上一节相同；policy 保留 ordered_sessions[0][:2]
for index, raw_turn in enumerate(ordered_sessions[0][:2], 1):
    content = strip_tail_marker(raw_turn["content"])
    print(index, raw_turn["id"], raw_turn["role"], raw_turn.get("time_anchor"),
          len(content), len(encoder.encode(content)))
```

实际结果：

| variant | conversation / session | retained turn | raw id / role | anchor | chars | cl100k tokens |
|---|---|---|---|---|---:|---:|
| 100k | `1` / `s1` | `s1:t1` | `0` / user | `March-15-2024` | 176 | 44 |
| 100k | `1` / `s1` | `s1:t2` | `1` / assistant | 空，回填 session anchor | 2,189 | 483 |
| 10m | `1` / `p1:s1` | `p1:s1:t1` | `0` / user | `July-01-2024` | 232 | 54 |
| 10m | `1` / `p1:s1` | `p1:s1:t2` | `1` / assistant | 空，回填 session anchor | 2,977 | 694 |

BEAM adapter 用 session 首个非空 anchor 回填 `session_time`，无自身 anchor 的 turn
由 LightMem `_turn_timestamp` 回退到该值
（`src/memory_benchmark/benchmark_adapters/beam.py:590-642`；
`src/memory_benchmark/methods/lightmem_adapter.py:1420-1431`）。

### 4.1 硬答案 A：全缺时 session

全量扫描定位到唯一全缺时 session：10m **0 基 row 位置 6、conversation id `7`、
`p1:s1`，244 turns**，与 M0-4 记录一致
（`m0-4-membench-beam-lightmem-compat.md:115-120`）。10m smoke 只加载首
conversation id `1` 并保留其 `p1:s1` 前 2 turns。

**答案 A：不会触达 conversation id `7` 的全缺时 `p1:s1`；该 blocker 仍存在于
formal，但不阻断当前 10m smoke。**

### 4.2 硬答案 B：超长 turn

M0-4 的全库病态最大值是 100k 348,853 chars 与 10m 329,788 chars
（`m0-4-membench-beam-lightmem-compat.md:130-146`）。本次 smoke 最长分别只有
2,189 与 2,977 chars，均不包含 30 万字符级 turn。10m 第二条的 `cl100k_base`
近似值为 694，说明真实运行会使用官方预压缩路径；官方 compressor 在有 tokenizer
时会继续压到 `<512`，异常时保留当前内容
（`third_party/methods/LightMem/src/lightmem/factory/pre_compressor/llmlingua_2.py:39-89`）。

**答案 B：两 variant smoke 均不含 30 万字符级 turn；按任务卡，LLMLingua-2
病态 turn 压缩实测推迟，不在本卡加载模型。**

## 5. 更新后的 smoke 准入结论

**BEAM 100k 与 10m 均可进入真实 smoke。** 理由是：两条认证切片的月名 anchor 已
通过 adapter 通用转换并由官方 normalizer 离线验收；10m smoke 不触达唯一全缺时
session；两条切片都不包含 M0-4 发现的 30 万字符级 turn。此结论只覆盖 frozen-v1
的两次极小 smoke，不解除 10m formal 的全缺时 blocker，也不代表 full 规模成本已验收。

## 施工报告

- worktree 创建命令：
  `git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m06 -b actor/m0-6-beam-time`
- worktree / branch：`/Users/wz/Desktop/mb-actor-m06` /
  `actor/m0-6-beam-time`；创建基点 `5fcdb5b`。
- 环境：`uv sync` 成功，实际输出含 `Resolved 154 packages`、`Installed 130 packages`。
- 允许范围：只改 LightMem adapter、其直接测试和本 note；未改 frozen BEAM adapter、
  third_party、其他 method/runner，未调用真实 API。
- 停工条件：真实非空 anchor 只有一种格式；实现不需要改 `beam.py` 或 third_party，
  两项均未触发。
- 为满足独立 worktree 的全量测试，测试前仅在本地补齐主树只读 `data/`、`models/`、
  benchmark/docs ignored 资产映射，并临时复制 SimpleMem ignored 快照以通过 method root
  安全检查；这些环境资产在提交前全部清除，不入 git。
- 全量完成门：`uv run pytest -q`；最终尾行原文：
  `1122 passed, 3 deselected, 2 warnings, 4 subtests passed in 128.33s (0:02:08)`。
- 编译完成门：`uv run python -m compileall -q src/memory_benchmark tests`；退出码 0，
  stdout/stderr 均为空。
- 本卡 commit message：`fix: adapt month-name timestamps for LightMem`；hash 以本分支
  `git log -1` 为准，未 push。
