# M1 MemoryOS 接入取证

> 日期：2026-07-14。范围：只读官方仓库、框架 adapter/registry/config/tests；
> 零真实 API。算法运行源是 `memoryos-pypi/`，`eval/` 只作为 LoCoMo native
> 复现事实源。本文不修改 `outputs/memoryos-locomo-full-20260603/`。

## 1. 官方评测面与 `eval/` / `memoryos-pypi/` 差距

**硬答案：官方仓库当前只有 LoCoMo 可复现入口；`eval/` 与产品版不是整体换算法，
而是相同 STM/MTM/LPM + 更新/检索/生成分层下的两套实现。差异足以改变数值，
但可按影响评测行为的重点清单描述，不触发“整体重写级不可清单化”停工条件。**

官方 README 只给出 `cd eval -> main_loco_parse.py -> evalution_loco.py`，且 TODO
仍把集成 benchmark suite 列为 ongoing（`third_party/methods/MemoryOS-main/README.md:443-458`）。
`main_loco_parse.py` 才是实际构建/答题入口；`evalution_loco.py` 只是读取答案后算
token-set F1（`third_party/methods/MemoryOS-main/eval/evalution_loco.py:44-70`）。

### 1.1 LoCoMo 实际调用序列

| 环节 | 一手行为 | 锚 |
|---|---|---|
| 数据转 page | 按 session 顺序遍历；speaker_a 开 page，另一 speaker 回填最近 page；图片 caption 拼入 text | `third_party/methods/MemoryOS-main/eval/main_loco_parse.py:159-200` |
| 初始化 | 每 sample 独立三份 JSON；STM=1、MTM=2000、topic threshold=0.6、retrieval queue=10 | `third_party/methods/MemoryOS-main/eval/main_loco_parse.py:230-252` |
| 注入 | 每个完整 QA page 先 `short_mem.add_qa_pair`；满则 `bulk_evict_and_update_mid_term`；随后检查 heat 并更新 LPM | `third_party/methods/MemoryOS-main/eval/main_loco_parse.py:254-259` |
| 检索 | 每题调用 `retrieve(segment=.1,page=.1,knowledge=.1)`；中期 page 按分数入 top-10 queue，另检索长期知识 | `third_party/methods/MemoryOS-main/eval/main_loco_parse.py:261-278`; `third_party/methods/MemoryOS-main/eval/retrieval_and_answer.py:13-45` |
| answer context | 短期、retrieval queue、用户画像/知识、assistant knowledge 全部拼入 system/user messages，且历史 page 带对话时间 | `third_party/methods/MemoryOS-main/eval/main_loco_parse.py:83-142` |
| answer LLM | 实际调用 `gpt-4o-mini`, temperature=0.7, max_tokens=2000 | `third_party/methods/MemoryOS-main/eval/main_loco_parse.py:139-157` |
| metric | 本地 token-set F1，按 category 求均值；没有 LLM judge 调用 | `third_party/methods/MemoryOS-main/eval/evalution_loco.py:7-36,44-67` |

### 1.2 影响评测行为的代码差距

