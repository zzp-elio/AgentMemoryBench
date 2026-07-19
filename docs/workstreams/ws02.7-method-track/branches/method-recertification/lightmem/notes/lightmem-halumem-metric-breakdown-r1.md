# HaluMem 官方细项与 question-type 分报 R1

日期：2026-07-19

范围：HaluMem evaluator 聚合；对所有 method 生效，不是 LightMem 专属公式。

真实 API：0；只读官方源码、既有 LightMem × HaluMem score/summary artifact，并运行 fake-judge
单元测试。

## 1. 论文主表不是三个单分数

论文表头的三个 task family 实际展开为：

| family | 论文列 | 框架字段 | 本轮前状态 |
| --- | --- | --- | --- |
| Extraction | R | `recall(all/valid)` | 已实现 |
| Extraction | Weighted R | `weighted_recall(all/valid)` | 已实现 |
| Extraction | Target P | `target_accuracy(all/valid)` | 已实现 |
| Extraction | Acc. | `weighted_accuracy(all/valid)` | 已实现 |
| Extraction | FMR | `interference_accuracy(all/valid)` | 已实现 |
| Extraction | F1 | `memory_extraction_f1` | 已实现 |
| Updating | C/H/O | `correct/hallucination/omission_update_memory_ratio` | 已实现；另保留官方 `Other` |
| QA | C/H/O | `correct/hallucination/omission_qa_ratio` | overall 已实现 |

因此“只有 extraction/update/QA 三个 overall”不成立；框架已经保存论文主表的全部核心列。
Extraction 与 Update 的 `category_breakdown` 还会按 memory type 给出阶段内切片。

## 2. 本轮发现的真实缺口

`HalumemQAEvaluator` 的每题 score row 已保存 `question_type` 与三分类 `result_type`，但旧
`category_breakdown` 只对二值 `score` 求均值，产出 `correct_qa_ratio + question_count`。
这意味着 overall C/H/O 完整、六类名称也存在，却无法区分某一 question type 的错误究竟是
Hallucination 还是 Omission。

R1 改为每个 question type 复用官方同形 `count_ratios()`：

- `correct_qa_ratio(all/valid)`；
- `hallucination_qa_ratio(all/valid)`；
- `omission_qa_ratio(all/valid)`；
- `qa_valid_num / qa_num`。

旧 `correct_qa_ratio` 与 `question_count` 继续作为兼容别名，分别等于
`correct_qa_ratio(all)` 与 `qa_num`。未识别 judge label 留在 all 分母但不进 valid 分母，强反例
用 Correct/Hallucination/Omission/Unexpected 四条锁为 `all=1/4, valid=1/3`。

该六类切片在 summary 中明确标为 `framework_supplementary`：它只重聚合官方逐题 C/H/O
结果；论文主表的官方 QA 列仍是总体 C/H/O。这样既能回答“各 question type 表现如何”，又不
把框架追加的诊断切片伪装成论文另报的主指标。

六类正式 question type 均由测试逐类锁定：Memory Boundary、Basic Fact Recall、Memory Conflict、
Generalization & Application、Multi-hop Inference、Dynamic Update。

## 3. memory_type 是否真的分开

是。`halumem_memory_type` 已按官方 `evaluation.py` 的特殊共享分母分别输出 `Event Memory`、
`Persona Memory`、`Relationship Memory`：

```text
total_num = all integrity records (including interference source) + update records
memory_integrity_acc = integrity_correct / total_num
memory_update_acc = update_correct / total_num
memory_acc = memory_integrity_acc + memory_update_acc
```

这不是三个阶段各用自己的分母，不能“修得更直观”而偏离官方。当前真实 Medium smoke 的
Event 分母是 2 条普通 integrity + 1 条 interference integrity + 4 条 update = 7；三类已分别落盘：
Event=`1/7 + 0/7 = 0.142857`，Persona=`0/102 + 0/102 = 0`，Relationship=`0/3 + 0/3 = 0`。

## 4. 既有真实 run 可否补分

可以零 API 重聚合，因为 `answer_scores.halumem_qa.jsonl` 已保存每题 `question_type` 与
`result_type`；无需重新调用 judge。当前 smoke 只有一题 Memory Boundary，历史 score row 可直接
得到该类 C/H/O=`1/0/0`。完整 full/pilot 才会自然覆盖六类；不得为了让 smoke 表格看起来齐全
而按 gold 类型重选付费题。

本轮不改既有 `outputs/` 历史 summary；新 evaluator 运行会生成完整字段，旧 artifact 可按上述
score row 离线重聚合。稳定语义已回填 `docs/survey/benchmarks/HaluMem.md` 与
`docs/reference/dataset-quirks.md`。

## 5. 验收门

- HaluMem evaluator / registered path / artifact runner / 文档门：`63 passed in 5.90s`；
- 全量回归：`1612 passed, 3 deselected, 2 warnings, 29 subtests passed in 151.89s`；
- 定向 `compileall`：exit 0；
- `git diff --check`：exit 0。

两条 warning 均来自既有 vendored A-Mem `ast.Str` 与 LightMem Pydantic v2 deprecation，和本轮
QA 聚合无关。
