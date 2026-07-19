# LightMem × MemBench pair 投递与运行身份 R1 实现记录

> 施工 actor：Codex / GPT-5.6 sol（由派工架构师核实，本会话未发生模型/入口切换，也未使用
> subagent）。worktree=`/Users/wz/Desktop/mb-actor-lightmem-membench-pair-r1`，
> branch=`actor/lightmem-membench-pair-r1`，基线=`d2c1834`。零真实 API、零下载、零 push。

## 1. 生产投递修复

`MethodRegistration` 新增 benchmark-aware `consume_granularity_resolver` 与公开 getter。
五个内置 method 的 factory 和 manifest 共用同一组纯 resolver：A-Mem/SimpleMem 固定
`turn`；Mem0 保持 LongMemEval/HaluMem=`session`、BEAM=`pair`、其余=`turn`；LightMem
改为 HaluMem=`session`、LongMemEval/MemBench=`pair`、其余=`turn`；MemoryOS 保持
LongMemEval=`pair`、其余=`session`。

因此 MemBench FirstAgent 的 canonical `user→assistant` child 经
`build_turn_events → GranularityAggregator(pair) → LightMem.ingest` 只形成一个真实
`TurnPair`，backend 只收到一次 `add_memory()`；两侧真实 role/content/timestamp 保留，
pair candidate ids 同时含 `n:user`/`n:assistant`，零 placeholder。ThirdAgent 连续 user
不会互配，每条成为独立 dangling pair，再由 LightMem 补 structural assistant；局部 child id
可在不同 conversation 重复，隔离依赖 backend/storage namespace 与 isolation key，不伪造
全局 id。

vendored `SenMemBufferManager.big_buffer/buffer` 与 `ShortMemBufferManager.buffer` 都是实例字段，
源码已能证明跨 `add_memory()` 调用保持；本修复又直接消除了 FirstAgent split-call 路径。
因此首轮 preflight 的“必须先跑付费 100k sentinel 才能判断 STM 聚合”BLOCKED 判词已被 R1
订正，不再是 API blocker。

## 2. manifest 与 resume 语义

registered CLI 为每个 method × benchmark 写顶层 `method.consume_granularity` concrete 值。
它不属于 `protocol_version/prompt_track/profile/provenance_granularity` 的历史缺字段兼容组，
所以旧 manifest 缺字段、新旧 `turn↔pair` 任一方向变化都严格 mismatch；相同 concrete 值
才允许 match。

串行真实 v3 provider 在 manifest 盖章时交叉校验声明值与实例
`provider.consume_granularity`；不一致抛 `ConfigurationError`。workers>1 根进程仍使用
`_UnusedRootSystem`，不为校验提前构造真实 method；声明由注册级 resolver 生成并传入 worker，
每个 worker 构造真实实例后再 fail-fast 交叉校验。未注册的真实 v3 instance 可从实例补字段；
`LegacyProviderBridge` 不被强加该新身份，旧 bridge 兼容范围保持不变。HaluMem operation-level
路径复用同一 manifest helper，并由真实 provider 交叉校验，无需 benchmark 专用特判。

本次不 bump `LIGHTMEM_ADAPTER_VERSION`：LightMem 抽取/压缩/分段/向量算法 adapter 未变，
变化的是 benchmark→provider 消费契约；用独立 manifest 字段只失效真正身份变化的 run，避免
LoCoMo 等其他 benchmark 被全局 version 粗暴连坐。

## 3. 时间、原文与 question-time 单向边界

production-path 强反例锁定：FirstAgent 两侧 content 中的 `place/time` 原文逐字保留，各自
`time_stamp` 只取自身 `turn_time`，不跨侧 fallback；100k 风格双侧 pair 或 ThirdAgent 单侧
无时均保持 `None`，不从 QA time、兄弟 turn、相邻消息或 wall clock 造值。输入时间倒序时，
pair/call 顺序与每条 timestamp 都保持原样。

官方 `third_party/benchmarks/Membench-main/benchmark/MembenchAgent.py` 的
`INSTRUCTION_FIRST` 含 `Question: (current time is {time}) {question}`；现有 unified builder
继续逐字使用官方模板并只用 `Question.question_time` 填 answer/query 侧。registered artifact
测试同时断言该值进入 answer prompt、却不出现在任何历史 event 的 `timestamp` 或
`original_turn_time`。