| 维度 | `eval/` | `memoryos-pypi/` | 影响 |
|---|---|---|---|
| 编排入口 | 脚本手工组合 `ShortTermMemory/DynamicUpdate/RetrievalAndAnswer` | `Memoryos` 公开类统一组合各层 | 产品版提供通用 `add_memory/get_response`；`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:247-259`; `third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py:29-124,226-250` |
| STM 迁移 | 加入后发现满，循环弹出 | 加入前若满则先迁移，避免 deque 自动淘汰 | 边界页归属不同；`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:254-258`; `third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py:240-246` |
| 页面/链构建 | `DynamicUpdate` 串行连续性、meta、multi-summary | `Updater` 保留同流程，增加 page id/embedding 复用、连接修复与 fallback session | 存储内容和 LLM 调用次序可能不同；`third_party/methods/MemoryOS-main/eval/dynamic_update.py:118-180`; `third_party/methods/MemoryOS-main/memoryos-pypi/updater.py:100-207` |
| MTM heat | α=.8, β=.8, γ=.0001，tau=24 小时 | α=β=γ=1，tau=24 小时 | 产品版与论文 α/β/γ 对齐，eval 副本不对齐；`third_party/methods/MemoryOS-main/eval/mid_term_memory.py:16-28`; `third_party/methods/MemoryOS-main/memoryos-pypi/mid_term.py:20-36` |
| 检索 | 单线程：中期 + 单一 LTM 文件 | 三路线程并行：中期、user KB、assistant KB | 产品版新增独立 assistant LTM；单路异常被置空列表；`third_party/methods/MemoryOS-main/eval/retrieval_and_answer.py:13-45`; `third_party/methods/MemoryOS-main/memoryos-pypi/retriever.py:70-130` |
| 检索关键词 | 每题在 segment search 中调用 LLM 提取 query keywords | 明确把 query keywords 置空，只按 embedding 相似度 | eval 检索多一次外部 LLM 且打分面不同；`third_party/methods/MemoryOS-main/eval/mid_term_memory.py:185-200`; `third_party/methods/MemoryOS-main/memoryos-pypi/mid_term.py:281-330` |
| 中期 top-k | top-m 由函数默认控制，最终 page queue=10 | top-m session=5，最终 page queue 构造默认=7 | LoCoMo native 数值分叉；`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:248-252`; `third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py:35-40,117-122` |
| LPM 容量 | Python list，无容量上限 | user/assistant knowledge 均为固定 deque(100) | 产品版实现论文 FIFO 容量；`third_party/methods/MemoryOS-main/eval/long_term_memory.py:5-11`; `third_party/methods/MemoryOS-main/memoryos-pypi/long_term.py:11-19` |
| response 后写回 | eval 直接答题，不把问答写回 | `get_response` 最后会 `add_memory(query,response)` | 框架必须剥离步骤 1-7，不能调用完整 `get_response`；`third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py:252-264,346-348`; `src/memory_benchmark/methods/memoryos_adapter.py:745-767` |

机械 diff 规模也支持“同模块成熟化而非小补丁”：short-term `+35/-12`、mid-term
`+394/-271`、long-term `+173/-133`、utils `+386/-378`。复算命令：

```bash
git diff --no-index --stat \
  third_party/methods/MemoryOS-main/eval/mid_term_memory.py \
  third_party/methods/MemoryOS-main/memoryos-pypi/mid_term.py
```

## 2. 超参三岔口

**硬答案：paper、LoCoMo eval 实配、pypi 无参数构造默认明显分叉；native LoCoMo
至少 STM/MTM/page top-k/检索阈值属于 DISPUTED 候选。现 TOML 确实使用 pypi
构造签名默认，而不是 README demo 的覆盖值。**

论文 PDF 没有源码行号，以下以 `Paper-MemoryOS.pdf:p.6` 的版面行号标注；可复算脚本：

```python
import fitz
page = fitz.open("third_party/methods/MemoryOS-main/Paper-MemoryOS.pdf")[5]
for number, line in enumerate(page.get_text().splitlines(), 1):
    print(number, line)
```

| 参数 | paper | `eval/` 实配 | pypi 默认 / 当前 TOML | 失配 |
|---|---:|---:|---:|---|
| STM page capacity | 7 (`Paper-MemoryOS.pdf:p.6`, text 55-56) | 1 | 10 / 10 | 三岔；`main_loco_parse.py:247-249`; `memoryos-pypi/memoryos.py:35`; `configs/methods/memoryos.toml:9,32` |
| MTM capacity | 200（论文措辞是 maximum length of segments；`p.6`, 56-58） | 2000 | 2000 / 2000 | 论文到代码字段语义还存在“segment 长度 vs segment 数”歧义；`main_loco_parse.py:249`; `memoryos-pypi/memoryos.py:36,88-94` |
| User KB / Agent Traits capacity | 100 (`p.6`, 58-59) | 无容量上限 | 100 / 100 | eval 失配；`eval/long_term_memory.py:5-10`; `memoryos-pypi/memoryos.py:37,95-107` |
| heat threshold τ | 5 (`p.6`, 59-61) | 5 | 5 / 5 | 一致；`eval/main_loco_parse.py:22-23`; `memoryos-pypi/memoryos.py:25-40` |
| heat α/β/γ | 1/1/1 (`p.6`, 61,112) | .8/.8/.0001 | 1/1/1（代码常量） | eval 失配；`eval/mid_term_memory.py:24-28`; `memoryos-pypi/mid_term.py:20-36` |
| topic merge θ | .6 (`p.6`, 116-117) | .6 | .6 / .6 | 一致；`main_loco_parse.py:251`; `memoryos-pypi/memoryos.py:40` |
| retrieval top-m sessions | 5 (`p.6`, 112-114) | 函数默认 top-5 | 5 / 5 | 一致；`eval/mid_term_memory.py:185-198`; `memoryos-pypi/retriever.py:92-99` |
| LoCoMo retrieved page top-k | 10 (`p.6`, 114-116) | queue 10 | queue 7 / 7 | pypi 失配；`main_loco_parse.py:252`; `memoryos-pypi/memoryos.py:38` |
| segment/page/knowledge filter | 论文未给三项 | .1/.1/.1 | .1/.1/.01 / 同值 | DISPUTED；`main_loco_parse.py:272-277`; `memoryos-pypi/retriever.py:92-99`; `configs/methods/memoryos.toml:15-17` |
| embedding | 论文未点名 | all-MiniLM-L6-v2 | all-MiniLM-L6-v2 / `sentence-transformers/all-MiniLM-L6-v2` | paper 来源待溯；`eval/utils.py:17-20`; `memoryos-pypi/memoryos.py:42`; `configs/methods/memoryos.toml:8` |

