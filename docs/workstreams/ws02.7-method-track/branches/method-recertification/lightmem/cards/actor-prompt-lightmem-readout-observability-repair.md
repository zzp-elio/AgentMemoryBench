# Actor 卡：LightMem 产品 readout 保真与 embedding 观测修复

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你是施工 actor，不是架构师；本卡就是完整、自包含的执行 prompt。
允许自行组织 subagent，但不得扩大 scope；发生实质使用时须在完成报告披露，主 actor 对最终
diff 与报告负责。

## 0. 这张卡解决什么

用户已经真实执行 LightMem × LongMemEval latest-v6 单/双 worker B11：

- `lm-lme-v6-r1q1-w1-s-cleaned`
- `lm-lme-v6-r1q1-c2-w2-s-cleaned`

prediction/evaluate、隐私、N/A 与 worker 隔离均走通，但架构师开箱发现三项同源缺口：

1. Qdrant payload 保存 `2023-05-20T03:29:00.000`，unified `formatted_memory` 却只剩
   `20 May 2023, Sat`。原因是公共 `answer_context` 误用了 LoCoMo author harness 的
   pretty-date formatter；这会删除时分，可能改变 LongMemEval 时间题答案。
2. manifest/model inventory 声明 `lightmem-embedding`，但真实
   `efficiency_observations.prediction.jsonl` 没有任何 `embedding_call`，overall
   `embedding_tokens={}`，与 checklist B7“LLM + embedding 调用都可观测”冲突。
3. 同一题的权威 `RetrievalEvidence.provenance_granularity="none"`，legacy retrieval
   metadata 却因 `items is not None` 写成 `"turn"`。evaluator 目前读 v1 evidence，所以分数
   没算错，但公开 artifact 自相矛盾。

本卡修复产品 readout、embedding observation 与逐题 metadata 真值；不改 LightMem 的抽取、
压缩、分段、向量、online-soft、检索排序或 benchmark 数据。

## 1. 隔离环境与最小读序

- worktree：`/Users/wz/Desktop/mb-actor-lightmem-readout-observability`
- branch：`actor/lightmem-readout-observability`
- 基线：派发时最新 `main`；先原样记录 `git rev-parse --short HEAD`

若路径或分支已存在，停工报告，禁止删除/复用。若用户尚未创建，可执行：

```bash
git -C /Users/wz/Desktop/memoryBenchmark worktree add \
  /Users/wz/Desktop/mb-actor-lightmem-readout-observability \
  -b actor/lightmem-readout-observability main
cd /Users/wz/Desktop/mb-actor-lightmem-readout-observability
uv sync
```

只按顺序读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/README.md`
4. `docs/reference/method-integration-checklist.md` 的 B4、B7、B11
5. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
   lightmem-longmemeval-b11-command-pack.md` 的机器验货段
6. `docs/reference/actor-handbook.md` §0-§4
7. 本卡允许清单内的生产代码与测试

不得重扫数据集、历史 survey 或全部 workstream；真实 run 已是本卡的一手反例。

## 2. 已裁产品 readout 语义

### 2.1 公共 `formatted_memory` 必须忠实产品接口

Phase 1 主线是 `MemoryProvider.retrieve() -> RetrievalResult.formatted_memory`，再由
benchmark-owned unified answer builder 构造 prompt。公共 `formatted_memory` 必须对应
vendored `LightMemory.retrieve()` 的产品语义：每条非空时间记忆输出
`"{time_stamp} {weekday} {memory}"`，保留完整 ISO timestamp；多条按检索顺序以换行连接。

- 禁止把 `2023-05-20T03:29:00.000` 降精度成 `20 May 2023`。
- `time_stamp is None` 时与 vendored missing-time 扩展一致，只输出 memory 文本，不能出现
  `None None`，也不能凭 weekday 单独造时间前缀。
- 空字符串等非 `None` 历史边界保持 vendored 行为，不做额外“智能修复”。
- `metadata["answer_context"]` 必须与最终 `RetrievalResult.formatted_memory` 字节一致；runner
  不能一份、metadata 又一份。
- 不从 question time、wall clock、相邻 turn 或 gold 补时间。

