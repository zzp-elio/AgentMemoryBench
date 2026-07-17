# Actor 返工卡：Metric Pack M0 R1 artifact details 收口

> **给当前 actor 的执行指令：你就是用户已选中的执行者。** 本卡被发送到当前 actor
> 会话即代表用户已经完成选择与授权，请直接执行；不要再选择、派发或等待另一个 actor。
> 这是首轮 `760f251` 的同 worktree 线性 follow-up，不新建 worktree、不 amend、不 push、零真实
> API。actor 可自行组织 subagent，但本卡只有一个局部修复，通常无需分包；若实质使用须披露。

## 0. 为什么返工

首轮主体经架构师 full diff 与定向复跑成立：Recall 公共内核复用既有 group 公式，四家壳层政策
未漂移；normalized EM / substring EM 公式、registry 启用面与 artifact-only 路径都正确，未发现
删断言/skip/xfail/吞异常等“为过测作弊”。

唯一阻断是首卡 §3.1 的稳定 artifact 合同没有完整落地：它要求所有 supplementary answer metric
details 同时写 `normalized_prediction` 与 `normalized_gold`。`NormalizedExactMatchEvaluator` 已写，
但 `SubstringExactMatchEvaluator` 只写了 token arrays，缺这两个字符串字段。不能把 tokens 当作
同名字段的替代品；报告消费者需要统一 key。

## 1. 开工边界

继续使用：

```text
worktree: /Users/wz/Desktop/mb-actor-metric-pack-m0
branch: actor/metric-pack-m0
base follow-up commit: 760f251
```

先执行并核对：

```bash
cd /Users/wz/Desktop/mb-actor-metric-pack-m0
git status --short
git log -3 --oneline
```

允许既有 `?? data` 软链；不得 add。若 HEAD 不是 `760f251`，或除 `data` 外已有未知改动，立即
停工报告，不覆盖现场。

本轮只需读：`AGENTS.md`、本卡全文、首卡 §3.1-§3.3、下列两个允许文件及首轮 implementation
note 尾部。不要重读整套 workstream。

## 2. 唯一生产修复

仅改：

```text
src/memory_benchmark/evaluators/answer_metrics.py
```

在 `SubstringExactMatchEvaluator.evaluate()` 中：

1. 各调用一次 `normalize_answer(answer.answer)` 与 `normalize_answer(gold.answer)`；
2. 由这两个已归一化字符串 `.split()` 得到 token，避免为了 details 再做第二轮归一化；
3. 保持现有 directional contiguous-token 公式、空 gold=0、metric name、strategy、direction、
   tier/version、abstention 与所有数字不变；
4. 在 details 增加精确键：

```text
normalized_prediction: <answer-text-v1 string>
normalized_gold: <answer-text-v1 string>
```

不得改 normalizer 语义，不得把 substring 退回裸字符包含，也不得改 normalized EM/F1/Recall。
若 `normalized_tokens` 因本修复不再被该模块使用，可只删除本文件对应的 unused import；不要删除
`answer_text.py` 的公共 helper 或导出。

## 3. 强反例

仅改：

```text
tests/test_answer_metric_pack.py
```

至少给现有 substring 正向例补断言：

```text
normalized_prediction == "alice moved to seattle in 2023"
normalized_gold == "seattle"
```

并给 empty-normalized-gold 例断言 `normalized_gold == ""`。保留全部现有方向、token boundary、
连续性与空 gold 断言；禁止删除或放宽测试。

## 4. 施工记录与允许清单

在首轮 note 末尾追加 R1 小节，不改写首轮历史：

```text
docs/workstreams/ws02.7-method-track/branches/metric-pack/notes/metric-kernels-m0-implementation.md
```

本轮允许修改严格只有三条：

```text
src/memory_benchmark/evaluators/answer_metrics.py
tests/test_answer_metric_pack.py
docs/workstreams/ws02.7-method-track/branches/metric-pack/notes/metric-kernels-m0-implementation.md
```

不要碰 registry、Recall、runner、README、TOML、third_party、outputs 或其它测试。

## 5. 自检、commit 与报告

只跑：

```bash
uv run pytest -q tests/test_answer_metric_pack.py tests/test_answer_f1.py tests/test_evaluator_registry.py tests/test_retrieval_metric_kernel.py
git diff --check
```

仅显式 add 上述三条，禁止 `-A`/`.`；提交前后查看 `git status --short`。新建线性 follow-up commit，
不 amend `760f251`，不 push。建议 message：

```text
fix(metrics): complete substring artifact identity
```

按 actor-handbook §4 回报：follow-up hash、测试尾行、实际三文件、偏差/停工点、subagent/模型切换。
到此停止，等待架构师强验收。