README Basic Usage 显式覆盖 STM=7、heat=5、queue=7、LTM=100、embedding=bge-m3，
所以它不是“无参数开箱默认”（`third_party/methods/MemoryOS-main/README.md:272-305`）。
作者要求 paper 优先的 GitHub issue URL 未被 vendored 文档保存；本地只能锚到政策对该
结论的登记，原始 URL **来源待溯**，不能在本卡编造
（`docs/reference/dual-track-config-policy.md:88-101,156-165`）。

## 3. 注入粒度

**硬答案：官方 LoCoMo 的算法 add 单元是完整 user/assistant QA page；框架实际
`add_memory` 单元也是 pair，但 registry 为 LoCoMo 选择 `session` 投递，adapter
在 session 内按 speaker 重新配 pair。因此算法粒度一致，框架事件聚合粒度不同。**

官方先把 speaker_a turn 开成 page，再用另一 speaker 闭合；assistant 开头会生成
空 user page，连续同 speaker 的行为则依赖“回填最近 page”而非严格轮次
（`third_party/methods/MemoryOS-main/eval/main_loco_parse.py:159-200`）。框架：

| 面 | 现状 | 锚 |
|---|---|---|
| 类级默认 | `consume_granularity="pair"` | `src/memory_benchmark/methods/memoryos_adapter.py:438-448` |
| registry | LongMemEval=`pair`，其余 benchmark（含 LoCoMo）=`session` | `src/memory_benchmark/methods/registry.py:543-563` |
| pair ingest | `TurnPair -> add_memory(user, assistant, timestamp)`；dangling/orphan 空侧保留 | `src/memory_benchmark/methods/memoryos_adapter.py:634-673` |
| session ingest | session 恢复为 Conversation，按 speaker/role 配 page，再逐 page `add_memory` | `src/memory_benchmark/methods/memoryos_adapter.py:675-697,1004-1070` |

差异：官方 eval 先把整个 conversation 转 page 后统一注入；框架按 session 分批转换，
所以跨 session 不会错误把 assistant 回填到上一 session，属于边界更严格的适配差异。

## 4. 隔离与 clean

**硬答案：MemoryOS 当前是 conversation 级物理目录隔离；清理能整目录删除，检索
按 backend 选择不会跨 conversation；并行时注册面声明不共享实例，runner 为 worker
构造隔离实例。三项均有正证据，缺口是尚无显式“并发双 conversation 压测”测试。**

| 判据 | 证据 | gap / 建议动作 |
|---|---|---|
| 清得干净 | 每 conversation 独立 backend 和 `storage_root/<safe conversation_id>`，内部再建 `users/<user_id>` 与 `assistants/<assistant_id>`；clean 直接 `rmtree` 目标目录 | 现有测试 `test_clean_retry_removes_only_target_conversation_directory` 锁目标删、sibling 留；`memoryos_adapter.py:876-914,1565-1586`; `tests/test_memoryos_adapter.py:411-439` |
| 漏不出去 | retrieve 先由 question/isolation 映射到 conversation，再只读该 backend | 有双 backend 内容隔离测试，但没有“同 query 跨 namespace 检索零命中”的生产路径测试；`memoryos_adapter.py:769-784,827-849`; `tests/test_memoryos_adapter.py:400-408` |
| 并行不打架 | `supports_shared_instance_parallelism` 默认 False；workers>1 时 runner 走 isolated worker instances | 建议 M2 增双 worker 目录/结果隔离测试；`methods/registry.py:129-142,834-864`; `cli/run_prediction.py:633-645`; `runners/prediction.py:453-458` |

