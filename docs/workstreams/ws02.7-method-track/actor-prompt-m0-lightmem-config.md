# M0-1 卡：LightMem native prompt/judge 配置一手抽取 + parity 测试

> ws02.7 Method Track M0 首个 actor 批次，2026-07-12 架构师（Opus 4.8）
> 开卡。**纯离线、零真实 API、不碰 method 算法**。本卡只做一件事：把
> LightMem 官方 locomo/longmemeval 实验里的 answer prompt 与 judge 配置
> **一手抄**成框架内注册的 native profile，并用逐字 parity 测试锁死。
> 运行时 config-track 切换机制是**下一卡**，本卡不做。

## 先读（最少清单，按序）
1. `AGENTS.md`
2. `docs/reference/actor-handbook.md`
3. `docs/reference/method-integration-checklist.md` B10
4. `docs/workstreams/ws02.7-method-track/notes/lightmem-m0-audit.md`（B10 表
   有全部一手出处行号）
5. 本卡

## 背景一句话
method 侧刚解冻。native 轨要用 method 自己 paper 的 answer/judge 配置。
本卡把 LightMem 的这些配置从它仓库抄进框架并 parity 锁死，作为后续
config-track 机制的可复用资产。你是本批唯一施工者，架构师验收 + 跑真实
smoke，你不用跑 API。

## 施工纪律
- TDD；每 task 一 commit（一行英文 `feat:`/`test:`）；本地 commit 不 push。
- **零真实 API**；不改 `third_party/`；不改 method 算法；中文 docstring。
- **一手抄，不发明**：每个 prompt/参数必须能落到 LightMem 仓库
  `文件:行号`；抄不准或有歧义 → **停工上报**，不猜。
- **parity 测试必须运行时读官方文件或 AST 逐字比对**（benchmark judge
  parity 测试是先例，如 `tests/test_llm_judge_parsing.py` 的 byte-for-byte
  参数化）。
- 遇本卡未覆盖 → 停工写断点交架构师。

## Task 1：解决 locomo answer prompt 的死代码问题（先做，可能停工）
LightMem locomo answer prompt 有两个候选：`experiments/locomo/prompts.py:148
ANSWER_PROMPT` 与 `:232 ANSWER_PROMPT_StructMem`。**必须核 `search_locomo.py`
的实际调用点**（原则 #2：读签名≠读调用；StructMem 是 LightMem 主打，很
可能实际用的是它）。
- 一手确定实际调用哪个 + 行号。
- 若两个都在活跃分支（按配置切换）或无法一手确定 → **停工上报**，附
  `search_locomo.py` 调用点证据，交架构师裁定用哪个。
- 确定后继续 Task 2。

## Task 2：注册 LightMem native answer profile（locomo + longmemeval）
新文件 `src/memory_benchmark/methods/lightmem_native_prompts.py`（或就近合适
位置，docstring 写明这是 LightMem native 轨资产）：
- **locomo**：native answer prompt builder，签名与现有 unified builder 一致
  （输入 formatted_memory + question 相关字段 → prompt 字符串），内容 =
  Task 1 定下的那个 prompt 逐字。
- **longmemeval**：native answer prompt builder，内容 = `experiments/
  longmemeval/run_lightmem_gpt.py:182-187` 的 system+user 两段逐字
  （"You are a helpful assistant." + "Question time:{question_date} and
  question:{question}\nPlease answer the question based on the following
  memories: {…}"）。
- native answer LLM 参数记为 profile 数据（不硬编码进 builder）：locomo/
  longmemeval 均来自 `LLMModel`（run_lightmem_gpt.py:51-80）= temperature=0,
  max_tokens=2000, top_p=0.8。以 dataclass/dict 形式和 builder 一起注册。

## Task 3：LightMem native judge 配置
- **locomo**：native judge = `experiments/locomo/llm_judge.py:22-46`
  ACCURACY_PROMPT **逐字**（CORRECT/WRONG，json_object，temperature=0）+
  **跳过 category 5**（`:107-108`）。注意：框架现有 `locomo-judge` 是
  lightmem 衍生但有 7 处文本偏差（见 judge-config-audit.md §3）——native
  profile 必须是**逐字无偏差版**，与现有 locomo-judge 分开注册，不改现有。
- **longmemeval**：native judge = `get_anscheck_prompt`
  （run_lightmem_gpt.py:8-28）= **官方逐字**，与框架现有 `longmemeval-judge`
  **完全相同**（已 parity）→ **直接复用现有，不新建**，在文档/profile 映射
  里标注"longmemeval native judge = 官方 = 框架现有"。
- native judge 参数：locomo temperature=0 + json_object；longmemeval
  n=1/temperature=0/max_tokens=10（官方，现有 longmemeval-judge 已是）。

## Task 4：parity 测试
`tests/test_lightmem_native_prompts.py`（新）：
- locomo/longmemeval native answer builder 输出 vs LightMem 仓库源文件
  **运行时读取逐字比对**（占位符替换后 byte-equal）；
- locomo native judge prompt vs `llm_judge.py` ACCURACY_PROMPT byte-equal +
  断言 cat5 跳过语义；
- longmemeval native judge = 复用现有断言（引用现有 evaluator，证明未重复
  造）；
- native answer 参数 = (temp=0,max_tokens=2000,top_p=0.8) 断言；
- **负空间**：断言 native locomo answer ≠ 框架 unified locomo answer
  （证明两轨确有别）、native locomo judge ≠ 现有 locomo-judge（7 偏差被
  消除）。

## 唯一自检命令（只跑这条，报真实输出）
```bash
uv run pytest -q tests/test_lightmem_native_prompts.py \
  tests/test_llm_judge_parsing.py tests/test_locomo_answer_metrics.py
```
（后两个是"没碰坏既有 answer/judge"的哨兵。）全量回归架构师验收时跑。

## 明确不做
- 不做运行时 config-track 切换机制（下一卡，架构师设计后派）。
- 不碰现有 locomo-judge / longmemeval-judge / 任何 unified prompt builder
  的既有行为。
- 不接 beam/membench/halumem 的 native（LightMem 无这些 native 配置）。
- 不碰真实 API、不加载真实模型、不改 third_party、不改 lightmem_adapter 的
  ingest/retrieve。

## 停点
Task 1-4 完成 + 自检通过 + 各 commit 就停，报告（实际模型名自查系统提示）。
Task 1 若停工，先交 Task 1 断点，不硬推。
