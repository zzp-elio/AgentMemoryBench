# Mem0 五格输入与 readout 保真 R1 实现记录

> actor：Claude Sonnet 5（Claude Code CLI，本会话系统提示自报模型，未做跨模型切换）。
> 隔离 worktree：`/Users/wz/Desktop/mb-actor-mem0-input-r1`，分支
> `actor/mem0-input-readout-r1`，base HEAD=`35c4322`（docs(mem0): distinguish official
> surfaces and retrieval windows）。任务卡：`mem0-input-readout-r1.md`。裁决全文：
> `mem0-joint-ruling.md`。

## 0. 范围回顾

联合裁决定位五个 Mem0 输入/readout 保真缺口，本卡逐一关闭，不新增任何 placeholder，不改
Mem0 V3 extraction/update/dedup/vector search 算法，不改 benchmark canonical 数据、
granularity、metric、TOML、embedding 或 HaluMem operation runner：

1. LoCoMo 显式 `speaker_a`/`speaker_b` → `user`/`assistant` 映射（不按首现）；
2. LoCoMo caption 改用共享 `[Sharing image that shows: {caption}]` wrapper；
3. role-native 四格（LongMemEval/MemBench/BEAM/HaluMem）content 去重复 role 前缀；
4. MemBench/HaluMem 的 native sanity readout 身份收紧为 `generic`；
5. HaluMem update probe 忠实透传 `RetrievalQuery.top_k`。

## 1. 五格真实 backend call shape

以下 shape 均取自 `tests/test_mem0_adapter.py` 新增强反例测试的实际断言（`FakeMemoryBackend`
记录的真实调用参数，非手写猜测）：

| benchmark | 投递粒度 | 实际 `Memory.add()` message 数/role | content 渲染 |
|---|---|---|---|
| LoCoMo | `turn`（legacy `add()` 与 v3 `ingest(TurnEvent)` 均逐 turn 单条 add） | 每 turn 1 条；role 由 `speaker_a→user`/`speaker_b→assistant` 显式映射决定，与说话顺序无关 | `{time_prefix}{speaker_name}: {rendered_text}`（具名 speaker 前缀保留，因为双 speaker 不是通用人称） |
| LongMemEval | `session`（adapter 内按位置两两切块，官方 `CHUNK_SIZE=2`） | 每 chunk 1-2 条；role 直接取 `normalized_role`，含连续同 role（如 `[user, user]`）与奇数尾（1 条） | `{time_prefix}{rendered_text}`（**不再**前置 `user:`/`assistant:`） |
| MemBench | `turn`（FirstAgent 两 canonical child 各自 singleton add；ThirdAgent singleton user add） | 每 turn 1 条 | 同上，marker=True 时原文 place/time 原样、无 header 重复 |
| BEAM | `pair`（正常 user→assistant 一批；dangling tail 单独一条） | 正常 pair 2 条；dangling tail 1 条，不补 assistant | 同上 role-native 渲染 |
| HaluMem | `session`（整 session 一次 add） | 每 session 1 条 add，内含全部 turn message | 同上 role-native 渲染；update probe 检索 `top_k=10`（忠实于 `query.top_k`），QA 检索仍 `top_k=self.config.top_k`（smoke=20） |

## 2. v2→v3 版本重建理由

五格输入修复改变了进入 Mem0 extraction/embedding 的 **build bytes**（LoCoMo role 映射、
role-native 去重复前缀、caption wrapper），因此任何用旧 `conversation-qa-v2` adapter 写入的
memory state 与新代码不再字节等价。`MEM0_ADAPTER_VERSION` 升为 `conversation-qa-v3`，
`Mem0Config.to_manifest()["adapter_version"]` 同步更新；`tests/test_mem0_adapter.py::
test_mem0_adapter_version_bumped_to_v3_with_v2_legacy_mention` 显式断言新值且
`!= "conversation-qa-v2"`/`!= "conversation-qa-v1"`。resume 走 `runners/prediction.py`
既有的整份 manifest `==` 精确比较（未改动、不在允许清单内），单键不等即会拒绝 resume——
这就是"旧 v2 resume mismatch"强反例的机制来源，不需要另建 resume 专用测试基础设施。

## 3. LoCoMo 4/10 vs 6/10 role 强反例

架构师在联合裁决中已对 source-locked `locomo10.json` 做过全量复算：10 个 conversation 中
只有 **4/10** 由 `speaker_a` 首发，其余 **6/10** 先由 `speaker_b` 发言。current-main 的
`_build_speaker_roles()`（按 speaker 首次出现顺序分配 user/assistant）会在这 6 个
conversation 把官方角色整体反转。