R1 通过只读软链复核正式数据（未暂存）：8 文件时间倒序分布依次为
`3, 7, 2, 21, 0, 3, 1, 2`，合计 `39`；trajectory/source-step/canonical-turn 总数为
`4,260 / 452,245 / 767,075`，与架构师现场值一致。实现不排序、不修钟、不丢 turn。

## 4. 测试与强反例

- registry：锁 LightMem MemBench=`pair`、LoCoMo=`turn`、HaluMem=`session`，并锁 Mem0、
  MemoryOS 等动态 resolver 既有矩阵。
- production path：FirstAgent 一次真实 pair/一次 backend call/两个 child id；ThirdAgent
  两个连续 user 各自 singleton + placeholder；两侧不同时间、双侧/单侧 `None`、倒序时间、
  question-time 不反灌。
- manifest/runtime：实例 fallback、resolver/factory mismatch fail-fast、旧缺字段与
  `turn↔pair` 双向 resume mismatch、相同值 match；registered 串行和 isolated worker artifact
  都携带同源字段。
- prompt：保留既有官方模板逐字 parity；registered MemBench 额外锁 prompt/history 时间单向边界。

最终卡定向自检尾行：`412 passed, 1 warning in 9.11s`。唯一 warning 是 vendored
LightMem logging config 的 Pydantic V2 deprecation，与本 R1 修改无关。随后
`git diff --check` exit 0、无输出。

## 5. 偏差与环境动作

- 隔离 worktree 原先缺 gitignored `data/`、`models/`、`third_party/benchmarks/`，按卡 §6 建立
  指向主工作区的只读软链，用于数据复核和定向测试；三条软链均不暂存。
- 在最终卡定向集合前，先跑新增用例的小集合定位；其中首次 `uv run` 只完成本 worktree
  `.venv` 环境创建，随后复跑得到 `1 passed` 与 `35 passed`。这是卡允许的定向调试，未跑
  full pytest、compileall 或真实 API。
- 首次完整卡定向集合尾行是 `18 failed, 391 passed, 1 warning in 19.20s`：17 项均为
  `tests/test_prediction_cli.py` 的手工 `SimpleNamespace` registration 未升级新 resolver，
  1 项是隔离 worktree 不带 `.env` 时 native judge fixture 未显式给模型。R1 将这些公开契约
  fixture 显式补齐 `turn` resolver，并给离线 judge 固定 `gpt-4o-mini`；失败集复跑尾行为
  `45 passed in 3.26s`。未读取、链接或复制 `.env`/secret。
- 其余无 plan 偏差或停工点。

## 6. 架构师 R2：任务卡 EOF 空白修复

架构师首轮审读确认实质 diff 与卡内 412 项定向测试通过，但
`git show --check 8825a1f` 报任务卡 line 189 `new blank line at EOF`，因此首轮 commit
暂不能验收。R2 只删除任务卡 EOF 的多余空行，不改卡面指令、首轮实现、测试或上方
`412 passed, 1 warning in 9.11s` 记录；本节如实追加 R2 检查证据。

## 7. 架构师 R3：合流测试 fixture 契约升级

架构师在 main 合流后跑 full suite，原始尾行为
`9 failed, 1570 passed, 3 deselected, 2 warnings, 29 subtests passed in 146.32s`。
这 9 项均为测试 fake/fixture 漂移，不是生产 resolver、manifest 或 runtime fail-fast
错误：artifact runner 的 4 项失败来自 3 个手工 `SimpleNamespace` registration 未声明
`resolve_consume_granularity`；BEAM 两个 variant、LoCoMo 与 LongMemEval 的 probe 壳吞掉
factory 已解析的粒度，继续使用探针默认 `conversation`；MemoryOS 精确 manifest 预期漏掉
新增的顶层 `consume_granularity=session`。生产 fail-fast 正确暴露了这些不一致。

R3 只升级允许范围内的 fixture：三个 fake registration 显式声明与其 fake provider 一致的
`turn` resolver；三个 `_ProbeAsMem0` 接收并传递 factory 的真实
`consume_granularity`（BEAM=`pair`、LoCoMo=`turn`、LongMemEval=`session`）；MemoryOS
精确预期补 `session`。未删除或放宽任何生产校验，也未修改生产文件。

五个相关失败文件定向复跑尾行为 `42 passed in 17.15s`；原任务卡 7 文件加 R3 5 文件的
12 文件合流集合尾行为 `454 passed, 1 warning in 14.40s`。唯一 warning 仍是 vendored
LightMem logging config 的 Pydantic V2 deprecation；全程零真实 API、零 push。