`_format_lightmem_memory()` 是 LoCoMo author harness 的 pretty-date/speaker prompt 配件，允许
继续服务 method 官方完整 builder；它不得再决定公共 unified readout。adapter 已有
`_format_lightmem_memory_as_official_retrieve()` 雏形，应收紧为 vendored 产品行为并复用，
不要复制第三份 formatter。

这一裁决对五 benchmark 的公共 product readout 一致生效，不新增 `if benchmark == ...` 的
损失性格式分支。LoCoMo 作者 prompt 可继续用自己的布局，但旧 LoCoMo unified answer artifact
因此只保留历史证据、不能冒充修复后的 readout 证据；implementation note 必须明说。

### 2.2 author prompt 与 unified readout 分层

`RetrievalResult.prompt_messages` 中为历史/author builder 保留的 LightMem 官方 LoCoMo 或
LongMemEval message 布局不得被本卡删除；本卡只把公共 `formatted_memory` 从 author formatter
解耦。不能为了让两个字符串相同而废掉作者完整 builder 所需的 speaker/system/user 结构。

### 2.3 逐题 provenance metadata 跟随 v1 evidence

`_retrieve_native()` 必须只构造一次 `RetrievalEvidence`，然后：

- `RetrievalResult.evidence` 使用它；
- legacy `metadata["provenance_granularity"]` 写同一个对象的
  `provenance_granularity`。

因此 LongMemEval/BEAM/HaluMem 为 `none`，LoCoMo online-soft 与符合条件的 MemBench 才可为
`turn`。不得再用 `items is not None` 单独猜粒度。manifest 里的旧静态字段属于 M1 已声明的
兼容债，本卡不改协议/manifest，也不得让 evaluator 回读 legacy metadata。

## 3. 已裁 embedding observation 语义

在每个 backend 创建后，对其**实际被算法调用的同一个** `text_embedder.embed` 安装一次透明
observer；不得另算向量、不得替换模型、不得改变参数/返回值/异常。

每次成功调用记录一条现有 `EmbeddingCallObservation`：

- `model_id="lightmem-embedding"`；
- build 中记 `stage=memory_build`，query 中记 `stage=retrieval`；
- latency 包围原始 `embed()`，来源为 `framework_timer`；
- 本地 SentenceTransformer 的输入 token 用它实际 tokenizer、实际 truncation/max sequence
  设置计数，来源为 `tokenizer_estimate`；记录的是模型实际消费的 token，不是字符数，也不是
  未截断的理论长度；
- 只在原调用成功后落 observation；失败语义保持原异常，不写“成功调用”；
- observer 重装必须幂等，同一 backend 不得双计；
- 关闭 efficiency collector 时零额外计数行为；
- conversation/question scope 与并行 worker 不得串写。若 current main 的 ContextVar 边界使
  任一真实 build/retrieval 调用无法归属，停工提交最小复现，不得静默丢 observation。

测试必须用 fake embedder/tokenizer，零模型下载。不要调用 upstream 累计
`get_token_statistics()` 冒充逐调用 observation；它的 local HF token 当前恒 0，且没有阶段/
latency/作用域。

registered v3 由 framework reader 调 answer LLM；model inventory 不应继续列一个该路径从不
调用的 `lightmem-answer-llm`。保留 `lightmem-memory-llm`、`lightmem-embedding`，framework
answer model 仍由 runner 追加。若一手 current code 证明 registered 主路径实际引用前者，停工
举证；不要凭旧 direct `get_answer()` 单测维持虚假 inventory。

## 4. 版本与 resume 身份

`LIGHTMEM_ADAPTER_VERSION` 从 `conversation-qa-v6` 升为 `conversation-qa-v7`。虽然 memory
build 算法不变，但公共 readout 与效率 artifact 契约变了，旧 run 不能 resume 成一半 v6、一半
v7。同步更新准确的 manifest/fixture/test 名称；不得把 v6 放进兼容集合。

不要新增另一套 `native/unified` 轨名，不改 TOML profile，不做 author section 迁移。

## 5. 允许修改文件

