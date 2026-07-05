# CLI v2 与输出目录布局设计

实现状态：2026-06-23 已完成主体实现与 focused 验证。`predict smoke/formal`、新旧
输出布局兼容和 `evaluate --run-id` 新旧目录解析均已落地；legacy `predict --profile ...`
仍保留兼容。

## 背景

当前 CLI 同时承载历史 `--profile smoke|official-full`、smoke 裁剪参数、正式实验分批参数和
评测参数。参数可用但不够直观，尤其是：

- smoke 和正式实验没有在命令结构上分开。
- `--smoke-turn-limit`、`--smoke-max-workers` 等名字暴露历史实现细节。
- `--confirm-api` / `--confirm-full` 语义像内部保护开关，不像用户意图。
- outputs 目录按 run id 平铺，长期实验增多后难以按 method / benchmark 查找。

本设计只整理 conversation-QA 主线 CLI，不改变 method 算法、benchmark adapter 或 metric
定义。

## 目标

1. 用户主路径收敛为 `predict smoke`、`predict formal` 和 `evaluate`。
2. smoke 明确用于低成本链路测试，允许裁剪历史和限制问题数，不要求 evidence 完整覆盖。
3. formal 明确用于正式口径实验，不裁剪历史、不限制问题；可用 conversation budget 分批推进。
4. 所有参数边界都有清晰异常信息。
5. 新输出目录按 method / benchmark / variant / mode 归类，同时兼容旧 `outputs/<run_id>/`。

## 推荐命令

### Smoke

```bash
memory-benchmark predict smoke \
  --method mem0 \
  --benchmark locomo \
  --run-id 20260623-1430-mem0-locomo-smoke-2conv-20rounds-1q \
  --allow-api \
  --conversations 2 \
  --rounds 20 \
  --questions-per-conversation 1 \
  --workers 2
```

语义：

- `--conversations N`: 最多抽 N 个 conversation；真实数量不足时取 min。
- `--rounds N`: 每个 conversation 最多保留 N 个完整 round；LoCoMo 在 runner 层转换为
  `2N` 个 turn，LongMemEval adapter 直接按完整双 turn round 裁剪。
- `--questions-per-conversation N`: 每个 conversation 最多问 N 个问题；真实可用问题不足时取 min。
- `--workers N`: conversation 并发数；实际 worker 数取 `min(N, selected_conversations)`。
- smoke 不支持 resume，也不支持 retry failed；失败后换 run id 重跑。

### Formal

```bash
memory-benchmark predict formal \
  --method mem0 \
  --benchmark longmemeval \
  --variant s_cleaned \
  --run-id 20260623-1600-mem0-longmemeval-s-formal \
  --allow-api \
  --conversation-budget 5 \
  --workers 4
```

语义：

- `--conversation-budget N`: 本次命令最多推进 N 个未完成 conversation；剩余不足 N 时取 min。
- formal 不裁剪历史、不限制 question；选中的 conversation 必须完整 add 并回答全部问题。
- formal 支持 resume；resume 时允许改变 `--conversation-budget`、`--workers`、
  `--retry-failed` 和 `--allow-api`。

### Evaluate

```bash
memory-benchmark evaluate \
  --run-id 20260623-1600-mem0-longmemeval-s-formal \
  --metric longmemeval-judge \
  --judge-profile compact \
  --allow-api \
  --workers 8
```

`--workers` 在 evaluate 中表示 judge 并发数。

## 强校验规则

- `predict smoke` 不允许 `--resume` 或 `--retry-failed`。
- `predict formal --retry-failed` 必须同时传 `--resume`。
- `--workers`、`--conversations`、`--rounds`、`--questions-per-conversation`、
  `--conversation-budget` 必须为正整数。
- smoke 的 `--conversations`、`--questions-per-conversation` 超过真实数量时取 min，不报错。
- formal 的 `--conversation-budget` 超过剩余未完成数量时取 min，不报错。
- method / benchmark / variant 必须由 registry 校验。
- 当前 LoCoMo 和 LongMemEval 要求 method 满足 conversation-QA memory provider 协议；
  未来新 benchmark 可声明新的接口要求。
- `--allow-api` 是真实 API 调用保护；没有它时，任何需要 API 的 predict/evaluate 都应在读取
  secret 或构造第三方 method 前失败。
- `--confirm-api` 暂时保留为 deprecated alias，行为等同 `--allow-api`。
- `--confirm-full` 暂时保留为 deprecated no-op 或兼容字段；新 CLI 不需要它。
- `--answer-prompt-file` / `--answer-prompt-profile` 不进入 CLI v2 主路径；retrieve-first
  架构下 method 返回完整 `prompt_messages`，prompt override 未来按单独需求设计。
- `run` 与 `calibrate-smoke` 暂时保留兼容，但文档不作为正式主路径推荐。

## 输出目录布局

新 run 使用 method-first 目录：

```text
outputs/runs/
  mem0/
    locomo/
      smoke/
        20260623-1430-mem0-locomo-smoke-2conv-20rounds-1q/
      formal/
        20260623-1600-mem0-locomo-formal/

  lightmem/
    longmemeval/
      s_cleaned/
        formal/
          20260623-1700-lightmem-longmemeval-s-formal-5conv/
```

没有 variant 的 benchmark 省略 variant 层。旧 `outputs/<run_id>/` 不迁移、不删除；evaluate 和
resume 必须同时支持旧目录和新目录。同名 run_id 同时出现在 legacy 与 v2 目录，或出现在
多个 v2 目录时，evaluate 必须报 ambiguity，不能静默选择其中一个。

## 兼容策略

第一阶段实现：

- 新 CLI 写法可用。
- 旧 `predict --profile smoke|official-full ...` 暂时继续可用，但内部映射到
  `smoke/formal`。
- 旧参数 `--smoke-turn-limit`、`--smoke-conversation-limit`、`--smoke-max-workers`、
  `--max-new-conversations`、`--question-limit-per-conversation` 暂时保留为 alias。
- README 和后续示例只展示新 CLI。

第二阶段再考虑删除 deprecated 参数。

## 自检

- 无 `TBD` / `TODO` 占位。
- smoke 与 formal 的语义不冲突。
- 输出目录兼容旧 run，不会破坏已完成实验资产。
- 所有用户可触发边界都有明确错误策略。
