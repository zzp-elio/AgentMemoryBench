# Actor 卡：MemoryOS × LoCoMo current-main 差量预检

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**本卡只审 MemoryOS × LoCoMo，不调用真实 API、不修改生产代码、不重扫
整个 LoCoMo。actor 可自行组织 subagent，但不得扩大文件/API/数据范围；主 actor 对最终证据负责。

## 0. 目标与唯一判词

用 current main 的 canonical LoCoMo → event stream → `memoryos-pypi.add_memory()` →
product retrieve/readout 全链，裁清角色扮演、空 placeholder、session 边界、time、caption、
speaker identity 与 retrieval metric 资格。

note 最后只能写一个：

```text
READY_FOR_B11
READY_FOR_B11_WITH_NA(<指标及原因>)
NEEDS_CODE(<最小、可测试的缺口>)
```

这不是付费 smoke 授权，也不得更新 frozen/B1-B11 状态。

## 1. 隔离与必读

- 建议 worktree：`/Users/wz/Desktop/mb-actor-memoryos-locomo`
- 建议 branch：`actor/memoryos-locomo-preflight`
- 记录基线 hash 与 `git status --short`；不暂存用户未跟踪资产。

依次读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/{README.md,memoryos/README.md}`
4. `docs/reference/actor-handbook.md`
5. `docs/survey/异常情况/locomo.md`、`docs/survey/{datasets,workflows}/locomo.md`
6. `docs/workstreams/ws02.6-first-smoke-hardening/notes/{locomo-source-lock.json,locomo-frozen-v1.md}`
7. `docs/reference/integration/memoryos.md` 与本卡点名源码

worktree 缺 gitignored `data/`/`models/` 时可建只读软链并披露；不得联网下载或读 `.env`。

## 2. 复用事实，禁止重复造轮子

- LoCoMo 是两个 named human speakers，不是天然 user/assistant；140/272 session 为 odd；
- turn 无独立 source time，所属 session date/time 是唯一合法 typed fallback；
- 图片由 canonical `ImageRef` 保留；有效 caption 用共享 wrapper，locator/query 不入正文；
- date-only key、malformed/empty/duplicate private evidence 由 benchmark/private evaluator 层处理；
- canonical gold evidence group 与 id 已冻结，method 不得解析或修补 private evidence。

只轻量核 source lock 未漂移。除非出现推翻稳定账的新反证，否则不重算全量数字。

## 3. 必须亲读的一手链

- `third_party/methods/MemoryOS-main/eval/main_loco_parse.py::process_conversation()` 与 answer builder
- `third_party/methods/MemoryOS-main/memoryos-pypi/{memoryos,retriever,short_term,mid_term,long_term}.py`
- `src/memory_benchmark/benchmark_adapters/locomo.py`
- `src/memory_benchmark/runners/event_stream.py`
- `src/memory_benchmark/methods/registry.py::_memoryos_consume_granularity()` 与 MemoryOS registration
- `src/memory_benchmark/methods/memoryos_adapter.py` 的 ingest/session converter、timestamp、
  sidecar、`_retrieve_native()`、`_retrieved_items()`、`_build_retrieval_evidence()`、speaker builder
- `src/memory_benchmark/methods/image_text.py`、`configs/methods/memoryos.toml`
- MemoryOS/LoCoMo registered、adapter、Recall/judge/prompt tests

## 4. 角色映射与 session 强反例

用 production canonical adapter + event stream + fake backend 记录 exact `add_memory()` 调用；
临时脚本不提交，note 要写探针构造和承重 stdout。至少覆盖：

1. A→B 正常交替；
2. B 开头（orphan assistant）；
3. A 结尾（dangling user）；
4. A→A、B→B 连续同 speaker；
5. 前 session A dangling，后一 session B 开头；
6. odd session 后接正常 session；
7. text-only、text+caption、caption-only、多图、空 caption；
8. 两 conversation 相同正文，验证 sidecar/physical state 不串。

锁死裁决：

- `speaker_a → user_input`、`speaker_b → agent_response`；ingest content 不拼 speaker name；
- 缺一侧只用 `""` placeholder，每个真实 turn 恰一次；
- **禁止跨 session 配对**。官方脚本的 `processed[-1]` 若会跨 session 回填，只记录为 upstream
  边界缺陷/框架安全扩展，不把它当 parity 目标；
- 每页 timestamp 必须属于该页所在 session，不能继承上一/下一 session；
- caption 字节符合共享 helper，URL/query/private evidence 不可达 method；
- output/native prompt 必须从 sidecar 恢复真实 speaker 名，但 unified ingest 不能因此改字节。

若 current converter 的跨 session 反例成立，判 `NEEDS_CODE`，不要用“官方也这样”放行。

## 5. retrieve/readout 与 metric 资格

制作逐层矩阵：STM、MTM `retrieved_pages`、user knowledge、assistant knowledge。每层列：

- 是否进入 `formatted_memory`；
- 是否 query-ranked、顺序是否稳定；
- 是否进入 `RetrievalResult.items`；
- 是否有当前 memory content 的 exact `source_turn_ids`（仅“参与生成”不算）；
- LoCoMo gold group 能否诚实消费；零 hit 如何表示。

不得因 sidecar 能映射 `retrieved_pages` 就把全层 readout 一律宣称 `valid/turn`。分别裁：

- LoCoMo Recall@k；
- Precision/F1@k（gold 不穷尽时应 N/A）；
- NDCG/stable ranking；
- answer-only metrics 与 LoCoMo judge/F1。

若 metric 只能测“中期 page 子检索”而不是产品完整 readout，必须明确 metric 名义和 artifact
边界；现有 evaluator 若表达不了，就判 N/A/NEEDS_CODE，不得静默缩小定义。

## 6. identity、成本与 smoke 候选

核 current TOML、adapter/source/consume granularity/retrieval evidence/track identity/resume；确认
native 仍只是 LoCoMo readout-native，judge 是 framework fallback。给出一个 W1 与一个 W2 的
最小 B11 候选（rounds=3、questions=1 是既有预算裁决），覆盖真实 odd/session/caption 形状但
不按 gold 筛选。只列调用结构，不把 page 数换算为 API 次数。

## 7. 唯一交付与自检

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/memoryos/notes/
  memoryos-locomo-current-main-preflight.md
```

note 必含 source identity、官方/产品/framework 映射表、8 类探针、逐层 readout/metric 矩阵、
测试盲点、最小补丁蓝图（若有）与唯一判词。不得改 README/survey/integration/src/tests/configs/
third_party/data/outputs/policy/handbook。

只运行：

```bash
uv run pytest -q tests/test_documentation_standards.py
git diff --check
```

仅显式 add 该 note，本地 commit 建议 `docs(memoryos): preflight locomo current main`；不 push、
不 amend、不跑全量/compileall/真实 API。按 actor-handbook §4 回报后停止。