`tests/test_mem0_adapter.py::test_mem0_locomo_explicit_speaker_mapping_locks_speaker_b_first_via_legacy_add`
用同一对 `speaker_a="Caroline"/speaker_b="Melanie"` 构造两个 conversation（分别
`Caroline`/`Melanie` 首发），断言两者中 `Caroline` 恒为 `user`、`Melanie` 恒为 `assistant`。
`test_mem0_locomo_v3_event_speaker_mapping_matches_legacy_add_byte_for_byte` 用
`speaker_b` 首发的同一 shape 走 v3 `ingest(TurnEvent)` 路径，并与 legacy `add()` 路径的
message 字节逐条比较相等。

**验证方法**：为确认全部 12 条新增强反例测试（不止 LoCoMo 相关的 4 条）是真实反例而非凑数，
临时 `git stash push --keep-index -- src/memory_benchmark/methods/mem0_adapter.py`（只回退
生产代码，保留新测试）后单独跑这批新测试，再 `git stash pop` 恢复。回退期间实测
`12 failed, 1 passed, 45 deselected`，`FAILED` 摘要逐条列出（原样摘录）：

```
FAILED tests/test_mem0_adapter.py::test_mem0_adapter_version_bumped_to_v3_with_v2_legacy_mention
FAILED tests/test_mem0_adapter.py::test_mem0_locomo_explicit_speaker_mapping_locks_speaker_b_first_via_legacy_add
FAILED tests/test_mem0_adapter.py::test_mem0_locomo_v3_event_speaker_mapping_matches_legacy_add_byte_for_byte
FAILED tests/test_mem0_adapter.py::test_mem0_locomo_speaker_mapping_fails_fast_on_missing_blank_or_equal_metadata
FAILED tests/test_mem0_adapter.py::test_mem0_locomo_speaker_mapping_fails_fast_on_undeclared_third_speaker
FAILED tests/test_mem0_adapter.py::test_mem0_locomo_singleton_turns_have_exactly_one_message_and_no_placeholder
FAILED tests/test_mem0_adapter.py::test_mem0_locomo_caption_wrapper_variants_render_exactly_once
FAILED tests/test_mem0_adapter.py::test_mem0_longmemeval_consecutive_same_role_session_has_no_role_text_duplication
FAILED tests/test_mem0_adapter.py::test_mem0_membench_first_agent_children_and_third_agent_singleton_render_original_text_once
FAILED tests/test_mem0_adapter.py::test_mem0_beam_dangling_tail_produces_singleton_add_with_no_synthetic_partner
FAILED tests/test_mem0_adapter.py::test_mem0_halumem_update_probe_uses_query_top_k_while_qa_keeps_configured_top_k
FAILED tests/test_mem0_adapter.py::test_mem0_reader_prompt_kind_explicit_non_native_identity_stays_generic
```

唯一按设计通过的是 `test_mem0_reader_prompt_kind_none_identity_still_uses_legacy_heuristics`
（它验证的正是未改变的旧兼容分支，理应两侧都通过）。以下两条 assertion diff 原样摘录自该次
回退运行的 stdout，直接命中本卡改动点：

```
# test_mem0_beam_dangling_tail_produces_singleton_add_with_no_synthetic_partner
AssertionError: assert '[Session tim...rst user turn' == '[Session tim...rst user turn'
- [Session time: 2024-04-02T00:00:00] first user turn
+ [Session time: 2024-04-02T00:00:00] user: first user turn

# test_mem0_halumem_update_probe_uses_query_top_k_while_qa_keeps_configured_top_k
assert backend.search_calls[0]["top_k"] == 10
assert 20 == 10
```

`git stash pop` 恢复生产代码后，同一批测试与全文件其余测试一并转绿（见 §8）。

## 4. 两代官方 LoCoMo surface 边界（未采纳论文双库路径的依据）

- **当前独立 `mem0ai/memory-benchmarks` LoCoMo runner**（架构师核验 HEAD=`4b61c5d3`）：单
  namespace、`speaker_a=user/speaker_b=assistant` 显式固定映射、`CHUNK_SIZE=1` 逐条
  add。本卡实现与此对齐。
- **`mem0ai/mem0/evaluation/src/memzero` 论文 harness**（架构师核验 HEAD=`9383e9a2`）：双
  `user_id` namespace、正反 role 双写（同一对话整段重复写两次、角色对调）、双路检索融合，
  并绑定 `MemoryClient(version="v2")` 与"只从 user role 抽取"的 custom instruction——这是
  另一条存储/检索算法流，不是当前单 namespace 路径缺一个配置开关。
- 架构师已核验 vendored `mem0/configs/prompts.py` 与最新 upstream 同为 SHA-256
  `10bc8a34…a5c`；最新版 V3 extraction prompt 已明确从两侧 role 抽取，且专门说明
  assistant role 可承载具名真实 speaker 的个人事实——旧双库"只抽 user 才安全"的补偿理由
  不再成立。

