# Judge 配置全景审计（B6.2 第一步，2026-07-12 架构师一手核证）

> 目的：回答"longmemeval judge 现状是官方还是 lightmem 配置"，并给五
> benchmark judge 配置一张全景表。全部证据为一手 `文件:行号`，比对对象：
> 官方 `third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py`
> vs lightmem `third_party/methods/LightMem/experiments/` vs 框架
> `src/memory_benchmark/evaluators/`。

## 0. 核证结论（先行）

1. **longmemeval 框架 judge 现状 = 官方 parity，不是 lightmem 配置**。
   此前"locomo/longmemeval judge 现用 lightmem 配置"的记忆**半对半错**：
   locomo 是 lightmem 衍生（且有 7 类文本偏差，见 §3），longmemeval 自
   B2 冻结起就是官方 parity，且有逐字与参数双测试锚（见 §1）。
2. **lightmem 的 longmemeval judge prompt 与官方逐字相同**（lightmem
   `run_lightmem_gpt.py:8-28` 原样复制官方 `get_anscheck_prompt`）。
   "judge 双轨"的实质差异只有三处：调用参数、解析函数、abstention
   gate（见 §2）——prompt 本身**无需双轨**。
3. **F2 裁决：不在 B6 开卡，降级为 R0 校准实验前置包**（理由见 §5）。

## 1. longmemeval：框架现状 = 官方 parity（证据链）

| 维度 | 官方 | 框架 | 测试锚 |
| --- | --- | --- | --- |
| prompt 五套模板 | `evaluate_qa.py:24-43` | `longmemeval_judge.py:152-219` 逐字 | `test_llm_judge_parsing.py:319-345` byte-for-byte 参数化（五路由全覆盖） |
| 调用参数 | `n=1, temperature=0, max_tokens=10`（`evaluate_qa.py:102-110`） | `longmemeval_judge.py:94-100` 逐项一致 | `test_llm_judge_parsing.py:192-212`（含 top_p/stream 负空间断言） |
| label 解析 | `'yes' in response.lower()`（`evaluate_qa.py:113`） | `longmemeval_judge.py:146-149` | 同上文件 yes/no 用例 |
| abstention gate | `'_abs' in question_id`（`evaluate_qa.py:101`） | `longmemeval_judge.py:140-143` | `test_longmemeval_abstention_prompt_uses_unanswerable_rule` |
| judge 模型 | 论文 gpt-4o（`model_zoo` 支持 4o/4o-mini，`evaluate_qa.py:11-15`） | gpt-4o-mini（`configs/evaluators/llm_judge.toml`） | **已声明偏差**（longmemeval-frozen-v1 已载） |

结论：现状不动即满足 plan §2 的"默认 = 官方 parity"。

## 2. lightmem vs 官方（longmemeval judge 实际差异——F2/R0 实现清单）

lightmem 源：`third_party/methods/LightMem/experiments/longmemeval/run_lightmem_gpt.py`

| 维度 | 官方 | lightmem | 行号 |
| --- | --- | --- | --- |
| prompt | get_anscheck_prompt 五套 | **逐字相同**（复制官方） | lightmem :8-28 |
| 调用参数 | max_tokens=10, n=1, temperature=0 | **max_tokens=2000, temperature=0.0, top_p=0.8, stream=False, 3 次重试** | lightmem :51-80（LLMModel） |
| 解析 | 全文 `'yes' in lower` | **`true_or_false`：首行去标点 token 精确匹配 yes/y/no/n → 首行子串匹配 → 默认 False** | lightmem :30-48 |
| abstention gate | `'_abs' in id` | **`'abs' in id`**（无下划线） | lightmem :190 |
| judge 模型 | 论文 gpt-4o | gpt-4o-mini | lightmem :136 |

lightmem 的 answer 侧（校准实验要用，见 §6 附录）：retrieve
`limit=20`（:181）；answer prompt = system "You are a helpful
assistant." + user `"Question time:{question_date} and question:{question}\nPlease answer the question based on the following memories: {…\n join}"`（:182-187）；
answer LLM 同一 LLMModel（gpt-4o-mini, max_tokens=2000, temperature=0.0,
top_p=0.8）。

## 3. locomo：框架 judge = lightmem 衍生，但**非逐字**（7 类文本偏差实测）

框架 `locomo_judge.py`（`metric_tier="framework_auxiliary"`，如实标注
非官方——LoCoMo 官方仓库无 LLM judge，此为既有裁决，保持不动）。
2026-07-12 架构师逐字 diff（框架 build_prompt 输出 vs lightmem
`experiments/locomo/llm_judge.py:22-46` ACCURACY_PROMPT 渲染）实测偏差：

