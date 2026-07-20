# Actor 卡：Mem0 五格输入与 readout 保真 R1

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你是施工 actor，不是架构师；按本卡已经裁定的边界实现，遇到停工条件
交回。不要把卡内“actor”理解为让你再启动另一个会话；你可自行组织 subagent，但主会话必须
亲自复核最终 diff、测试与报告，且不得扩大 scope。

## 0. 这张卡解决什么

Mem0 默认 V3 extraction 确实区分 `user`/`assistant` role，但 core **不要求 pair 完整、role
交替、user 起始或偶数条数**；current-main LoCoMo 官方 harness 自己就是
`CHUNK_SIZE=1`。因此本卡**不增加任何 placeholder**。它只关闭联合审计确认的五个输入/readout
保真缺口：

1. LoCoMo 不能按“首个出现 speaker=user”猜角色；source-locked 10 个 conversation 只有
   4 个由 `speaker_a` 首发，必须显式 `speaker_a=user / speaker_b=assistant`；
2. LoCoMo caption 当前裸拼，必须使用共享
   `[Sharing image that shows: {caption}]` wrapper；
3. LongMemEval/MemBench/BEAM/HaluMem 已有结构化 message role，正文又加
   `user:`/`assistant:` 会让 Mem0 prompt 看到重复 role；
4. MemBench 因全部问题都有 question time，被 native sanity readout 静默误标为
   `longmemeval`；
5. HaluMem 官方 Mem0 wrapper 的 update probe 原生请求 `top_k=10`，当前 adapter 却忽略
   `RetrievalQuery.top_k`、固定用 TOML 20。本卡只让 `purpose="memory_update_probe"` 忠实
   使用请求值；不改变普通 QA/其他 benchmark 的 product retrieval depth。

本卡不改 Mem0 V3 extraction/update/dedup/vector search 算法，不改 benchmark canonical 数据、
granularity、metric、TOML、embedding 或 HaluMem operation runner。权威裁决：
`docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/notes/
mem0-joint-ruling.md`。

## 1. 隔离环境与必读顺序

建议 worktree：`/Users/wz/Desktop/mb-actor-mem0-input-r1`
建议 branch：`actor/mem0-input-readout-r1`

