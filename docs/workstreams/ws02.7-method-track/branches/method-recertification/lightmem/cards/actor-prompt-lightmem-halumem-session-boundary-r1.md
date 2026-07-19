# Actor 卡：LightMem × HaluMem session flush 完整性 R1

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你负责修复 LightMem 官方 `force_segment` 路径的两个确定性状态错误，
用零 API 强反例证明 HaluMem 每个 session 的抽取输入完整且不跨 session。actor 可自行组织
subagent，但不得扩大允许范围；若实质使用，最终报告须披露分工，主 actor 仍对全部交付负责。

## 0. 这张卡解决什么

HaluMem 的 operation-level 评测按 session 交错执行：

```text
ingest 当前 session
→ 冻结当前 session extraction report
→ update probes
→ 当前 session QA
→ 下一 session
```

LightMem adapter 已为 HaluMem 使用一次
`add_memory(messages, force_segment=True, force_extract=True)`，并只旁听这次调用实际插入的
memory。但 2026-07-19 架构师沿真实 vendored sensory buffer 复核后发现两处确定性错误：

1. `sensory_memory.py` 的 forced tail 已全部加入 `segments` 后，却执行
   `start_idx = len(boundaries)`；这里需要的是已输出 message 的清理位置，不是 boundary 个数。
   非空 boundary 时会留下已输出过的旧 message，下一 session 可重复、串入，或因 user/assistant
   奇偶结构被破坏而 `IndexError`。
2. `lightmem.py` 先接收 `add_messages()` 已自动切出的 `all_segments`，随后在
   `force_segment=True` 时用 forced tail **覆盖**它，而非合并；跨过 sensory threshold 的
   session 会丢掉本次调用较早已切出的 segment，只把尾部送给 STM/extraction。

因此旧 note 的 `READY_FOR_HALUMEM_B11_COMMAND` 已被架构师改判为
`BLOCKED_SESSION_FLUSH_INTEGRITY`。本卡不是调参，不改 segmentation threshold、prompt、
messages_use、online-soft、metric 或数据；只修复“已输出内容应恰好向下游一次，并从 buffer
恰好移除一次”的 bookkeeping 契约。

**不以做出指标为目标强改 method。**如果 LightMem 现有公开 force 语义在上述最小 bookkeeping
修复后仍不能给出“当前 session 完整且仅当前 session”的候选，立即停工；架构师将把
LightMem × HaluMem extraction（及依赖它的 memory-type）诚实判为 N/A，而不是发明 reset、
改分段算法或另造 session extraction pipeline。

## 1. 隔离环境与开工

从最新 `main` 创建独立 worktree；若路径或分支已存在，不删除、不 reset，停工报告：

```bash
git -C /Users/wz/Desktop/memoryBenchmark worktree add \
  /Users/wz/Desktop/mb-actor-lightmem-halumem-flush-r1 \
  -b actor/lightmem-halumem-session-boundary-r1 main
cd /Users/wz/Desktop/mb-actor-lightmem-halumem-flush-r1
git rev-parse --short HEAD
git status --short
```

新 worktree 缺 gitignored `data/`、`models/` 时，可建指向主工作区同名资产的只读软链；不得
复制、修改或暂存。不得读取/打印 `.env`，不得调用真实 API、下载模型或创建 `outputs/`。
测试若只需配置占位，使用 `OPENAI_KEY=dummy BASE_URL=http://127.0.0.1:9`；任何意外联网立即
停工。

## 2. 最少必读顺序

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/README.md`
4. `docs/reference/actor-handbook.md`
5. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
   lightmem-halumem-current-v7-preflight.md` 的 §8-§10
6. 本卡点名的生产文件及相邻测试：
   - `third_party/methods/LightMem/src/lightmem/factory/memory_buffer/sensory_memory.py`
   - `third_party/methods/LightMem/src/lightmem/memory/lightmem.py`
   - `third_party/methods/LightMem/src/lightmem/factory/memory_buffer/short_term_memory.py`
     （只读，除非停工交回；用于确认 `force_extract` 清空语义）
   - `src/memory_benchmark/methods/lightmem_adapter.py` 的 source identity、HaluMem ingest/capture/
     end_session
   - `src/memory_benchmark/runners/operation_level.py` 的 session ingest/report/update/QA 顺序
   - `tests/test_lightmem_adapter.py` 的官方 preprocessing 与 HaluMem session-report tests