clean hook 已挂到 registration（`src/memory_benchmark/methods/registry.py:618-628,834-864`）。
失败发生后框架先记录 `failed_ingest`，显式 clean-retry 才执行 hook；这不是单次
`add_memory` 的事务回滚（`src/memory_benchmark/runners/prediction.py:737-788`）。

## 5. 检索副作用与 B5+ 落点

**硬答案：adapter 正确保留了检索时 `N_visit/last_visit_time/H_segment` 更新；
B5+ 可在 adapter add 侧维护规范化 page 文本到公开 turn ids 的 sidecar，再以检索
返回 page 原文反查。当前 v3 `RetrievalResult` 没有 items，provenance 仍是 none。**

产品检索只在 session/page 达阈值且有命中时更新访问统计、重建 heap 并保存
（`third_party/methods/MemoryOS-main/memoryos-pypi/mid_term.py:281-362`）。adapter
直接调用该接口，没有复制状态后回滚（`src/memory_benchmark/methods/memoryos_adapter.py:851-870`）；
测试明确只禁止 `get_response` 步骤 10 的 `add_memory`，允许 heat 变化
（`tests/test_memoryos_adapter.py:722-787`）。

B5+ 最小落点：

1. add 侧在 `conversation_to_memory_pages` / `_ingest_pair` 已同时知道公开 turn id
   与 `user_input/agent_response`（`memoryos_adapter.py:657-672,1004-1070`）；在该处
   持久化 `normalized page text -> source turn ids` sidecar。
2. 产品 page 被写入时保留 `page_id/user_input/agent_response/timestamp`，检索返回
   `page_data` 原对象（`memoryos-pypi/mid_term.py:115-147,333-357`）。可用规范化
   user+assistant 文本无损反查；重复文本必须映射到全部 source ids，不能任选一条。
3. 当前 `_retrieve_native` 只返回 `formatted_memory/prompt_messages/metadata`，没有
   `items`（`memoryos_adapter.py:818-849`），且注册面未声明 provenance
   （`memoryos_adapter.py:447-448`; `methods/registry.py:834-864`）。M2 需填
   `RetrievedItem.source_turn_ids` 并把声明改为 turn；sidecar 必须随 state 持久化，
   旧 state 缺少 sidecar 应 fail-fast，不能按 rank 伪造来源。

## 6. B8+ 外部调用韧性清单

**硬答案：唯一付费网络面是 OpenAI-compatible LLM；adapter 已给它 120 秒超时、
8 次重试和指数退避。embedding 推理本地，但首次按 Hugging Face 模型名构造时可能
联网下载，项目未设置 offline/local_files_only、timeout 或 retry，这是 B8+ 明确 gap。**

| 调用点 | 用途 | timeout / retry | 失败 state 语义 |
|---|---|---|---|
| `backend.client.chat.completions.create` | STM→MTM 连续性/meta/multi-summary，以及 heat 触发的 profile/knowledge 抽取 | TOML 120 秒、8 retries、5 秒起步×2、60 秒封顶；wrapper 实际传 `timeout`，捕获 timeout/connection 后重试 | 最终异常抛给 runner；conversation 被标 failed_ingest，clean-retry 删除整物理目录；`configs/methods/memoryos.toml:20-24,43-47`; `memoryos_adapter.py:916-976`; `registry.py:618-628` |
| framework answer LLM | unified reader 回答问题，不是 MemoryOS 算法内部 | 共享配置默认 60 秒/8 retries，并实际传给 OpenAI SDK client；MemoryOS 主线 retrieve 不调官方 `get_response` | answer 失败不再写 method；官方步骤 10 已跳过；`config/settings.py:17-23,147-200`; `readers/answer.py:198-249`; `cli/run_prediction.py:580-603`; `memoryos_adapter.py:600-628,745-767` |
| `SentenceTransformer(model_name)` / `BGEM3FlagModel(model_name)` | 本地 embedding 推理 | 模型已缓存时零网络；首次 cache miss 可能访问 Hugging Face。无 `local_files_only`、显式 timeout/retry | 失败语义按路径分叉：retrieve 的三条 future 把异常降级为空列表；ingest 的页面 embedding 处理先记录错误，后续插入重算仍可能抛出并进入 failed_ingest clean-retry；降级未写入 manifest；`memoryos-pypi/utils.py:142-181,185-211`; `memoryos-pypi/retriever.py:109-130`; `memoryos-pypi/updater.py:38-60,172-196` |
| JSON/FAISS | short/mid/long 本地持久化与进程内向量检索 | 零网络，不适用 | 每 conversation 目录隔离；`memoryos-pypi/memoryos.py:70-108`; `memoryos-pypi/mid_term.py:301-306` |

