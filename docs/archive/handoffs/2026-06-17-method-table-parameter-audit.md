# 2026-06-17 Method Table 参数与调用路径审计交接

## 背景

用户在准备并行成本校准 smoke 前指出：不能只看 method 仓库默认参数或“能跑”，必须对齐
论文表格对应实验设置。尤其是：

- A-Mem 应按论文 Table 1 的 LoCoMo 五类 QA 实验设置核对。
- LightMem 应按论文 Table 2 LongMemEval-S 和 Table 3 LoCoMo 的设置核对。
- adapter 必须严格遵守 method 官方算法逻辑；不懂、不确定或犹豫时必须先说明并和用户
  对齐。

本轮没有运行真实 API，也没有修改第三方核心算法。

## 已完成

1. 更新 `AGENTS.md`，新增硬规则：
   - method adapter 必须严格复刻目标 method 的官方/论文算法调用路径。
   - 论文、README、复现实验脚本和当前 adapter 不一致时，必须先记录证据并和用户对齐。
   - 不懂、犹豫或不确定的实验设置、参数含义、调用粒度和算法步骤，不能写进
     official/smoke profile。
2. 更新 `docs/method-resource-parameter-audit.md`：
   - 将 A-Mem 和 LightMem 标记为真实 smoke 前阻塞。
   - 记录 A-Mem Table 1 GPT-4o-mini 的按类别 `k`：
     - Multi Hop=40
     - Temporal=40
     - Open Domain=50
     - Single Hop=50
     - Adversarial=40
   - 记录 A-Mem 官方 robust QA 调用路径：
     `question -> generate_query_llm(question) -> retrieve_memory(keywords, k) -> category prompt -> answer LLM`。
   - 记录当前 A-Mem adapter 差异：
     直接 `find_related_memories_raw(question, k=10)`，未复刻 query keyword generation 和
     Table 8 按类别 k。
   - 记录 LightMem Table 2 / Table 3 关键配置：
     - LongMemEval-S Table 2 GPT-4o-mini：`r=0.5, th=256`、`r=0.6, th=256`、
       `r=0.7, th=512` 及对应 OP-update。
     - LoCoMo Table 3 GPT-4o-mini：`LightMem(0.7,512)`、`LightMem(0.7,768)`、
       `LightMem(0.8,768)`。
     - LoCoMo reported retrieval：combined `total-limit=60`。
   - 记录当前 LightMem adapter 差异：
     - 未显式支持 `compression_rate r` 和 `stm_threshold th` profile。
     - 当前 backend config 为 `compress_config.rate=0.6`，不等于 Table 3 的
       `0.7/0.8`。
     - LightMem 当前源码中 `ShortMemBufferManager(max_tokens=512)` 是硬编码，Table 3
       的 `th=768` 不能直接通过 adapter config 设置。
     - 当前 adapter 一次传完整 conversation 并强制 `force_segment=True,
       force_extract=True`；官方 LoCoMo / LongMemEval 脚本按 user+assistant turn pair
       多次调用 `add_memory()`，只在最后一轮强制 segment/extract。
     - 当前 adapter 使用项目自定义 reader prompt；LightMem LoCoMo reader 使用
       speaker-organized memories，LongMemEval reader 显式包含 question time。
3. 更新 `docs/current-roadmap.md`：
   - A-Mem / LightMem fake/offline smoke 不再等同于论文 Table 级参数对齐。
   - 新增 A-Mem 和 LightMem 参数/调用路径补齐任务。
   - Phase J 的资源与参数审计从完成状态改回未完成，等待 Table 级审计闭环。
