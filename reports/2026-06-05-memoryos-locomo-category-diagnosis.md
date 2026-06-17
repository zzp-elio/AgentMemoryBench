# MemoryOS-LoCoMo Category 对齐诊断

日期: 2026-06-05 11:05:32 CST

## 结论

当前证据显示，我们的 LoCoMo category 映射和本次实验输出没有发现错位。MemoryOS 论文/复现侧存在明显的 category 输出顺序风险，但还不能在未拿到作者原始 `all_loco_results.json` 或未复跑 release-code 参数前，直接断定论文表格一定错位。

## 已排除的问题

1. 原始数据不一致
   - `benchmarks/locomo-main/data/locomo10.json`
   - `memory_benchmark/methods/MemoryOS-main/eval/locomo10.json`
   - 两者 SHA256 一致，JSON 结构完全一致。

2. LoCoMo 官方 category 映射错误
   - LoCoMo 官方 `evaluation_stats.py` 汇总顺序是 `[4, 1, 2, 3, 5]`。
   - LoCoMo 项目页描述的类别顺序是 single-hop、multi-hop、temporal、commonsense/world knowledge、adversarial。
   - 因此映射为:
     - `4`: Single Hop
     - `1`: Multi Hop
     - `2`: Temporal
     - `3`: Open Domain / commonsense-world knowledge
     - `5`: Adversarial

3. 我们 adapter 或 score 聚合发生错位
   - adapter 读取后的 `(question_id, category)` 顺序与原始 LoCoMo 非 adversarial QA 完全一致。
   - `predictions.jsonl` 与 `scores.jsonl` 的 category mismatch 数量为 0。
   - 本次分布为 `1:282, 2:321, 3:96, 4:841`，与原始 LoCoMo 数据一致。

4. 单纯 F1 定义差异导致错位
   - 用 MemoryOS 仓库自带简化 F1 对同一批 predictions 重算后，整体模式仍然类似。
   - 因此 F1 定义差异存在，但不能解释当前“像错位”的主要现象。

## 关键风险点

MemoryOS README 的复现入口是:

```bash
cd eval
python3 main_loco_parse.py
python3 evalution_loco.py
```

但 `evalution_loco.py` 使用:

```python
for category, f1_scores in category_f1.items():
```

它不会按 LoCoMo 官方 `[4, 1, 2, 3, 5]` 重排，而是按结果 JSON 中 category 首次出现顺序输出。

对 LoCoMo10 原始数据和 MemoryOS bundled 数据检查后，category 首次出现顺序是:

```text
[2, 3, 1, 4, 5]
```

对我们的 predictions 模拟运行 MemoryOS `evalution_loco.py`，输出顺序也是:

```text
Category 2
Category 3
Category 1
Category 4
```

这说明如果论文作者直接根据该脚本输出人工填表，而没有显式映射 category id，就存在较高的表格错位风险。

## 数值错位信号

不考虑类别名，只做数值最近匹配时，最佳配对是:

| 我们类别 | 我们 F1 | 最接近论文列 | 论文 F1 | 差值 |
| --- | ---: | --- | ---: | ---: |
| Single / 4 | 51.86 | Open Domain | 48.62 | 3.24 |
| Multi / 1 | 37.24 | Single Hop | 35.27 | 1.97 |
| Temporal / 2 | 41.26 | Multi Hop | 41.15 | 0.11 |
| Open / 3 | 25.91 | Temporal | 20.02 | 5.89 |

这个模式支持“论文表格可能有列错位”的怀疑，但它不是最终证明。

## 未排除的问题

1. MemoryOS 论文表格可能来自作者私有评测脚本，而不是开源 `evalution_loco.py`。
2. 本次运行按论文文字参数优先；MemoryOS release eval 代码参数与论文文字参数不完全一致。
3. GPT-4o-mini API/backend、随机性、prompt 和 MemoryOS 内部更新过程可能导致 category 分数非线性变化。
4. 当前没有作者原始 `all_loco_results.json`，无法直接验证论文表格每个数字对应的 category id。

## 建议下一步

1. 不立即断言论文错位，先把它作为高优先级假设。
2. 如果要继续排查，优先用 release-code 参数跑一个小样本对照，观察输出顺序和分数方向。
3. 如果要严格复现论文，最好拿到或复构 MemoryOS 论文中的原始 `all_loco_results.json`，否则只能做合理复现和差异说明。