不要重扫 HaluMem 全量结构，不重做 frozen-v1 benchmark 审计。

## 3. 架构师已复现的失败（必须先在 worktree 重现）

### 3.1 forced tail 清理位置错误

用真实 `SenMemBufferManager`、确定性 tokenizer/segmenter/embedder 构造两个 pair；第一 session
产生非空 boundary 并 force flush。current main 的结果为：

```text
session1_segments= [[('user', 'u1'), ('assistant', 'a1')],
                    [('user', 'u2'), ('assistant', 'a2')]]
after_session1_buffer= [('assistant', 'a1'), ('user', 'u2'), ('assistant', 'a2')]
token_count= 1
session2_error= IndexError list index out of range
```

修复后第一 session 输出列表必须保持不变，但 `buffer=[]`、`big_buffer=[]`、`token_count=0`；
第二 session 必须只输出第二 session 内容且不报错。

### 3.2 automatic segments 被 forced tail 覆盖

用最小 fake sensory manager 让 `add_messages()` 返回 `AUTO` segment、forced cut 返回 `TAIL`
segment，并让 fake short-memory 记录收到的列表。current main 实际为：

```text
shortmem_received= [[{'role': 'user', 'content': 'TAIL'}]]
```

修复后必须按原顺序收到 `AUTO`、`TAIL` 两段，各恰一次；不得倒序、去重、合并文本或重复。

## 4. 已裁实现边界

仅做下列最小语义修复：

1. `SenMemBufferManager.cut_with_segmenter(..., force_segment=True)` 在把 remaining tail 加入
   `segments` 后，清除**本次已经全部输出的 current buffer**；不得用 boundary count 充当
   message index。非 force 分支仍只移除已切出的 prefix，保留未切 tail，行为不变。
2. `LightMemory.add_memory()` 必须保留 `add_messages()` 在本次调用已生成的 automatic segments，
   再按顺序追加 forced tail；不得覆盖 automatic segments。
3. `build_lightmem_source_identity()` 必须至少纳入
   `src/lightmem/factory/memory_buffer/sensory_memory.py`。`lightmem.py` 已在身份中；修复后
   `method_source_sha256` 会自然变化并阻止旧状态 resume。
4. **不 bump `LIGHTMEM_ADAPTER_VERSION`，仍为 `conversation-qa-v7`**：本批没有修改 adapter
   输入/输出/config 协议；运行实现差异由 method source identity 如实承载。不得为省事绕过
   source identity，也不得把旧 source hash 加入兼容白名单。
5. 不清空 embedding retriever/LTM，不重建 backend；session 边界只清理 sensory/short-term
   已经输出并抽取的暂存态，已插入长期记忆必须保留，供 update/QA 读取累计在线状态。

如果正确修复需要改变 segmentation boundary、similarity threshold、compression、extraction
prompt/batching、memory 内容或 online-soft insert/update 语义，立即停工交回架构师，不自行调算法。

## 5. 必须新增的强反例

全部零 API，至少覆盖：

1. **非空 boundary + force**：输出 segment bytes/order 与 current 预期相同，sensory
   `buffer/big_buffer/token_count` 全清。
2. **连续两个 session**：第二 session 不含第一 session message/source id，不崩溃、不重复；
   第一 session 已插入的 LTM 仍存在，证明清的是暂存态而非长期记忆。
3. **threshold crossing + force**：同一次 `add_memory` 内 automatic prefix 与 forced tail 都进入
   short-memory/extraction，原顺序、全覆盖、各一次。这个测试必须会在 current main 因覆盖而失败。