4. 追加 method 写入接口粒度记录：
   - Mem0：官方接口是 `Memory.add(messages, ...)`；官方 benchmark 中 LoCoMo 按
     session chunk、LongMemEval 按 user+assistant pair 写入。当前 adapter 已展开到
     turn-level `Memory.add([message], run_id=conversation_id, ...)`，属于细粒度写入，
     但若要完全复刻 Mem0 官方 benchmark，还需单独决定是否改为 chunk/pair。
   - MemoryOS：官方/PyPI 语义是 `add_memory(user_input, agent_response, timestamp)`；
     当前 adapter 将 turn 配成 dialogue page / QA pair 后逐 page 写入，和 LoCoMo eval
     路径一致。
   - A-Mem：官方写入是 `add_note(content, time)`；当前 adapter 逐 turn 调用
     `add_note(...)`，写入粒度基本对齐，阻塞点在 QA 的 query keyword generation 和
     category k。
   - LightMem：官方脚本按 user+assistant turn pair 多次调用 `add_memory()`，只在最后一轮
     `force_segment=True, force_extract=True`；当前 adapter 一次性传整段 conversation，
     是明确不对齐点。

## 关键结论

不要马上运行 A-Mem 或 LightMem 的真实 API smoke。

当前安全状态：

- MemoryOS：只跑 LoCoMo，已经按之前约定对齐论文优先参数；暂不跑 LongMemEval。
- Mem0：可以继续按当前 repo/default + 项目 `gpt-4o-mini` 策略讨论，但如要严格复刻
  Mem0 官方 benchmark，还需单独确认 answerer/judge 模型和 LongMemEval chunk size。
- A-Mem：必须先修 wrapper 调用路径，至少补齐 query keyword generation；如果目标是
  论文 Table 1 GPT-4o-mini，应支持按类别 `k`。
- LightMem：用户已指定先采用 `(0.7,512)`；必须先解决 `r/th` 与 add 粒度问题；
  LongMemEval 还需确认 `limit=20`、question time prompt 和 OP-update。OP-update 已确认
  是 Table 2 每个 `r/th` 组合对应的 offline parallel update 行。

## 下一步建议

1. 和用户确认优先实现的 profile：
   - A-Mem：是否直接以 Table 1 GPT-4o-mini 为 official profile。
   - LightMem：LoCoMo official profile 选择 `LightMem(0.7,512)`、`LightMem(0.7,768)` 还是
     `LightMem(0.8,768)`。
2. 用户确认后再写实施计划并改代码。
3. 改代码顺序建议：
   - 先 A-Mem：补 query keyword generation + category k，测试 fake runtime 接收 query。
   - 再 LightMem：补 turn-pair incremental add，profile 字段和 prompt/retrieval 差异。
4. 修完后再运行离线/fake tests；真实 API smoke 仍需用户确认 method、benchmark、样本规模、
   run_id 和预算。

## 2026-06-17 续做更新：LightMem profile / add / prompt

本轮根据用户要求重新阅读 LightMem PDF、README 和官方实验脚本后，完成了不触网的
LightMem adapter 修正。没有运行真实 API，没有修改第三方核心算法。

新增依赖：

- 通过 `uv add pdfplumber pypdf pymupdf` 加入 PDF 读取工具。
- 使用 PyMuPDF 抽取 `third_party/methods/LightMem/lightmem.pdf` 到
  `tmp/pdf_text/lightmem-pymupdf.txt`，用于核对附录和实验设置。

新增/确认的 LightMem 事实：

- 论文 5.1 明确使用 Incremental Dialogue Turn Feeding：对话历史按 turn level、one turn
  at a time 输入。
- README Add Memory 示例也遍历 `session["turns"]` 后逐 `turn_messages` 调
  `lightmem.add_memory(...)`。
- `LightMemory.add_memory(messages, METADATA_GENERATE_PROMPT=None, force_segment=False,
  force_extract=False, ...)` 是原生写入接口。
- LightMem 的 LoCoMo `experiments/locomo/add_locomo.py` 会把每条原始 LoCoMo turn 转成
  `user(content)+assistant("")`，并在每批写入时传
  `METADATA_GENERATE_PROMPT_locomo`；只有最后一批 `force_segment=True` 和
  `force_extract=True`。
