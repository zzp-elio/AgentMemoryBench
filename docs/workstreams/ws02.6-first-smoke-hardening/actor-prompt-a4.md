# 发给 actor：LoCoMo A4

T1-T3 已完成并由架构师验收，不要重做。当前只执行
`docs/workstreams/ws02.6-first-smoke-hardening/plan-b0-b1-locomo.md` 的 **A4：最小
smoke + unified answer**，完成后停下等待架构师验收，不要继续 A5/A6。

开工只需依次阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b0-b1-locomo.md` 的第 1、2、4 节
4. `docs/reference/actor-handbook.md`
5. 官方 prompt 一手源：
   `third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:25-29,243-244,283-289`
   与 `third_party/benchmarks/locomo-main/global_methods.py:92-127`

不要重新跑全量基线，不要重复扫描全部 LoCoMo 数据，不要启动 reviewer subagent，不要
运行全量 pytest/compileall，不要更新 README/roadmap/frozen 文档。

实现范围：

- 把 LoCoMo smoke 改为首个 conversation × 前两个连续 turn × 首个 Phase-1 public
  question；question 选择和公开 metadata 均不得读取 evidence；
  `smoke_context_truncated` 只表示公开 history 是否被裁短。
- 保持 session 边界和 full odd turn；turn 无时间沿用 session 时间；caption 只拼一次，
  URL 不进入 method content。
- 新建 LoCoMo unified prompt builder 并注册为默认；普通题用官方 short-phrase prompt，
  category 2 加日期提示。
- LoCoMo answer LLM 配置跨 method 统一为 `gpt-4o-mini`、role=user、temperature=0、
  max_tokens=32、top_p=1；不要改其他 benchmark。
- 只修改 plan A4 列出的代码和直接相关测试。遇到需要改 v3 协议、metric、resume、真实
  method 或第三方算法时立即停工上报。

完成后只运行一次：

```bash
uv run pytest -q tests/test_prediction_cli.py tests/test_event_stream.py \
  tests/test_locomo_conversation_adapter.py tests/test_benchmark_registry.py \
  tests/test_config_profiles.py
```

通过后做一个本地 commit（不 push），commit message：
`feat(ws02.6): freeze LoCoMo smoke and unified answer contract`。

最后只回复四项：commit hash、测试尾行、实际改动文件、是否存在 plan 偏差/停工点。