1. 引号字符：lightmem `’CORRECT’`（两侧 U+2019）→ 框架 `‘CORRECT‘…’`
   （U+2018/U+2019 配对）；`’gold’` 同款；
2. lightmem 3 处行尾尾随空格被框架删除；
3. lightmem `it's`（ASCII 撇号，2 处）→ 框架 `it’s`（U+2019）；
4. 输出指令两行被框架合并为一行；
5. `key as "label"`（双引号）→ 框架 `key as 'label'`（单引号）；
6. lightmem 模板首行空行被框架去除；
7. "Just return the label" 前的空行位置不同。

另有**判分范围差异**：lightmem 评测跳过 category 5（`llm_judge.py:107-108`），
框架 locomo-judge 全类别判分（cat5 的官方语义由 locomo-f1 的拒答短语
规则承担）。

影响评估：auxiliary tier 无 parity 义务，**冻结行为不动**；但 lightmem
校准实验（playbook 原则 #16）若要复现 lightmem 论文 locomo 数字，须用
逐字 prompt + cat5 跳过对齐 → 归入 R0 前置包（§5）。

## 4. 五 benchmark judge 配置全景表

| benchmark | 现行 evaluator | prompt 来源 | 参数 | 模型 | 与官方偏差 |
| --- | --- | --- | --- | --- | --- |
| LoCoMo | locomo-judge（framework_auxiliary）+ locomo-f1（官方主指标） | lightmem ACCURACY_PROMPT 衍生（§3 有 7 类文本偏差） | temperature=0.0 + json_object（compact） | gpt-4o-mini | 官方无 judge → 无 parity 义务；非逐字 lightmem 已实测留档 |
| LongMemEval | longmemeval-judge | 官方 evaluate_qa.py 逐字（双测试锚） | n=1/temp=0/max_tokens=10 | gpt-4o-mini | 仅模型（论文 gpt-4o，已声明） |
| MemBench | 无 judge（membench-choice-accuracy 单字母解析） | — | — | — | 官方 json_schema 结构化输出 vs 框架文本解析（frozen §7 已声明） |
| BEAM | beam-rubric-judge（官方 parity，E4 裁决） | 官方 rubric prompt | 官方路径 | gpt-4o-mini | int 截断 bug → float 主分 + official_int 双轨（已声明） |
| HaluMem | halumem-extraction/update/qa + 合成 memory-type | 四套官方 prompt 逐字（2,568/4,891/2,259/3,834 字符，AST parity 锚） | 官方 | gpt-4o-mini（官方 eval 同款） | MemOS/Supermemory 官方数字的宽松 prompt 偏差（frozen 已声明） |

判定：**五家现状全部符合既定政策**（官方有 judge 就 parity、官方无
judge 用 lightmem 参考且如实标 auxiliary）。B6.2 无需改任何冻结行为。

## 5. F2 裁决（架构师，2026-07-12）

**F2（judge 双 profile actor 卡）不在 B6 开卡，降级为 R0 校准实验
前置包**。理由：

1. 双轨的"默认轨 = 官方 parity"已是现状，零工作量（§1）；
2. lightmem 轨的唯一消费者是 R0 校准实验（预算未批）；现在实现无
   验证场景（零真实 API 政策下无法试跑），放 R0 前置一次做对；
3. B6 关键路径缩短，method 解冻（M0）提前，服务 7.20 里程碑。

差异清单已在本文件 §2/§3 落盘，实现时照抄即可，无信息损失。原则 #16
推论继续成立：lightmem profile 是**扩展**，默认口径不变，不触发
frozen-v2。

## 6. 附录：lightmem 校准实验配置指针（R0 前置包工作清单）

- **longmemeval**：judge = §2 差异表三处（参数/解析/gate）做成
  `lightmem` profile；answer = §2 answer 侧（prompt 模板 + limit=20 +
  max_tokens=2000/temp=0/top_p=0.8）；数据 = `longmemeval_s`
  （lightmem :140）。
- **locomo**：judge = ACCURACY_PROMPT 逐字（§3 的 7 类偏差全部还原）+
  json_object + temperature=0.0 + **cat5 跳过对齐**；answer =
  `experiments/locomo/prompts.py` 的 ANSWER_PROMPT +
  `search_locomo.py:457-462`（chat.completions，temperature=0.0，
  **prompt 作 system role**，无 max_tokens/top_p 显式设置）。
- 校准目标数字 = lightmem 论文中 A-mem/MemoryOS/Mem0 的
  locomo/longmemeval 结果；对上 = 框架外部校准通过，之后切统一公平
  配置（用户 2026-07-11 拍板战略）。
