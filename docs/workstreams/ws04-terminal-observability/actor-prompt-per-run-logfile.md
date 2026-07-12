# 卡 Y：per-run 日志持久化（method logger → logs/method.log）

> 2026-07-13 架构师（Opus 4.8）开卡。ws04 最小前置子集：把每个 run 里
> **已经在生成、却只冲到终端的** method 日志落盘,让成本/异常可事后追溯。
> **纯离线、零真实 API、不碰 third_party、不碰 method 算法。** 不做 ws04 的终端
> 观测大改（Rich 心跳、tqdm 治理等留 ws04 本体）。

## 先读（按序）
1. `AGENTS.md`
2. `docs/reference/actor-handbook.md`
3. `src/memory_benchmark/observability/run_context.py`（`logs_dir` 在 `:86`,
   run 生命周期/logs 目录准备在 `:146` 附近；现有只写 `run.log` 两行 + `events.jsonl`）
4. 本卡

## 背景（架构师一手核过）
现在每个 run 的 `logs/` 只有 `run.log`（**两行**:起止）+ `events.jsonl`（4 类粗事件）。
而真正的诊断信号——method 自己 logger 打的 INFO/WARNING(如 LightMem `LightMemory`
logger 的 "force_segment=.. force_extract=.."、segment 数、**"Created N MemoryEntry
objects"**、token 统计、"No entries found in database" 警告)——**全冲到终端、没落文件**。
后果:一次 run 跑完无法回看"为什么这格 0 分/为什么这格便宜/记忆是否真的构建了"。
这些日志**已经在生成**(method 的标准 `logging`),缺的只是"落盘"。

**当前活案例(本卡直接服务的诊断)**:1-round LightMem smoke 出现空库,无法判定是
segmenter 切出空 buffer 还是抽取返回 0——因为 "Created N" 那行是 INFO、没落盘。本卡
落地后重跑即可读到 N。

## 设计（架构师定,照此实现）
**run-scoped root-logger FileHandler → `logs/method.log`,run 起挂、run 止摘。**
- 在 run 生命周期开始处(run_context 准备 logs_dir 后)给 **root logger** 挂一个
  `logging.FileHandler(logs_dir/"method.log")`,level=**INFO**,带时间戳格式。
- **run 结束/异常都要移除该 handler 并 close**(try/finally),避免:① handler 泄漏
  (重复 run/并行 run 累积)、② 跨 run 串写。
- **降噪**:加一个 filter 过滤掉已知刷屏的第三方 namespace(至少
  `transformers`、`urllib3`、`httpx`、`sentence_transformers`;它们的 INFO 无诊断价值)。
  method 自己的 logger(如 `LightMemory`)与框架 INFO 保留。
- **不改终端行为**:终端照常打印(现有 handler 不动),本卡只是**额外**落一份文件。
- **不改 `run.log`/`events.jsonl` 现有内容**(可保留;`method.log` 是新增第三份)。

## 施工纪律
- TDD；每 task 一 commit；本地 commit 不 push。
- 零真实 API；中文 docstring；不改 third_party/method 算法。
- 线程安全:并行 conversation 下 FileHandler 要安全(Python logging 本身线程安全,
  但确认 handler 只挂一次、run 级而非 conversation 级)。
- 遇未覆盖 → 停工写断点。

## Task 1：run-scoped method.log FileHandler
- 在 run_context / run 生命周期挂载点实现挂/摘(try/finally),写 `logs_dir/method.log`。
- INFO level + 时间戳格式 + 第三方降噪 filter。

## Task 2：测试（fake、无真实 API）
- 跑一条最小 fake run(用现有 fake reader/method 或直接对一个测试 logger 发 INFO),
  断言:① `logs/method.log` 被创建;② 含预期 INFO 行;③ run 结束后 root logger 上
  **不再残留**该 handler(断言 handler 已摘,防泄漏);④ 被降噪的 namespace 不出现。
- 若能低成本:断言两次连续 run 各写各的 `method.log`、不串写。

## 唯一自检命令
```bash
uv run pytest -q tests/  # 定向到你新增/改动的 observability 测试 + 现有 run_context/observability 测试
```
（不跑 `-m api`。）全量回归架构师验收时跑。

## 明确不做
- 不做 Rich 进度心跳/tqdm 治理/终端重排(ws04 本体)。
- 不改 method 算法、third_party、terminal 现有打印。
- 不把 secret/private 数据写进日志(method logger 若打了 prompt 内容属其既有行为,
  本卡不新增泄漏面;但**不要**新增打印 gold/evidence/judge label 的日志)。

## 停点
Task 1-2 完成 + 自检通过 + 各 commit 就停,报告(实际模型名自查系统提示)。
落地后架构师会重跑 1-round smoke 用 `method.log` 诊断空库问题。
