# M2 MemoryOS adapter 施工记录

> 日期：2026-07-15。范围：speaker 出口映射、共享图片文本、turn provenance、
> 检索降级审计、LoCoMo readout-native bundle。零真实 API，未修改 third-party。

## 1. R1 speaker 内化

**结论：ingest 继续向 MemoryOS 的 `user_input/agent_response` 槽写裸文本；真实
speaker 只在 LoCoMo 检索出口恢复。speaker map 与 provenance 共用 sidecar 持久化，
resume 缺失即 fail-fast。**

| 环节 | 落法与锚 |
|---|---|
| 官方喂法 | speaker_a 开 page、speaker_b 回填；文本不带 speaker 前缀（`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:159-200`） |
| adapter 配对 | 内部 page 转换保留裸 `user_input/agent_response`，并另外携带 source turn ids（`src/memory_benchmark/methods/memoryos_adapter.py:1247-1325`） |
| speaker 持久化 | sidecar schema 同时存 `speaker_map` 与 `pages`；冲突/损坏/旧 state 缺失均 fail-fast（`memoryos_adapter.py:1409-1570`） |
| formatted memory | STM/page 用真实 speaker；profile/knowledge 严格执行官方三正则（`memoryos_adapter.py:1623-1715`; 官方 `main_loco_parse.py:88-113`） |
| 非 LoCoMo | 无 speaker map 时保留现有 `User/Assistant` 排版；测试锁住双形态（`tests/test_memoryos_adapter.py`） |

## 2. R7 共享图片文本

新增 `turn_text_with_images`：turn 文本与每张有 caption 的图片按
`[Sharing image that shows: {caption}]` 空格拼接；空 caption 跳过，纯图 turn 可只含
photo tag，`metadata.query` 从不读取（`src/memory_benchmark/methods/image_text.py:1-20`）。
MemoryOS 的 bridge/session/pair ingest 均走该 helper，并从 TurnEvent 的
`turn_images` 恢复 ImageRef（`memoryos_adapter.py:763-791,1247-1325`）。

**已声明偏差：**MemoryOS 官方 eval 用 `(image description: {caption})`
（`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:177-181`）；本框架按 R7
采用 method-neutral 的 sharing 格式。后续 mem0/lightmem 解冻改造不在本卡。

## 3. R4 turn provenance

**结论：page 原文可无损反查，不触发停工门。** pypi 中期检索返回原 page dict，
`user_input/agent_response` 未改写（`third_party/methods/MemoryOS-main/memoryos-pypi/mid_term.py:333-357`）。
adapter 以这两个字段的规范 JSON 作为精确键，不使用 embedding/模糊文本匹配：

- add 成功后记录 `page key -> 全部 source_turn_ids`，重复文本合并全部公开 id；sidecar
  用同目录临时文件 + `os.replace` 原子写（`memoryos_adapter.py:1470-1546`）。
- retrieve 只对 pypi 实际返回的 page 生成 `RetrievedItem`；page_id 优先作 item_id，
  缺 page_id 才用 page key 哈希；精确键缺失即 fail-fast，禁止 rank 伪造
  （`memoryos_adapter.py:941-975`）。
- class 与 registry 都声明 `provenance_granularity="turn"`
  （`memoryos_adapter.py:457`; `methods/registry.py:855-859`）。
- clean-retry 原有整 conversation 目录删除会连同 sidecar 一起删除，无新增残留面
  （`memoryos_adapter.py` 的 `clean_memoryos_conversation_state`）。

## 4. R5 降级审计

pypi 在三条 retrieval future 的聚合点吞异常并把该路改为空列表
（`third_party/methods/MemoryOS-main/memoryos-pypi/retriever.py:102-129`）。adapter 在
调用窗口临时包装三条实际任务方法：记录异常 stage 后原样重抛，让官方聚合行为不变；
返回 metadata 增加 `degraded_retrieval`、`degraded_retrieval_count`、
`degraded_retrieval_stages`（`memoryos_adapter.py:1030-1081,874-891`）。合法空命中
不标降级，只有捕获到异常才标记。

## 5. R6 readout-native bundle

LoCoMo 官方 system/user answer prompt 已逐字资产化，包含原 typo 与角色扮演文本；
运行时从 backend 四层原始结构填充，不从合并后的 formatted_memory 反向解析
（`src/memory_benchmark/methods/memoryos_native_prompts.py:11-114`；
`memoryos_adapter.py:977-1028`）。AST parity 测试现场读取官方
`main_loco_parse.py:83-142` 并逐字比较。

| 轴 | 本卡口径 |
|---|---|
| native 格 | 仅 `memoryos × locomo`；其余四格 single-track collapse（`methods/config_track.py:77-101`） |
| answer | gpt-4o-mini, temperature=0.7, max_tokens=2000, top_p=None（官方调用点 `main_loco_parse.py:139-157`） |
| judge | 官方只有本地 token-set F1，无 LLM judge；bundle 写 `judge_profile=None`，evaluate 回落框架默认 judge（`config_track.py:77-89`; `cli/commands.py:213-226`） |
| benchmark identity | registry 显式传 `context.benchmark_name`，不做数据形态启发式（`methods/registry.py:543-564`） |

### 5.1 native build 限制

按任务卡 §4.6 裁决，本框架当前 `config_track=native` 是 **readout-native**；build
仍统一使用产品默认。paper 超参已作为资产逐参记录在
`MEMORYOS_NATIVE_LOCOMO_HYPERPARAMETERS`，包括 MTM 容量语义与三个 filter 阈值的
DISPUTED 注释（`memoryos_native_prompts.py:46-66`）；bundle 的
`hyperparam_ref=memoryos.paper.locomo.disputed-build-profile-v1` 仅声明资产。
真正消费 build override 的框架级机制归 R0 前置包，与 LightMem/Mem0 同框，不在本卡。

## 6. 验收与偏离

- 定向测试：`uv run pytest -q tests/test_image_text.py tests/test_memoryos_native_prompts.py tests/test_memoryos_adapter.py tests/test_config_track.py tests/test_main_cli.py`
- compileall：`uv run python -m compileall -q src/memory_benchmark tests`
- 测试结果：`146 passed in 14.55s`；compileall exit 0。
- 额外文档标准探测：本批相关 docstring 检查通过，但整文件命令因独立 worktree
  缺主树未追踪的 `docs/archive/logs/README.md` 得到 `1 failed, 150 passed`；该文件
  不在本卡允许清单，按 playbook #18 未拷贝、未补造，且不计入本批完成门。
- plan 偏离：无。两次停工均由任务卡 §4.5/§4.6 裁定解除；未实现 native build
  profile 是已裁定的框架级声明缺口，不是本卡漏项。
- 真实 API：未调用。
- third-party：零 diff。

## 施工报告

- worktree：`/Users/wz/Desktop/mb-actor-m2mos`
- branch：`actor/m2-memoryos-adapter`
- commit：本地提交见本分支 `git log -1`（本 note 与代码同一提交）。