额外事实：vendored 原始 `OpenAIClient` 自己不传 timeout，且捕获所有异常后返回错误
字符串（`third_party/methods/MemoryOS-main/memoryos-pypi/utils.py:37-64`）；生产 adapter
替换了 `chat_completion`，因此实际运行以 wrapper 的抛错/重试语义为准
（`src/memory_benchmark/methods/memoryos_adapter.py:916-976`）。

**B8+ gap：**embedding 首次下载缺显式韧性与可审计的“模型已本地锁定”前置检查；
retrieve 的 embedding 异常会静默降级为空结果且无 manifest 标记；单次 `add_memory`
不是事务，失败隔离依赖 runner 的 clean-retry，不是即时回滚。

## 7. native 注册面与模型口径预研

**硬答案：MemoryOS native 注册面只有 LoCoMo；官方 LoCoMo answer 是
gpt-4o-mini / temperature 0.7 / max_tokens 2000，评测是本地 F1、没有 judge
prompt/model。adapter 已产 `prompt_messages` 且 formatted_memory 带对话时间，
但当前没有 MemoryOS native config bundle，M2 注册前还需把 eval 的 answer prompt
逐字资产化。**

| 项 | 事实 | 锚 |
|---|---|---|
| native benchmark | README 只发布 LoCoMo reproduce；其他集成 benchmark 尚在 TODO | `third_party/methods/MemoryOS-main/README.md:443-458` |
| answer prompt | system 定义 speaker 角色与极简回答；user 分 `<CONTEXT>/<MEMORY>/<CHARACTER TRAITS>`，日期/时长有格式约束 | `third_party/methods/MemoryOS-main/eval/main_loco_parse.py:83-142` |
| answer 模型/参数 | gpt-4o-mini, temperature=.7, max_tokens=2000 | `third_party/methods/MemoryOS-main/eval/main_loco_parse.py:139-157` |
| judge | 无 LLM judge；`evalution_loco.py` 做 token-set F1 | `third_party/methods/MemoryOS-main/eval/evalution_loco.py:7-36,44-67` |
| adapter native messages | retrieve 构造并返回 `prompt_messages` | `src/memory_benchmark/methods/memoryos_adapter.py:784-815,818-849` |
| 当前 bundle | `_NATIVE_CONFIG_TRACK_BUNDLES` 无 memoryos 项，因此 native 现状 fail-fast | `src/memory_benchmark/methods/config_track.py:74-83,86-107` |
| 时间口径 | STM、中期 page、user/assistant knowledge 均把存储 timestamp 拼进 formatted_memory | `src/memory_benchmark/methods/memoryos_adapter.py:1244-1299` |

模型口径补充：论文 LoCoMo 表报告 GPT-4o-mini 与 Qwen2.5-3B 两组结果
（`Paper-MemoryOS.pdf:p.7`, text 21-97,98-168）；仓库复现实际调用点固定
gpt-4o-mini。按当前项目全局模型政策，native 第一阶段是否保留 gpt-4o-mini 无模型
冲突；真正分叉是 prompt 与超参。非 LoCoMo 四格依据 single-track collapse 规则不应
臆造 native（`docs/reference/dual-track-config-policy.md:171-180`）。

## 施工报告

- worktree：`/Users/wz/Desktop/mb-actor-m1mos`
- branch：`actor/m1-memoryos-evidence`
- 改动：仅本 note。
- 测试：纯文档卡，按任务卡未运行 pytest。
- 偏离：PDF 无稳定源码行号，论文事实改用 PDF 页码 + PyMuPDF 可复算 text line；
  作者 GitHub issue 原始 URL 未在本地资产中，明确记“来源待溯”。
- 停工点：无。