4. **HaluMem production adapter 链**：至少两个 session；第一 session 至少两个 pair 且强制形成
   非空 boundary，第二 session 再 ingest。通过真实 vendored sensory/short-memory 路径和 fake
   extraction/insert 边界证明每个 `SessionMemoryReport` 只包含本 session 调用产生的候选；不能
   再用直接“每 add 伪造一条 memory”的 `SessionCaptureFakeLightMemoryBackend` 代替承重证明。
5. **no-boundary force**：既有 clean flush 行为不变。
6. **non-force carryover**：只删已发 prefix、保留 tail 的官方增量语义不变。
7. **identity**：source files 列表含 sensory 文件；改动前身份不能与改动后伪装成同一 source。
8. **版本/manifest**：adapter version 仍为 v7，source identity 参与既有 strict manifest/resume；
   不新增 HaluMem 特判兼容键。

现有 fake session-report test 可保留作 observer/call-boundary 单测，但不得把它当作第 4 条的替代。

## 6. 前四格差量保护

本修复可能触达所有使用官方 `LightMemory.add_memory()` 的 benchmark。用零 API 定向测试证明：

- 非 final `force_segment=False` 的 segmentation/carryover 语义不变；
- LoCoMo/LongMemEval/MemBench/BEAM 已有 role、pair、caption、missing-time、lineage、readout、
  RetrievalEvidence 测试无退化；
- 不声称旧真实 artifacts 使用了新 source identity。回卡 note 只给“是否需要重跑前四格”的
  reachability 输入，由架构师裁决；actor 不自行改 frozen/REAL_SMOKE_PASSED 状态。

## 7. 允许文件

只允许修改：

```text
third_party/methods/LightMem/src/lightmem/factory/memory_buffer/sensory_memory.py
third_party/methods/LightMem/src/lightmem/memory/lightmem.py
src/memory_benchmark/methods/lightmem_adapter.py
tests/test_lightmem_adapter.py
tests/test_lightmem_registered_prediction.py
tests/test_method_registry.py
tests/test_halumem_registered_prediction.py
docs/reference/integration/lightmem.md
docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
  lightmem-halumem-session-boundary-r1-implementation.md
```

允许清单中的文件若无需修改就不要制造空白 diff。不得改 benchmark adapter、operation runner、
evaluator/metric、TOML、prompt、short-term manager、其他 method、README/status、data/models/outputs。
若测试契约确需修改清单外文件，停工报告，不自行扩 scope。

所有新增 Python 类/函数须有中文 docstring；第三方既有文件若新增 helper，也须有中文 docstring。

## 8. 定向自检与提交

只运行一次直接相关门：

```bash
OPENAI_KEY=dummy BASE_URL=http://127.0.0.1:9 \
uv run pytest -q \
  tests/test_lightmem_adapter.py \
  tests/test_lightmem_registered_prediction.py \
  tests/test_method_registry.py \
  tests/test_halumem_registered_prediction.py \
  tests/test_documentation_standards.py
git diff --check
```

不得跑全量 pytest、compileall、真实 API、模型下载或写 outputs。只显式 add 实际改动路径，禁止
`git add -A`/`.`；commit 前查看 `git status --short`。建议 commit：

```text
fix(lightmem): isolate forced session flushes
```

按 `actor-handbook.md` §4 回报：commit hash、测试尾行原文、实际文件、两处失败修复后的强反例
结果、前四格 reachability 判断、偏差/停工点、subagent 使用与真实模型/入口；不要 push。到此
停止，等待架构师 full diff 与强验收。

## 9. 停工条件

- 修复会改变 boundary/threshold/compression/prompt/memory 内容，而非 bookkeeping；
- 无法同时保证 automatic prefix 与 forced tail 各一次、顺序不变；
- session flush 后仍有 sensory/short-term residual，或清掉已插入 LTM；
- HaluMem report 仍能含前一 session 新抽取候选；
- 达成 current-session-only 需要另造 reset/session API、改 segmentation/extraction 算法或清空 LTM；
- source identity 无法覆盖本次改动的 runtime 文件；
- 需要真实 API/下载、修改数据或越过允许清单；
- 15 分钟内无法解释的生产链/测试矛盾。