先记录 `git rev-parse --short HEAD`，然后只按顺序读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/README.md`
4. `docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/notes/
   mem0-joint-ruling.md`
5. 六份 preflight 只定点读联合裁决链接的相应小节，不重扫 benchmark census
6. `docs/reference/actor-handbook.md`
7. 本卡允许清单内生产代码与测试

若 worktree 缺 gitignored `data/`/`third_party/benchmarks/`，可建只读软链供既有测试读取；禁止
复制、修改或暂存数据。不得读 `.env`、调用真实 API、下载模型或写 outputs。

## 2. 锁死语义

### 2.1 绝不新增 placeholder 或改 ingest 粒度

- LoCoMo、MemBench 保持 `turn`；LongMemEval、HaluMem 保持 `session`；BEAM 保持 `pair`。
- MemBench FirstAgent 两 canonical child 仍是两次 singleton add；ThirdAgent 每条 observation
  仍是 singleton user add。
- BEAM dangling user、LongMemEval singleton/assistant-first/same-role 都按生产聚合器给出的真实
  fragment 提交；缺另一侧时不补空消息，更不补 “I get it!” 等伪内容。
- 一次 pair add 与两次 singleton add 会改变 extraction batch/last messages，禁止把它们视为
  等价重构。

### 2.2 LoCoMo role 映射

1. `benchmark_name == "locomo"` 时，从公开 conversation metadata 读取非空、互异的
   `speaker_a`/`speaker_b`，固定映射为 `user`/`assistant`。legacy `add(Conversation)` 与 v3
   event ingest 必须共用同一 helper/规则。
2. 缺字段、空白、两者相同、真实 turn 出现第三个未声明 speaker，均
   `ConfigurationError` fail-fast；不得回落到 first-seen、字母排序或默认 user。
3. LoCoMo message `role` 用上述映射；content 仍必须含真实 speaker name 前缀
   `"{speaker}: {text}"`，因为双 speaker 不是通用 user/assistant 人称。
4. 非 LoCoMo 的有效 `normalized_role` 直接作为 role；未知 role 的既有兼容边界不因本卡放宽。

这里必须把两代官方入口分开，不能只看见“都在 mem0ai 仓库”就混为一种 native：

- 当前独立 `mem0ai/memory-benchmarks` LoCoMo runner（架构师核验 HEAD=`4b61c5d3`）是
  **单 namespace + A/B 固定 role + singleton add**；这是本卡主产品路径的参照。
- `mem0ai/mem0/evaluation/src/memzero` 论文 harness（核验 HEAD=`9383e9a2`）是
  **双 user_id + 正反 role 双写 + 双路检索融合**，并绑定 `version="v2"` 和“只从 user
  messages 抽取”的 custom instruction。它靠 role 翻转让两个库分别看到两位 speaker，
  是另一条实现流，不是缺一个配置开关。

因此本卡绝不创建第二 namespace、复制同一 turn、合并双路检索或改 answer builder。若未来要
复现论文 harness，必须另建显式 implementation variant；不得把它塞进 `author_locomo` TOML
section 或当前 adapter 小分支里。最新版 V3 prompt 已明确抽取两侧消息，并特别覆盖
assistant role 承载具名真实 speaker 的场景；这正是当前单 namespace 路径不需要反向双写的
直接依据。架构师已核验 vendored 与最新 upstream `mem0/configs/prompts.py` 的 SHA-256 完全
一致（`10bc8a34…a5c`）；actor 不需要再次联网或猜版本。

### 2.3 content 只渲染一次

1. 先用 `methods/image_text.py::turn_text_with_images(turn)` 生成原文+结构化 caption；不得在
   benchmark adapter 提前写 wrapper，也不得读图片 query/URL/path/redownload metadata。
2. 若 turn 有当前 adapter 支持的有效 `normalized_role in {user,assistant}`，content 是
   `effective_time_prefix + rendered_text`，**不再**加 `turn.speaker:`。这样 Mem0
   `parse_messages()` 最终只产生一次 `user:`/`assistant:`。
3. 若没有有效 normalized role（LoCoMo named speaker），content 是
   `effective_time_prefix + "{speaker}: " + rendered_text`。
4. 现有时间契约零变化：`turn_time → session_time → None` 恰好一个 header；MemBench 原文
   marker 严格为 `True` 时不再加 header，原 place/time 文本原样保留；无时间保持 None；
   question time、兄弟 turn、wall clock 均不可回填。
5. caption-only/multi-caption/空 caption 都按共享 helper；正文+caption 字节形如
   `text [Sharing image that shows: caption]`，不裸拼。caption URL/query 不进 content。
6. 生成空 content 继续 fail-fast；不得为使测试通过制造 placeholder 文本。

### 2.4 native sanity readout 身份

1. 显式 `benchmark_name in {"locomo","longmemeval","beam"}` 仍使用对应 current-main
   官方 native prompt builder，作为 artifact sanity/未来 author section 的原料；unified 主表
   builder 不变。
2. **只要显式 benchmark identity 存在但不在上述三家**（当前是 MemBench、HaluMem），
   `_reader_prompt_kind()` 必须返回 `"generic"`，不能再由 question time/category 猜成别家。
3. 只有 `benchmark_name is None` 的 legacy 兼容调用才允许保留现有 source/category/time
   heuristics；测试必须锁住显式 identity 优先。

### 2.5 HaluMem update 检索窗口

1. `_retrieve_native()` 只在 `query.purpose == "memory_update_probe"` 时把
   `query.top_k` 传给 Mem0 `Memory.search()`；当前 runner 请求值为 10，与官方
   `eval_memzero.py` 一致。
2. `purpose="qa"` 与所有非 operation-level retrieval 继续使用 `self.config.top_k`；不要借本卡
   让标准五 benchmark QA 从 20 暗降到通用 runner 的 10。
3. RetrievalResult metadata 必须区分 configured value 与本次 actual value，并标明 limit source；
   不得继续把固定 20 写成实际值。
4. 不在 adapter 或 operation runner 二次截 items；Mem0 原生 search 已经能执行请求。不得把此
   规则泛化到没有 top-k 的 method，也不得拆分 opaque formatted text。

### 2.6 identity

本卡改变进入 extraction/embedding 的 build bytes。`MEM0_ADAPTER_VERSION` 从
`conversation-qa-v2` 升为 `conversation-qa-v3`，manifest/resume 测试同步收紧；旧 v2 memory
state 不得被声明兼容。不要顺手重命名 config track/TOML section。

## 3. 允许修改文件

```text
src/memory_benchmark/methods/mem0_adapter.py
tests/test_mem0_adapter.py
tests/test_mem0_native_prompts.py
tests/test_locomo_registered_prediction.py
tests/test_longmemeval_registered_prediction.py
tests/test_membench_registered_prediction.py
tests/test_beam_registered_prediction.py
tests/test_halumem_registered_prediction.py
docs/reference/integration/mem0.md
docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/notes/
  mem0-input-readout-r1-implementation.md