本卡因此**未**创建第二 namespace、复制 turn、合并双路检索或改 answer builder；未来若要
复现论文 harness，需另建显式 implementation variant，不塞进当前 adapter 或
`author_locomo` TOML section。

## 5. caption bytes

`_turn_to_message()` 改用 `methods/image_text.py::turn_text_with_images(turn)` 渲染正文+
caption，不再手写 `content_parts` 裸拼。实测字节（`tests/test_mem0_adapter.py::
test_mem0_locomo_caption_wrapper_variants_render_exactly_once`，`session_time=None` 排除
时间前缀干扰）：

| 场景 | 实际 message content |
|---|---|
| 正文+单 caption | `Caroline: check this out [Sharing image that shows: a blue vase on a table]` |
| caption-only（content=""） | `Caroline: [Sharing image that shows: a sleeping cat]` |
| 多 caption | `Caroline: two photos [Sharing image that shows: a red bike] [Sharing image that shows: a green door]`（wrapper 出现 2 次，对应 2 张图） |
| 空白/None caption | `Caroline: no usable caption here`（两张图 caption 分别为 `"   "`/`None`，均不产生 wrapper） |

同批测试另断言 image 的 `path`（含 `?query=vase&token=secret`）与 `metadata["query"]` 不
出现在最终 content 中——`turn_text_with_images()` 只读 `image.caption`，query/URL/path
不会进入正文，无需额外过滤逻辑。

## 6. 无 placeholder 证明

以下真实调用序列证明本卡未在任何场景补写合成消息：

- **LoCoMo 单独 user/assistant turn**（`test_mem0_locomo_singleton_turns_have_exactly_one_message_and_no_placeholder`）：
  各自只产生 1 条 `add()` 调用、1 条 message。
- **MemBench FirstAgent 两 child + ThirdAgent singleton**
  （`test_mem0_membench_first_agent_children_and_third_agent_singleton_render_original_text_once`）：
  3 次独立 `provider.ingest(event)` 产生 3 次 `add()`，每次恰 1 条 message，原文 place/time
  逐字节保留，无 `[Turn time`/`[Session time` header 重复。
- **BEAM dangling tail**（`test_mem0_beam_dangling_tail_produces_singleton_add_with_no_synthetic_partner`）：
  `user, assistant, user` 三 turn session 经真实 `GranularityAggregator("pair")` 聚合，产出
  1 个正常 pair（2 条 message）+ 1 个 dangling pair（`second=None`，1 条 message，role=user，
  metadata `turn_ids=["s1:t2"]`），未合成 assistant 搭档。
- **LongMemEval 连续同 role**（`test_mem0_longmemeval_consecutive_same_role_session_has_no_role_text_duplication`）：
  `[user, user, assistant]` 三 turn 按官方位置切块产生 `[2, 1]` 两次 add，第一次 2 条
  message 均 role=user、content 各自独立（`message 0`/`message 1`），无 placeholder 补位。

## 7. HaluMem update 实际 top-k

`operation_level.py:389`（不在允许清单内，只读确认）硬编码
`RetrievalQuery(query_text=..., isolation_key=..., question_time=None, top_k=10,
purpose="memory_update_probe")`。`test_mem0_halumem_update_probe_uses_query_top_k_while_qa_keeps_configured_top_k`
直接构造该 shape 驱动真实 `Mem0._retrieve_native()`（`FakeMemoryBackend`），实测：

```
backend.search_calls[0]["top_k"] == 10   # purpose="memory_update_probe"
backend.search_calls[1]["top_k"] == 20   # purpose="qa"，即便 query.top_k 故意传 5 也被忽略
update_result.metadata == {..., "top_k": 10, "configured_top_k": 20, "top_k_source": "query_top_k", ...}
qa_result.metadata == {..., "top_k": 20, "configured_top_k": 20, "top_k_source": "config_top_k", ...}
```

QA 请求刻意传入 `top_k=5`（不同于 `Mem0Config.smoke().top_k=20`），证明 `qa` purpose 是真正
忽略 `query.top_k` 而不是恰好与 config 数值相同重合。

## 8. 定向测试尾行

允许清单内 7 个文件的定向命令（与任务卡 §5 完全一致）：

```
uv run pytest -q \
  tests/test_mem0_adapter.py \
  tests/test_mem0_native_prompts.py \
  tests/test_locomo_registered_prediction.py \
  tests/test_longmemeval_registered_prediction.py \
  tests/test_membench_registered_prediction.py \
  tests/test_beam_registered_prediction.py \
  tests/test_halumem_registered_prediction.py
```