- LongMemEval 官方 `experiments/longmemeval/run_lightmem_gpt.py` 按真实
  `user+assistant` pair 写入，并在回答 prompt 中包含
  `Question time:{item['question_date']}`。
- LightMem 的 LoCoMo `search_locomo.py` 检索/回答路径不直接使用 `LightMemory.retrieve()`；
  它读取 Qdrant entry payload、按 speaker 分组，然后用 `ANSWER_PROMPT` 生成答案。

已修改：

- `src/memory_benchmark/methods/lightmem_adapter.py`
  - `LightMemConfig` 新增 `compression_rate` 和 `stm_threshold`。
  - official-mini 当前固定用户指定 `(r=0.7, th=512)`；`stm_threshold != 512` 会抛
    `ConfigurationError`，因为当前 vendored LightMem 源码中 STM `max_tokens=512`
    不是普通 config。
  - backend config 的 `compress_config.rate` 从旧的 `0.6` 改为 `config.compression_rate`。
  - source identity 增加 `experiments/locomo/prompts.py` 和
    `experiments/longmemeval/run_lightmem_gpt.py`。
  - `add(list[Conversation])` 不再把完整 conversation 一次传给 `add_memory()`；
    adapter 内部按来源拆分：
    - LoCoMo：每个原始 turn -> `[user(content), assistant("")]`。
    - LongMemEval：每个真实 `[user, assistant]` pair。
  - 只有最后一批写入使用 `force_segment=True, force_extract=True`。
  - LoCoMo 写入传官方 `METADATA_GENERATE_PROMPT_locomo`。
  - reader prompt 改为：
    - LongMemEval：官方 `Question time:{question_time} and question:{question}` 格式。
    - LoCoMo：读取官方 `ANSWER_PROMPT`，用 speaker-organized memory 布局。
- `configs/methods/lightmem.toml`
  - smoke 和 official-full 均显式写入 `compression_rate = 0.7`、`stm_threshold = 512`。
- `tests/test_lightmem_adapter.py`
  - 新增/修正 fake tests 覆盖 `(0.7,512)`、LoCoMo 单 turn + 空 assistant 增量写入、
    LongMemEval user+assistant pair 写入、LoCoMo/LongMemEval reader prompt。
- `docs/method-interface-inventory.md`
  - 更新 LightMem 当前 adapter 状态和已知差异。
- `docs/method-resource-parameter-audit.md`
  - 更新 LightMem 当前对齐状态和剩余未确认项。
- `docs/current-roadmap.md`
  - 将 LightMem 已完成项拆成子项勾选；保留 search/offline update 未确认项。
- `AGENTS.md`
  - 更新当前断点和最新 focused 验证。

验证：

```text
uv run pytest tests/test_lightmem_adapter.py -q
13 passed, 1 warning

uv run pytest tests/test_lightmem_adapter.py tests/test_amem_lightmem_registry.py -q
17 passed, 1 warning

uv run pytest tests/test_lightmem_registered_prediction.py -q
1 passed

uv run pytest tests/test_documentation_standards.py -q
5 passed

uv run python -m compileall -q src/memory_benchmark tests
exit 0
```

仍未解决/需要用户确认：

1. 是否继续复刻 LightMem 针对 LoCoMo 的 `search_locomo.py` Qdrant payload 检索路径。
   当前 adapter 使用 `LightMemory.retrieve()`，能走官方 LightMemory 检索接口，但字符串结果
   通常不带 speaker payload，因此不是 `search_locomo.py` 的完全等价实现。
2. 是否在真实 smoke 前接入 LightMem offline update：
   - LoCoMo 脚本：`offline_update_all_entries(score_threshold=0.9)`。
   - LongMemEval 独立 OP-update：文档/脚本中常见 `score_threshold=0.8`。
3. 下一步主线仍是 A-Mem Table 1 GPT-4o-mini profile：
   `generate_query_llm(question) -> retrieve_memory(keywords, category_k) -> answer LLM`。
