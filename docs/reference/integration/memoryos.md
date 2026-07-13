# MemoryOS 接入实例（B1-B11 逐项）

> 判据模板：`../method-integration-checklist.md` §B；勾选总表：`../integration-status.md`。
> 状态：**adapter 已落地（ws02.5 迁移版），B1-B11 未正式过**——"已知事实"为 2026-07-13
> 架构师代码取证预填，非验收结论。

- adapter：`src/memory_benchmark/methods/memoryos_adapter.py`（1,595 行）
- 算法源：**memoryos-pypi 通用产品引擎**（ws02.5 迁移背景：原包装 `eval/` 目录的
  LoCoMo 专用副本有"主场优势"，已弃用；`third_party/methods/MemoryOS-main` 仍留作
  native 配置取证来源）
- native 格：**locomo**（唯一格；配置来源=**论文超参**——作者 GitHub issue 明确指引，
  policy §4 case 2 判例）

## 0. 接口调用面（黑盒拆解，预填）

| 框架钩子 | adapter 行为 | 落到 MemoryOS 官方接口 |
|---|---|---|
| `ingest(TurnPair)` | consume_granularity="pair"（adapter:447）；orphan/dangling 空侧留空串注入不丢 | `backend.add_memory(user_input, agent_response, timestamp)`（adapter:668） |
| `ingest(SessionBatch)` | LoCoMo 用（speaker 人名 role 使 pair 锚定失效）：`conversation_to_memory_pages` 按 speaker 配对成 QA pair 再逐对投递（adapter:676-697） | 同上逐 page `add_memory`（:692） |
| `end_conversation` | **no-op**（adapter:741-744） | — |
| `retrieve(query)` | **复刻官方 `get_response` 步骤 1-7**（memoryos.py:259-302），**跳过步骤 8-9 答题与步骤 10 的 add_memory 写副作用**（adapter:748-757 docstring） | `retriever.retrieve_context(user_id, config 阈值)`（:862）+ `short_term_memory.get_all()` + `user_long_term_memory.get_raw_user_profile(user_id)`（:1264） |
| clean-retry | `clean_memoryos_conversation_state`（adapter:1565）+ registry `_clean_memoryos_failed_ingest_state`（registry.py:827） | 文件系统删 `users/<user_id>/` 状态目录（:1535） |

## B1-B11 逐项（全部 ⬜ 待 M 阶段，下面只记已知事实/风险）

- **B1**：⬜。接口=add_memory/retrieve_context，不用 get_response 答题（公平性已按
  设计落地）；pypi 版本锁定 + license 待做。**注意**：算法源是 pypi 包不是 vendored
  目录——来源锁的形态（pip 版本号 + 哈希）与其他 method 不同，M 阶段定契约。
- **B2**：⬜。pair 为主 + LoCoMo session 级绕道（见 §0）；HaluMem memory_point：
  add_memory 无返回记忆列表的已知通路，预计 gap，待核签名。
- **B3**：⬜ **物理隔离**：per-conversation `Memoryos` 实例 + 独立 `data_storage_path`
  （adapter:441 docstring；`user_id=_safe_user_id(conversation_id)` :1392，同时作目录名）。
- **B4**：⬜。formatted_memory 组装短/中/长期 + user/assistant knowledge 全层
  （:748-757）；时间戳随 add_memory 注入，检索回带情况待核。
- **B5**：`provenance_granularity="none"`（adapter:448）→ recall/ndcg 预计 N/A。
  **B5+ 初判（2026-07-13 MemoryData 判例）：可无损改造**——检索层返回原文
  （retrieval_queue 的 user_input），adapter 存储时记 `normalized_text→source_ids`
  反查表即可。见 `ws02.7/notes/memorydata-recall-retrofit-survey.md` 策略③。
- **B6**：⬜。end_conversation=no-op 的**初判依据**：retrieve 读全部层含 short_term
  （get_all），未迁移到中长期的内容也检索得到 → 无 flush 需求。M 阶段用官方源码锚死
  这个论证（短期→中期迁移触发条件）。
- **B7**：⬜。adapter 有 stdout 抑制包装（`_suppress_stdout_if_needed`），LLM 调用
  观测路径待审。
- **B8**：⬜ **本 method 是 checklist B8 的判例主角**：heat/N_visit 是算法固有状态
  必须保留（playbook §4.5.7）；我们已跳过 get_response 步骤 10 的写副作用，但
  `retrieve_context` 本身是否改 heat 待官方源码锚。clean-retry 钩子已挂。
- **B9**：⬜。参数=pypi 官方默认（short_term_capacity=10 等，非 LoCoMo 调参）——
  与 unified 轨"repo 默认超参"政策一致。
- **B10**：⬜。native=locomo 论文超参（作者 issue 指引）；**reproduce-vs-paper 检查
  必做**（eval 目录与论文已知失配，正是 §5 规则的动因判例）；issue 链接落锚待补。
- **B11**：⬜。

## 特殊情况
1. **主场优势迁移史**：eval/ 副本→pypi 通用引擎是本项目公平性的标志性决策，勿回退。
2. native 超参来源=论文（非 eval 目录），是全矩阵唯一一例作者显式背书 paper 的格。