```text
src/memory_benchmark/methods/lightmem_adapter.py
src/memory_benchmark/methods/registry.py
tests/test_lightmem_adapter.py
tests/test_lightmem_registered_prediction.py
tests/test_method_registry.py
docs/reference/integration/lightmem.md
docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
  lightmem-readout-observability-repair.md
```

不得改 benchmark adapter、event stream、provider protocol、collector/entity/storage、TOML、
evaluator、runner、third_party、其它 method、父/支线 README、现有 run artifacts 或 command pack。
若现有 collector API 无法表达本卡 contract，停工交回，不自行扩协议。

## 6. 必测强反例

1. 非空 ISO timestamp 含时分秒/毫秒：public `formatted_memory` 与 vendored product formatter
   字节一致，且不等于 pretty-date 版本；会在 current main 失败。
2. `time_stamp=None`：只输出 memory；不得出现 `None`、weekday-only prefix 或 synthetic time。
3. 两条 memory 保持 retrieval 顺序；content、score、source ids 与 speaker payload 不变。
4. LoCoMo author prompt 仍使用既有 pretty-date/speaker 布局，而 unified public
   `formatted_memory` 使用产品格式，证明两层没有再次耦合。
5. LongMemEval 非空真实形状的 `answer_context == formatted_memory`，完整时分进入 benchmark
   unified builder 的 `History Chats`，question time 仍只在 `Current Date`。
6. LongMemEval 的 v1 evidence 与 metadata 都是 `none`；LoCoMo valid 例两处都为 `turn`。
7. fake build 至少两次 embed、fake retrieval 一次 embed：逐条 observation 的 stage、model id、
   token、latency source、conversation/question id 正确，summary 不再 `embedding_tokens={}`。
8. observer 幂等；collector disabled 时不写；original embed 抛错时异常原样且无成功 record。
9. 两个并发 conversation 的 embedding observation 不串 id、不丢 call。
10. model inventory 不含未使用 `lightmem-answer-llm`，仍含 framework answer、memory LLM 与
    embedding；manifest instrumentation identity 不丢。
11. adapter manifest 为 v7，旧 v6 不可 resume；无真实 API/模型/数据依赖。
12. 所有新增/修改 Python 函数、nested helper 与测试函数有准确中文 docstring。

## 7. 唯一定向自检

```bash
uv run pytest -q \
  tests/test_lightmem_adapter.py \
  tests/test_lightmem_registered_prediction.py \
  tests/test_method_registry.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_documentation_standards.py
```

允许失败定位时跑单条；完成报告须给上述最终组合的真实尾行。不得调用真实 API、下载模型、
改 outputs、跑全量 pytest 或 compileall。

## 8. 明确不做与停工条件

不处理本轮发现的 retrieval summary `mean_score=0.0`（另一张并行卡负责）；不压制
`768>512` tokenizer warning；不修 LightMem INFO log 为空；不调参数、不改 top-k、Recall/NDCG、
gold、question-time cutoff 或 placeholder。

以下任一出现即停工：

- 产品 readout 保真必须改 third_party/runner/protocol 才能完成；
- token 计数只能靠第二次真实 embed 或网络调用取得；
- observer 改变原始向量、调用次数、异常或线程顺序；
- v7 导致允许清单外 production contract 必改；
- 定向失败暴露与本卡无关的真实缺陷且 15 分钟内不能消解。

停工 note 写最小复现、源码锚与已完成安全部分；禁止删强反例或把 expected 改回损失性行为。

## 9. 提交纪律与报告

- `git diff --check`；add 前后各看 `git status --short`；只显式 add，禁 `-A`/`.`。
- 本地单 commit，不 amend、不 push；建议：
  `fix(lightmem): preserve product readout and embedding observations`
- note 必须记录 v6 真实反例、产品/author 分层、v7 失效面、embedding 计量来源、测试尾行与偏差。
- Co-Authored-By 只写可核实真实模型；模型切换无法核实时不猜。
- 按 actor-handbook §4 回报：commit hash、最终测试尾行、实际改动文件、偏差/停工点、subagent
  分工和模型切换。到此停止，等待架构师 full diff 与强验收。