```

允许清单中的文件无需为凑数修改；没有真实 diff 就不要 add。禁止改 registry、event_stream、
benchmark adapter、image helper、operation runner、provider protocol、evaluator、TOML、
third_party、父/支线 README、六份 preflight、联合裁决、data/models/outputs。

若正确实现必须改允许清单外生产文件，立即停工；不要用 monkeypatch/fake 绕过真实调用链。

## 4. 必测强反例

### 4.1 core/LoCoMo

- 用两个最小 Conversation 锁住：`speaker_a` 首发与 `speaker_b` 首发都得到同一显式映射；后者
  必须会在 current main 失败。
- v3 event metadata 同样锁住 `speaker_b` 首发；legacy/v3 对同一 turn 的 message bytes 一致。
- 缺 speaker_a、空 speaker_b、二者相同、第三 speaker 全部 fail-fast。
- 单独 user singleton、单独 assistant singleton 都只含一条 message；无 placeholder。
- 正文+caption、caption-only、多个、空白 caption；query/URL/path 不泄漏；wrapper 恰一次。

### 4.2 role-native 四格

- LongMemEval assistant-first、连续同 role、singleton/odd tail：实际 backend call 按既有 chunk
  形状，无 placeholder、无 `assistant: assistant:` 或 `user: user:`。
- MemBench FirstAgent 两 child 仍两次 add；ThirdAgent singleton user；原 place/time bytes 原样、
  header 不重复；100k 缺时不造时间。
- BEAM 正常 pair 一批，dangling tail singleton；不跨 session、不补 assistant；10M 错位原文不
  被 adapter 猜修。
- HaluMem 整 session 一批，结构化 roles 原样；session report/lineage/长期 state 不受 content
  renderer 之外的变化。
- HaluMem update `RetrievalQuery(top_k=10)` 实际传给 fake Mem0 backend 的 search=10，返回顺序
  与条目数原样；HaluMem QA 仍用 configured 20。metadata 精确区分 configured/actual/source。

### 4.3 prompt/identity

- 显式 `benchmark_name="membench"` 且 question_time 非空仍为 generic；HaluMem 同样 generic；
  LoCoMo/LME/BEAM 不退化。
- `benchmark_name=None` 的既有 legacy heuristic 保持原兼容结果。
- manifest/adapter metadata 精确为 v3；至少一条旧 v2 resume mismatch 强反例，不能通过删除
  identity 断言放宽兼容。
- 所有有效 message 的 role/content 键存在；不得修改 Mem0 prompt、TOML 或 fake backend 来
  “适配”错误输出。

## 5. 唯一定向自检

```bash
uv run pytest -q \
  tests/test_mem0_adapter.py \
  tests/test_mem0_native_prompts.py \
  tests/test_locomo_registered_prediction.py \
  tests/test_longmemeval_registered_prediction.py \
  tests/test_membench_registered_prediction.py \
  tests/test_beam_registered_prediction.py \
  tests/test_halumem_registered_prediction.py
```

只跑这一次直接相关集合；不得跑全量 pytest、compileall、真实 smoke、网络或模型下载。测试若因
gitignored data 缺失，可按 §1 建只读软链并披露；不能删掉真实 registered 测试或把断言改成只
检查“不报错”。

## 6. 停工条件

- current source 推翻“Mem0 singleton 合法”或出现 core 对 pair/交替的硬校验；
- v3 event 没有公开 speaker_a/b metadata，且只能通过读取 private/gold 才能映射；
- shared image helper 无法表达已裁 wrapper；
- renderer 修复改变 provenance sidecar、namespace、ingest granularity、time fallback 或
  session report，15 分钟内不能定位；
- 必须改 operation runner、TOML、benchmark canonical 数据、third_party 算法或真实数据；
- 定向测试暴露允许清单外真实生产缺陷。

停工时只完成安全的 note，写最小复现、源码锚、已完成部分和建议裁决；不要删强反例、扩大
scope 或用 placeholder 让测试绿。

## 7. 提交与完成报告

- `git diff --check`；add 前后各看 `git status --short`；只显式 add 路径，禁 `-A`/`.`。
- 本地线性单 commit，不 amend、不 push；建议 message：
  `fix(mem0): preserve benchmark message semantics`。
- implementation note 必须列出：五格真实 backend call shape、v2→v3 重建理由、LoCoMo
  4/10 vs 6/10 role 强反例、两代官方 LoCoMo surface 边界、caption bytes、无 placeholder
  证明、HaluMem update actual top-k、定向测试尾行、任何偏差。
- Co-Authored-By 只写可核实真实模型；发生模型切换且无法核实时不猜。
- 按 actor-handbook §4 回报：commit hash、测试尾行原文、实际改动文件、偏差/停工点、subagent
  分工与模型/入口切换。到此停止，等待架构师 full diff 与强验收。
