# MemoryOS 接入实例（B1-B11 逐项）

> 判据模板：`../method-integration-checklist.md` §B；勾选总表：
> `../integration-status.md`。
> 状态：**M1 一手取证 + M2 离线施工/强验收通过；track identity M0 后进入 B11 五格真实 smoke。**
> 证据底：`ws02.7/notes/m1-memoryos-evidence.md`、
> `ws02.7/notes/m2-memoryos-adapter.md`。

- adapter：`src/memory_benchmark/methods/memoryos_adapter.py`
- 算法运行源：vendored `third_party/methods/MemoryOS-main/memoryos-pypi/` 通用产品引擎
- native 格：仅 LoCoMo；其余四格 single-track collapse
- 2026-07-15 离线门：定向 146 项、M2 registry 返工定向 6 项；主树全量
  `1176 passed, 3 deselected, 2 warnings, 4 subtests passed`

## 0. 接口调用面

| 框架钩子 | adapter 行为 | 官方接口/状态 |
|---|---|---|
| `ingest(TurnPair)` | LongMemEval 走 pair；orphan/dangling 空侧保留，不丢 turn | `Memoryos.add_memory(user_input, agent_response, timestamp)` |
| `ingest(SessionBatch)` | LoCoMo 走 session，按官方 speaker_a 开 page/另一 speaker 回填；裸文本注入，图片经框架统一 helper | 同上逐 page 注入 |
| `end_conversation` | no-op；STM/MTM/LPM 均能在 retrieve 时读出 | 无额外 flush |
| `retrieve(query)` | 复刻产品 `get_response` 的检索步骤 1-7，覆盖 STM、MTM、user/assistant knowledge；跳过答题和末尾问答写回 | `retriever.retrieve_context` + 各层原始状态读取；保留 heat/N_visit 算法副作用 |
| provenance | add 后原子 sidecar 保存 page 精确键→全部 source turn ids；LoCoMo speaker map 共存 | 检索返回原 page dict 后精确反查；旧/损坏 state fail-fast |
| clean-retry | 删除单 conversation 物理目录，sidecar 同删 | `clean_memoryos_conversation_state` |

## B1-B11 当前结论

- **B1 来源与接口 ✅（PyPI canonical；ChromaDB=reproduction variant）**：只用产品版 `add_memory` 和拆出的纯 retrieval，不用
  benchmark 专用 eval 副本作算法运行源，也不调用一体化 `get_response` 代答题。
  `eval/` 只提供 LoCoMo native prompt/超参史料。产品版与 eval 的关键数值分叉已在
  M1 §1-§2 逐项列出，未假装两者等价。当前 Phase 1 canonical 继续用已接入且更易审计的
  `memoryos-pypi`。Fable 审计与架构师抽锚确认 `memoryos-chromadb` 同时改变检索关键词、
  top-k/heat、合并、持久化与异常语义，裁为 `reproduction_variant:memoryos-chromadb`，
  不因名字含 ChromaDB 就假定“只换向量库”；未来接入须重开 B3/B4/B5/B6/B8/B11。
- **B2 注入粒度 ✅ pair/session**：算法 add 单元仍是 QA page；LongMemEval 由 runner
  pair 投递，LoCoMo 因 speaker 名不是 user/assistant role，由 session 投递后在 adapter
  内按官方姿势配 page。消费批次不等于 provenance 粒度。
- **B3 隔离 ✅ 物理**：每 conversation 独立 backend/storage 目录；worker 不共享
  实例；clean 只删目标目录并保留 sibling。真实并行 smoke 归 B11。
- **B4 formatted_memory ✅ 全层+时间+身份**：短/中期 page 与 user/assistant
  knowledge 全部纳入；LoCoMo 在出口按持久 speaker map 恢复真人姓名，非 LoCoMo 保持
  User/Assistant；时间随 page 输出。共享图片表示固定为
  `[Sharing image that shows: {caption}]`，不读 `metadata.query`。
- **B5 provenance ✅ turn + RetrievalEvidence v1**：page 原文键使用规范 JSON 精确匹配，
  不做 embedding/模糊文本反查；重复 page 合并全部公开 turn ids。sidecar schema、原子替换、
  旧状态 fail-fast 与 clean 路径均有测试；M0 已逐题写 valid(turn)，identity 未注入时 pending，
  stable ranking 在逐 method rank 审计前保持 pending。
- **B6 flush ✅ no-op**：retrieve 直接覆盖尚在 STM 的内容及已迁移层，无需额外
  conversation flush。
- **B7 效率插桩 ✅（待 B11 产物复证）**：产品 LLM wrapper 接入框架 collector；
  answer LLM 属框架 reader。真实三类 observation 是否齐全在每格 smoke 开箱验货。
- **B8/B8+ 副作用与韧性 ✅（带声明缺口）**：保留检索 heat/N_visit 更新，禁止的只是
  `get_response` 末尾把 eval 问答写回。三路 future 吞异常的官方降级由 adapter 包装
  实际任务方法审计，metadata 写 `degraded_retrieval*`；合法空命中不误标。LLM 有
  timeout/retry/clean-retry；首次 embedding 模型下载缺显式 offline/timeout 仍是声明缺口。
- **B9 模型/超参口径 ✅（product-default MiniLM；零重建）**：paper、eval、pypi
  默认三岔已留档，不把其中一套冒充另一套。unified 主轨必须使用 vendored 产品实现的 pinned
  product-default embedding。现行 PyPI 签名默认与当前 profile 同为
  SentenceTransformer all-MiniLM-L6-v2/384、外部 L2 normalize + FAISS IP，build 字节不变，
  无需重建；裸名/限定名等价仍须以本地模型 revision/hash 进 identity。
- **B10 双轨 🟡 readout-native 身份 M0 待落**：LoCoMo 官方 system/user prompt 由 AST parity 锁逐字
  核对，answer=`gpt-4o-mini`, temperature=0.7, max_tokens=2000。官方无 LLM judge，
  bundle `judge_profile=None` 时回落框架默认 judge。paper build 超参只登记资产，当前
  config-track 尚不消费 build override；这是与 LightMem/Mem0 共用的框架级缺口。新 manifest
  必须显式 `native_scope=readout_only`、`judge_source=framework_fallback`，不再只靠 None 推断。
- **B11 smoke+冻结 🟡**：离线代码门已过；还缺五格真实 predict、产物开箱、免费
  evaluator、付费 judge（如适用）与并行/operation-level 既定门。用户未确认预算、规模、
  run_id 前不得执行。全部通过后才写 `memoryos-frozen-v1.md`。

## 特殊情况与不可回退项

1. eval 专用副本→pypi 通用产品引擎是公平性决策，不得为了复现单一榜单把运行源切回；
   ChromaDB 已证明是算法 variant，不得作为同 identity 的 storage backend。
2. LoCoMo speaker 身份只在出口恢复；给 ingest 文本加 speaker 前缀会改变抽取/embedding，
   与官方姿势冲突。
3. native 目前明确是 **readout-native**，不是 paper-build-native；manifest/报告必须带
   该限制，等待三 method 共用的 build-profile 框架卡。
4. M2 主提交 `e2fff4b`，registry 测试替身返工 `bfe69f1`；两者均已过主树全量门。