尾行原文：

```
75 passed in 10.98s
```

`tests/test_mem0_adapter.py` 单独尾行：`58 passed in 3.69s`（46 条既有测试全绿 + 12 条新增
强反例）。

## 9. 偏差披露

1. **隔离 worktree 缺 `.env`（环境偏差，非代码偏差）**：新建 worktree 不含 gitignored
   `.env`；`test_beam_registered_prediction.py`/`test_halumem_registered_prediction.py`
   中 6 个用例在构造 `LLM judge efficiency_model_inventory` 时需要读取
   `OpenAISettings.model`（仅取模型名字符串用于 `ModelDescriptor` 观测声明，调用链上无真实
   HTTP 请求），因此需要环境中存在某个 `OPENAI_KEY`/`OPENAI_API_KEY` 字符串。按硬规则
   "不得读 `.env`"，本次**未**读取或软链主仓 `.env`，而是在 pytest 命令前用 shell 内联
   `OPENAI_KEY=sk-test-offline-dummy-key`（虚构占位值，不写入任何文件、不持久化）。已用
   主仓（含真实 `.env`）单独复跑 `test_halumem_fake_registered_chain_runs_three_evaluators`
   核实：同一份测试代码在有 `.env` 的环境下本就会通过，证明这 6 个失败纯属新
   worktree 缺 `.env` 的环境 artifact，与本卡生产代码改动无关。
2. **未修改 5 个 registered-prediction 测试文件**：`test_locomo/longmemeval/membench/
   beam/halumem_registered_prediction.py` 均通过 `monkeypatch.setattr(method_registry_module,
   "Mem0", _ProbeAsMem0)`（或 HaluMem 的 method-neutral `FakeHalumemProvider`）替换真实
   `Mem0` 类，本卡改动的全部逻辑都在真实 `Mem0` 类体内，这 5 个文件因此从未真实调用到
   任何一处改动，属于纯回归门（已在 §8 验证全绿），无真实 diff 可加，按任务卡 §3
   "没有真实 diff 就不要 add" 保持未改动。
3. **`docs/reference/integration/mem0.md` 更新范围**：只更新了 §0 接口调用面表格的
   role 映射描述、HaluMem top-k 段落，并新增"R1 五格输入/readout 保真修复"小节陈述五项
   机制性事实；未触碰 B1-B11 的 ✅/🟡 状态标签或 frozen 声明——那些仍是架构师验收后的
   判断，本卡不越权代裁。
4. 未运行全量 `pytest`、`compileall`、真实 smoke 或任何网络/模型下载；未触碰
   `data/`/`third_party/benchmarks/`（只建了只读软链供既有测试读取，未复制、未修改）；
   未调用真实 API。
5. Co-Authored-By：Claude Sonnet 5（本会话系统提示明确标注 `claude-sonnet-5`，未发生
   模型/入口切换，无需标注"未核实"）。

## 10. 架构师 R1 follow-up（2026-07-20）

基线 commit：`1de6ef8`。R1 复核确认首轮
`test_mem0_adapter_version_bumped_to_v3_with_v2_legacy_mention` 只比较版本字符串，未经过
真实 resume preflight，因此首轮 §2 将其称为“旧 v2 resume mismatch 强反例”证据不足。
本节追加更正，不改写首轮历史。

- 保留原版本常量测试，但收紧 docstring，不再声称字符串不等本身证明 resume 拒绝。
- 新增 `test_mem0_v2_manifest_is_rejected_by_real_resume_preflight`：current manifest 的
  `method` 直接取 `Mem0Config.smoke().to_manifest()`，锁定真实
  `adapter_version=conversation-qa-v3`；existing legacy manifest 从 current 深拷贝，只把
  `method.adapter_version` 改成 `conversation-qa-v2`，schema、source fingerprint 与所有
  其他字段保持相同。
- 正向门把同一 v3 manifest 写入真实 `ExperimentPaths.manifest_path`，调用
  `runners.prediction._validate_run_manifest_state(..., resume=True)` 成功；负向门在同一路径
  写入仅 adapter version 不同的 v2 manifest，再经过同一 preflight，实测抛出
  `ConfigurationError: Resume manifest mismatch`。这证明拒绝来自真实 resume 身份门，
  不是测试手工比较或无条件失败。
- R1 零生产代码 diff；只修改 `tests/test_mem0_adapter.py` 与本 implementation note。

R1 七文件定向命令使用 shell 内联
`OPENAI_KEY=sk-test-offline-dummy-key`，未读取 `.env`、未调用真实 API；尾行原文：

```text
76 passed in 11.33s
```

R1 无停工点；未使用 subagent，未运行任务卡外测试，未 amend，未 push。
