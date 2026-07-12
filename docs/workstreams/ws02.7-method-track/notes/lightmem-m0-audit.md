# LightMem M0.1 接口审查（架构师一手，2026-07-12）

> 按 `docs/reference/method-integration-checklist.md` B1-B11 逐项核。
> 证据全部一手 `文件:行号`。缺项写"待抽取/待验"，不编造。这是第一个
> method 的审查范本。

## 一手核实矩阵（本 method 参与的 benchmark）

`third_party/methods/LightMem/experiments/` 只有 **locomo + longmemeval**
两个官方实验目录 → **native 轨 = {locomo, longmemeval}**；其余三 benchmark
（beam/membench/halumem）LightMem 无官方配置 → **只有 unified 轨**。

## B1 来源锁与接口选择
- vendored `third_party/methods/LightMem/`；官方 commit **来源待溯**（快照
  无独立 .git 需确认）；适配器锁定的官方文件见 `lightmem_adapter.py:270-273`
  （add_locomo/search_locomo/prompts/run_lightmem_gpt）。
- 接口：`LightMemory.add_memory()` ingest + `.retrieve()` 检索（产品接口，
  非 eval 专用入口）。

## B2 注入粒度
- `consume_granularity` 实例级、registry 按 benchmark profile 设、默认
  `"turn"`（`lightmem_adapter.py:303,315,355`）。适配器 benchmark 无关。
- **HaluMem memory_point**：LightMem 抽取是内部 topic-segmentation，能否按
  HaluMem 语义暴露 per-session memory points = **待验**（halumem 无 native
  轨，unified 轨下按 turn 注入即可，不阻塞）。

## B3 隔离方式 = **物理**（已实锤）
- 每 conversation 独立 Qdrant collection + 独立 on-disk 路径
  （`lightmem_adapter.py:388-390`：`qdrant/{collection_name}` +
  `{collection_name}_summary`），`storage_root` 当前 run 独占，
  `clean_lightmem_conversation_state` 物理清理。
- 未来并行安全：物理隔离天然进程/路径隔离，利于并行。

## B4 formatted_memory（含时间戳）= 达标
- 注入侧带 `time_stamp`（`lightmem_adapter.py:1145,1152,1206`；
  `_turn_timestamp` 取 turn.turn_time→session.session_time，`:1410-1419`）。
- 检索侧保留时间（`:681` `original_session_time or event.timestamp`），
  折入 formatted_memory（`:773-779`）。前提 dataset 有时间戳（五家满足）。

## B5 provenance = **none**（已实锤）
- `provenance_granularity = "none"`（`lightmem_adapter.py:304`）。
- **推论：recall / longmemeval-retrieval-rank / *-recall 类指标对 LightMem
  全 N/A**（能力边界，非 bug）。今天新建的 rank/recall evaluator 在
  LightMem 上不出数，要等有 provenance 的 method 才点亮。

## B6 flush/finalize = **必须**（已实锤）
- `update="offline"`（`lightmem_adapter.py:461`）；`force_segment/
  force_extract` 只在 last batch（`:493-494,579-580`）；locomo 额外
  `end_conversation → _run_locomo_offline_update`（`:556-565,1000-1008`，
  **检索耦合**：读回向量库合并更新）。**不 flush 检索到空记忆**。框架
  end_conversation 钩子已接。

## B7 效率插桩 = **api_usage 已做**（范本）
- `_BufferedMemoryManagerUsage` 捕获 memory manager LLM usage，api_usage
  优先 tokenizer 兜底（`lightmem_adapter.py:78-90`；`extract_api_token_usage/
  resolve_token_usage` 导入 `:55-60`）。
- 原生返回：LightMem `add_memory` 返回 add_input_prompt/add_output_prompt/
  api_call_nums（`experiments/longmemeval/run_lightmem_gpt.py` INIT_RESULT）
  → 作交叉参照留档。
- 约束：ShortMemBufferManager 硬编码 max_tokens=512，适配器只允许显式声明
  512（`:109,178`）。

## B8 检索副作用 / clean-retry
- 检索本身无写副作用（embedding retrieve 只读）；offline_update 是构建期
  显式步骤非检索期。clean-retry = 物理隔离目录级重建。**待补**：失败态
  半构建目录的清理契约（M0 实现时确认）。

## B9 模型口径
- 内部构建 LLM：`lightmem.toml llm_model="gpt-4o-mini"`（第三模型角色）。
- embedding：locomo native = huggingface all-MiniLM-L6-v2 / 384 维
  （`experiments/locomo/add_locomo.py:194-198`）= **与框架 unified embedding
  相同** → LightMem×locomo 两轨 embedding 一致、记忆可复用。longmemeval
  native embedding **待抽取确认**（run_lightmem_gpt.py 的 text_embedder）。

## B10 双配置轨（native 一手出处）

| benchmark | native answer prompt | native judge | native embedding | retrieve |
|---|---|---|---|---|
| locomo | `experiments/locomo/prompts.py:148 ANSWER_PROMPT`（另有 :232 StructMem 变体，**用哪个待定**——StructMem 是 LightMem 主打，需核 search_locomo 实际调用点） | ACCURACY_PROMPT（CORRECT/WRONG，跳过 cat5，`experiments/locomo/llm_judge.py:22-46,107`；7 处文本偏差已录 judge-config-audit §3） | all-MiniLM/384 | limit=60（lightmem.toml，与论文 total-limit 一致） |
| longmemeval | system"You are a helpful assistant"+user"Question time:{date} and question:{q}\nPlease answer based on memories:{join}"（`experiments/longmemeval/run_lightmem_gpt.py:182-187`） | get_anscheck_prompt 官方逐字（`:8-28`）；参数 max_tokens=2000/temp=0/top_p=0.8（LLMModel `:51-80`）；abstention gate `'abs' in id`（`:190`） | 待抽取 | limit=20（`:181`） |

**注意**：locomo answer 用 ANSWER_PROMPT 还是 ANSWER_PROMPT_StructMem，必须
核 `search_locomo.py` 实际调用点（原则 #2 死代码判例：读签名≠读调用）——
留给实现时一手定，架构师验收核。

## B11 结论
- **unified 轨**：五 benchmark 都能跑（适配器 benchmark 无关）。
- **native 轨**：locomo + longmemeval，配置一手出处如上（两处待抽取项标注）。
- 阻塞项：无。可进入实现（config-track 机制 + LightMem 两 native profile）。
