# Actor 卡 M5-mem0：frozen 前三项取证审计（零生产代码）

> 派发日 2026-07-14。这是**纯取证卡**：只读代码+写一份 note,不改任何
> 生产代码、测试或 third_party,不调真实 API。产出 =
> `docs/workstreams/ws02.7-method-track/notes/m5-mem0-audit.md`。
> 背景:mem0 即将 method-frozen-v1,架构师对表(checklist B11 冻结门)
> 查出三项缺口需要一手证据,全部是"读代码给锚"性质,适合独立取证。

## 0. Git 纪律
```
git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m5mem0 -b actor/m5-mem0-audit
cd /Users/wz/Desktop/mb-actor-m5mem0 && uv sync
```
禁 push;note 写完本地 commit 一次即可。禁跑全量(纯文档无需);若你
写了任何验证脚本,放 scratch 不入库,note 里贴脚本关键行与输出。

## 1. 取证项一:B8+ 外部调用韧性清单（checklist B8+ 判据,2026-07-14 新增）

列出 mem0 method 在本框架运行时的**全部外部(网络)调用点**,每点一行:
调用点 file:line / 用途 / 超时配置 / 重试配置 / 失败后 state 语义。

已知起点(架构师初核,你补全并逐点验证):
- mem0 内部抽取 LLM(OpenAI-compatible):`api_timeout_seconds`/
  `api_max_retries` 从 `configs/methods/mem0.toml:20-21` 进
  adapter(mem0_adapter.py:100-101 附近)——**核这两个值真正落到
  客户端构造**(顺着 config 流到 mem0 LLM client 的 file:line,签名默认值
  不作数,要实际传参链)。
- 框架 reader LLM(答题):找 adapter 的 reader_client 构造与超时设置。
- embedding:`embedding_provider="huggingface"`=本地 SentenceTransformer
  (mem0_adapter.py:93),**验证零网络调用**(模型加载来自本地缓存?首次
  下载算不算调用点?如实记录)。
- qdrant(本地模式)与 mem0 官方 SQLite:验证本地零网络。
- 失败 state 语义:ingest 中途失败后,`clean_failed_ingest_state` 能否
  清干净(M2 已有测试,给测试名与锚即可,不重跑)。

**判据**:每个网络调用点必须"有超时+有重试或明确失败语义+失败不留半写
state"。有缺口的点如实列出,不修(修是后续卡的事)。

## 2. 取证项二:B7 native 注入 token 审计（efficiency-injected-tokens-policy 口径）

mem0 native 三格(locomo/longmemeval/beam)刚落地(M4)。逐格核:
**效率观测统计的"注入记忆 token" ≡ native prompt_messages 里实际嵌入的
记忆文本**(政策=两轨统一记"记忆载荷 token",native 模板开销不计入,
见 `docs/reference/efficiency-injected-tokens-policy.md`)。
- 锚出 mem0 adapter 效率统计中记忆载荷的计量点(file:line);
- 锚出三个 native builder 把 memories 嵌进 prompt 的位置
  (mem0_adapter.py `_build_mem0_locomo_prompt`/`_build_mem0_longmemeval_prompt`/
  `_build_mem0_beam_prompt`);
- 判断:计量的文本集合与嵌入的文本集合是否同一(载荷≡嵌入)。若失配,
  给出失配的具体形态(多计了模板?漏计了时间戳前缀?),不修。

## 3. 取证项三:native run 的评测路由

架构师要裁决"native 格评测口径",需要事实:对一个 native run
(如 `outputs/runs/mem0/locomo/smoke/native/mem0-locomo-native-s1`),
`memory-benchmark evaluate --run-id ... --metric locomo-judge` 会用哪个
judge prompt/模型?
- 顺着 evaluate 调用链锚:evaluator 构建时是否读 run manifest 的
  config_track/bundle 的 `judge_profile`(M4 注册的
  `MEM0_NATIVE_JUDGE_PROFILES`),还是永远用注册表默认 judge;
- 免费指标(locomo-f1/recall 等)对 native run 的 artifacts 是否口径无关
  照常可评(预期是,给锚);
- 只答"现状是什么+锚",不评价应该是什么(那是架构师裁决)。

## 4. 完成门
note 三节硬答案(每节一张锚表);本地 commit;停工条件:任何一节的事实
无法在 30 分钟内锚定(说明结构比预期复杂),停工列出卡住的调用链。

## 施工报告（actor 填写）
（待填）
