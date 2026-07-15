---
id: ws02.6
parent: ws02
status: done（五 benchmark 全部 frozen-v1 + B6 横向总验收完成 2026-07-12；method 侧已转 ws02.7）
created: 2026-07-09
---
# ws02.6 首次真实 smoke 加固（跑通 + 可信双门）

## 收官冻结记录（2026-07-12；现行 method 状态见 ws02.7）

- 2026-07-12（**F1 强验收通过 + B6.5 总验收门通过 → B6 完成、method
  侧解冻**，架构师 Opus 4.8 接任 Fable 5）：actor（codex+GPT-5.6）三
  commit `0c3a7bd`（longmemeval-retrieval-rank）→ `a44f6ed`
  （membench-source-accuracy）→ `16fcc51`（registry + DCG 下标纠正）。
  **架构师独立验收**：① DCG/NDCG/recall 公式**逐行核对官方
  eval_utils.py:4-29 一致**，并写复算脚本拿框架 `_evaluate_at_k` 与
  官方公式（NumPy2.0 兼容复刻）**3000 随机例零失配**（recall_any/all
  +ndcg 全等）；DCG 下标纠正确认正确（`enumerate(rel[1:],start=2)` ↔
  官方 `arange(2,size+1)`）；ideal-DCG 免 corpus 等价式在"gold 全在
  corpus"不变量下精确成立。② 两 evaluator 均走 `evaluate_run_artifacts`
  钩子（evaluation.py:86-95 分发确认生产可用）；k>top_k 跳过不冒充、
  abstention 官方排除、N/A payload、缺上游/未知前缀 fail-fast、空格
  None——代码+测试双证。③ fixture 私有 label/public question 经真实
  序列化（membench 上游经真实 choice evaluator+run_artifact_evaluation
  落盘）；answer_prompts 手写与冻结 recall 测试一致（method 公开输出
  形状无私有漂移风险）。④ registry 两注册 offline+benchmark 专用，
  全量清单断言含两新 metric（H4 教训满足）。⑤ 既有 evaluator/runner/
  third_party 零改动。**定向 33 passed + 全量 1069 passed（1058+11
  自洽）+ compileall**。**建模登记（非缺陷）**：longmemeval-rank 的
  `_ranked_source_ids` 对 item→多 source_turn_ids 采 expand-then-
  truncate-at-k-ids，是 artifact-only 下的合理决定（已记入
  longmemeval-frozen-v1 §7）。**B6.5 门条件全部满足**（全量+compileall
  +两审计无 open 项+GC-1 进 spec+F1 验收）→ **B6 横向总验收完成，
  method 侧正式解冻（Method Track M0 解阻）**。M0 首步（roster 排序、
  首个 method、EverOS 排最后）涉及方向/预算，交用户拍板启动。
- 2026-07-12（**B6.3 + B6.4 完成**，Fable 5）：① **B6.3**：匹配键
  契约升格 spec 通用契约 **GC-1**（spec.md B6 节后新增；三判例 +
  HaluMem N/A 边界 + 新 benchmark 接入检查项；裁定不进 playbook——域
  契约非手艺）。② **B6.4 六项互查完成**，
  [notes/b6-horizontal-audit.md](notes/b6-horizontal-audit.md)：五冻结
  记录无矛盾（smoke/resume/answer 归一五行表全部代码现场核证
  settings.py:245-318）；question-time 五行表全有锚；**3 处加法修复**
  ——locomo/longmemeval 补端到端 category_breakdown 锚（此前与其余三家
  不对齐）、全局私有键黑名单补 `has_answer`/`memory_points`/
  `session_memory_points` 三缺口（quirks "全局黑名单"描述由此修成真；
  全量通过反证无既存泄漏）；prompt parity 两代方法差异登记 ws03；
  **frozen-v2 候选零**。修复后全量 **1058 passed** + compileall。
  **B6 余项：派发 F1（卡已开）→ F1 验收 → B6.5 总验收门 → method
  解冻 M0。**
- 2026-07-12（**B6 开工：B6.2 收口 + F1 卡开**，Fable 5）：
  ① **B6.2 judge 核证完成**，[notes/judge-config-audit.md](notes/judge-config-audit.md)
  ——longmemeval 框架 judge **现状已是官方 parity**（prompt 逐字 +
  参数 n=1/temp=0/max_tokens=10 双测试锚，`test_llm_judge_parsing.py:192-212,319-345`），
  此前"longmemeval 用 lightmem 配置"的说法证伪；lightmem 的
  longmemeval judge prompt 本就逐字复制官方，双轨实质差异只有参数/
  解析/abstention-gate 三处；locomo 框架 judge 系 lightmem 衍生但
  实测 7 类文本偏差（auxiliary tier，冻结不动）。**裁决：F2 不开卡，
  降级 R0 校准实验前置包**（差异清单已落 audit §2/§3/§6，实现时照抄）。
  ② **F1 卡已开待派发**：[actor-prompt-f1.md](actor-prompt-f1.md)
  （`longmemeval-retrieval-rank`：官方 k=[1,3,5,10,30,50] 三指标，
  abstention 官方排除语义；`membench-source-accuracy`：四格合成指标
  走 evaluate_run_artifacts 钩子——落点改裁，原 summary 扩展方案作废，
  理由见 plan §1）。③ plan §1 官方路径笔误勘误（实际
  `src/retrieval/eval_utils.py`，"开工现场复核"纪律再次抓到二手转述
  漂移）。下一步：用户派 F1 → actor 施工期间架构师做 B6.3 + B6.4。
- 2026-07-11（**B6 plan 就绪，执行预定 2026-07-12**）：
  [plan-b6-horizontal.md](plan-b6-horizontal.md)——B6.1 论文指标两
  缺口（actor 卡 F1）、B6.2 judge 双轨（架构师先核 longmemeval 现状
  再开 F2）、B6.3 匹配键通用契约、B6.4 五套契约横向互查（本体）、
  B6.5 总验收门 → method 解冻 M0。执行者 = Fable 5（若在线）或继任
  架构师（先读 handover-to-next-architect.md）。
- 2026-07-11（**HaluMem `frozen-v1`，B5 完成——五 benchmark 全冻**）：
  H5 commit `a55a3de` 验收通过（三操作 e2e 六项断言全在案，SMOKE→FULL
  的既有测试修改是修正"smoke 下测 resume"的概念错误并补 policy 四
  断言）。B5 全程 H1-H5 五批 + 架构师直修一次（update 空检索路由
  parity bug），四次停工全部停对（两次纠正架构师：H1 探针 bug、H4 卡
  落点盲区；一次半对：H5 extraction 误诊/update 真 bug）。冻结门：
  **1058 passed** + compileall + 真实数据抽查（含新事实：generated
  session questions 键恒空、无 memory_points——虚惊核证 3,467 题全在
  普通 session）+ e2e privacy CLEAN + 零真实 API。冻结记录
  [halumem-frozen-v1.md](notes/halumem-frozen-v1.md)；survey 三卡已
  契约化；quirks 全部换实锚。**下一步 = B6 横向总验收**（已立项：
  论文指标两缺口、judge 双轨、"匹配键=公开 id 空间"升通用契约；见
  spec B6 与本断点区 2026-07-11 立项条目）。
- 2026-07-11（H5 停工 → **架构师已裁决 + 直修生产 bug，actor 复工**）：
  三条引证一手核证后**半数成立**——extraction 论断误诊
  （`_update_memory_keys` 本有非空过滤，halumem_extraction.py:350-360，
  空检索 point 已留 integrity）；**update 论断成立是真 parity bug**
  （空检索照常 judge 进分母，与官方 evaluation.py:59-70 分歧，空检索
  point 被双计 + 分母虚增，影响生产非仅 smoke）；runner 无错不动
  （官方同样无条件探针记录，路由在评测端）。架构师直修（D5 先例）：
  update evaluator 跳过空检索（不 judge 不进分母）+
  `skipped_empty_retrieval_count` 诊断计数 + 契约测试（probe record
  经 runner 真实 `_update_probe_record` 序列化）。定向 54 / 全量
  **1055 passed**（1054+1，基线更新）。裁决全文见
  [actor-prompt-h5.md](actor-prompt-h5.md) 末尾，actor 按原卡复工。
- 2026-07-11（codex+GPT-5.6，H5 停工）：真实链路的“空 update 检索
  路由回 integrity、update 分母为 0”要求与生产实现冲突，H5 禁改生产
  代码，故未运行测试、未提交。证据：operation-level runner 对每个 update
  memory point 检索后无条件追加 probe record
  （`src/memory_benchmark/runners/operation_level.py:363-381`）；extraction
  evaluator 仅凭该 record 的 session/index 键存在就把 gold 从 integrity
  互斥移除（`halumem_extraction.py:52-56,81-85`），不检查检索内容是否为空；
  update evaluator 又会把空 `memories_from_system` 拼成空字符串后照常调用
  judge 并计入分母（`halumem_update.py:41-46,61-73`）。因此空 fake 不能
  产生任务卡要求的 `None + count=0`，需架构师裁定是在 runner 仅对非空
  retrieval 落 update record，还是在 evaluator 路由/过滤层表达官方空检索
  语义。H5 测试草稿已撤回，`src/` 零改动。
- 2026-07-11（**H4 架构师强验收通过 → H5 卡已开**）：commit `5b4e358`。
  四套官方 judge prompt（2568/4891/2259/3834 字符）架构师 AST 独立
  复算一致 + 运行时 parity 测试四套全覆盖；合成指标 halumem-memory-type
  官方共享分母复刻、上游缺失 fail-fast、fixture 真实落盘；聚合复审
  12 项全一致；0 分母 None+计数。**验收发现直修一处**：registry 全量
  metric 清单断言未含新 metric（测试过时，根因=卡的自检命令覆盖不到，
  教训已入 H5 卡自检命令）。定向 53、全量 **1054 passed**（1046+8
  自洽，基线更新）。H5 = 三操作离线 e2e（`actor-prompt-h5.md`，禁改
  生产代码，六项断言含 update 0 分母边界与 is_generated_qa_session
  runner 级锚）。H5 过后进入架构师冻结包。交接信已同步。
- 2026-07-11（H4 停工 → **架构师已裁决，actor 复工**）：actor 三个
  候选项的否决理由全部成立（顺序依赖非契约/重复 judge 且 LLM 非
  确定性/半分母违 parity），但存在第四条路且是**既有机制**：
  `memory_type_accuracy` = 合成指标 `halumem-memory-type`，走
  `evaluate_run_artifacts` artifact-level 钩子（已有 8 个 evaluator
  使用，runners/evaluation.py:86-96），读同 run 两份上游 scores
  artifact，零 judge 调用，`requires_api=False`；文件级依赖 fail-fast
  （非执行顺序依赖）；上游 fixture 必须由真实 evaluator+fake judge
  跑出落盘，不许手写 jsonl。裁决全文见
  [actor-prompt-h4.md](actor-prompt-h4.md) 末尾。
- 2026-07-11（codex+GPT-5.6，停工）：在 H4 的
  `memory_type_accuracy` 官方共享分母落点遇到 plan 未覆盖的
  evaluator 边界；H1-H3 已完成并 commit，H4 未改产品代码、未运行
  测试。证据：官方 `eval/evaluation.py:364-383` 在同一次聚合中将
  integrity 与 update 记录累加到同一 `total_num`，再同时计算
  `memory_integrity_acc` / `memory_update_acc` / `memory_acc`；框架将两阶段
  注册为独立 `halumem-extraction` 与 `halumem-update`
  （`src/memory_benchmark/evaluators/registry.py:239-260`），
  `run_artifact_evaluation` 每次只运行一个 evaluator 并立即写该 metric
  自己的 score/summary（`src/memory_benchmark/runners/evaluation.py:56-96,233-271`），
  无跨 metric 聚合阶段。现有 extraction 还会将有检索结果的 update
  point 互斥路由移出 integrity（`halumem_extraction.py:106-117`），update
  记录只在另一 evaluator 中产生（`halumem_update.py:61-100`）。若强行落到
  任一现有 evaluator，只能三选一：依赖评测顺序读另一 metric
  artifact、重复调用另一阶段 judge，或输出非官方半分母。等待架构师
  裁定共享维度应归属新的组合 evaluator/后处理阶段，还是允许某个
  现有 evaluator 重放另一阶段。
- 2026-07-11（**H3 架构师强验收通过 → H4 卡已开 + 交接包创建**）：
  H3 commit `9f77216`，运行时 parity 测试（AST 逐字+原样性断言）与
  answer 归一（官方无硬编码采样参数 → API 默认如实标注，全部行号
  一手核对）质量高；定向 45、全量 **1046 passed**（1038+8 自洽，
  基线更新）。**H4 = B5 最重批**（`actor-prompt-h4.md`）：四套官方
  judge prompt 逐字（eval_tools.py:4-65,68-158,161-215,218-283）+
  聚合 parity + memory_type 维度 + 六类 breakdown + 0 分母契约；
  架构师四裁决已预置（recall=N/A 冻结限制、memory_type 官方原样、
  0 分母 None+计数、valid/Other 诊断字段）。**交接包**：
  `docs/reference/handover-to-next-architect.md`（继任者第一读物，
  Fable 5 离任前持续更新）+ playbook §9/§9.5 刷新。
- 2026-07-11（**H2 架构师强验收通过 → H3 卡已开**）：commit `b89dedd`，
  固定形状 smoke（4 session×8 turn×1 题）+ 三层 fail-fast + 声明式
  policies 全部核证；真实 Medium 锚（4×18/2/5）在测试里钉死；全库
  交替性 0 异常；定向 37、全量 **1038 passed**（1025+13 自洽）。
  验收顺手修 `_default_smoke_history_limit` 过期 docstring。H3 =
  运行时 prompt parity + answer 归一（轻批，`actor-prompt-h3.md`；
  formatted_memory 原样代入已预裁定，官方 llms.py 无硬编码采样参数
  llms.py:28,31）。全量基线更新为 **1038**。
- 2026-07-11（**H2 卡升级 v2 + 用户四项新指令立项**）：用户二次拍板
  推翻"session 内不裁 turn"旧口径——HaluMem smoke 改**固定形状硬裁剪**
  （首 conv 前缀 4 session × 每 session 前 2 turn × QA 1 题，零 CLI
  旋钮 fail-fast；operation-level 交错评测下通用裁剪旋钮语义不通）。
  架构师取证：首 conv s3 天然缺 questions 键 + 首个更新探针 session
  （7 probes），四路径免费全覆盖；smoke 验收口径 = 运行时三操作调用
  ≥1（非聚合桶非空——裁剪后 update 检索空会被官方语义路由回
  integrity，0 分母是 H4 要处理的 evaluator 边界）。**四项立项**：
  ① judge 配置双轨：longmemeval 增加官方/lightmem 可选 judge profile
  （locomo 无官方 judge、保持 lightmem 不动；membench/beam/halumem
  为官方 parity）+ **lightmem 校准实验计划**（全量前用 lightmem 的
  judge+answer 配置复跑 locomo/longmemeval，对齐其论文中 A-mem/
  MemoryOS/Mem0 数字以校准框架，再换统一公平配置）——B6 展开，
  longmemeval judge 现状（是否还是 lightmem 配置）B6 一手核；
  ② evaluator 通用化（recall 骨架/judge 调用壳）+ per-benchmark 指标
  归目录 + prompt 统一存放 + 遗留盘点 → 已扩充进 ws03（铁律：重构
  只在 B6 行为冻结后动手）；③ 长期健壮性排查（wall-clock 泄漏 +
  judge/answer 模型指纹）→ ws03；④ method 名单变更：**去 cognee、
  加 EverOS**（`third_party/methods/EverOS` 已 vendored，上游活跃，
  排 method 接入序列最后）。
- 2026-07-11（**H1 架构师强验收通过** → H2 卡已开）：commit `67eb1a2`
  五项验收全过——lock 一手复核（仅 title 用了 README h1 副标题，架构师
  已修加 title_note）、audit 全部数字独立复算一致（两 variant 各 3,467
  题/491 缺键/evidence 4,651 元素全 `{memory_content,memory_type}` 无
  turn id/3,354 同 session+1,297 前序）、Q1/Q2/Q3+memory_type 分母全部
  一手核证（evaluation.py:59-70,178-185,364-383；prompts.py:90）、定向
  24 passed、全量 **1025 passed** 持平。验收新发现登记 quirks：
  **`is_generated_qa_session` session 官方评测端整体跳过
  （evaluation.py:51-52）**，Long 1,030 个生成 session 只 ingest 不评测
  （H2 锚 adapter 层，H5 锚 runner 层）。actor 本批零缺陷。**H2 卡 =
  `actor-prompt-h2.md`**（三操作最小前缀规则+声明式 policy；架构师裁定：
  运行时走规则，policy 常量 4 由真实数据锚测试钉住；前缀分布基线
  4×18/2/5 actor 须独立复算）。详见 plan-b5-halumem.md §4。
- 2026-07-11（H1 二次停工 → **架构师认错勘误**，actor=codex+GPT-5.6）：
  actor 全量扫描证明 H1 卡的两项数据前提是**架构师探针 bug 的产物**——
  ① evidence 实为原生 list（架构师用 `str(v)` 打印把 list 看成了
  `"[]"`）；② `is_update` 是字符串 "True"/"False"，字符串 "False" 在
  truthy 判断下为真（架构师的 `if m.get("is_update")` 中招，"15/15 全
  update"实为 15/15 全 "False"）。架构师用正确类型判断独立复核 actor
  全对（全库 evidence 6,934 全 list；"True" 6,244 条全带非空
  original_memories；官方探针要求二者同时成立
  `eval_memzero.py:210-222`）。**连锁勘误：正确语义下 smoke 最小前缀 =
  4×18/2/5（非"19/20 前缀=1"）**，smoke 仍极小（≈4 session）。plan
  §2.1/§2.4、H1 卡 Q1/Q2、quirks 档案均已勘误；`is_update` 字符串布尔
  本身登记为 quirk（truthy 判断必错——架构师亲自示范了中招）。actor
  按勘误后的卡复工。
- 2026-07-11（H1 Q3 停工 → **架构师已裁决**，actor=codex+GPT-5.6）：官方
  五脚本 QA prompt 异构，实际语义两族——严格记忆族 3/5（MEMZERO×2+ZEP）
  vs 宽松族 2/5（MEMOS 允许 world knowledge，`prompts.py:89`）；架构师
  另实锤 `PROMPT_MEMOBASE` 是**死代码**（memobase 脚本 import MEMZERO，
  跨 benchmark 第三个死代码案例）。**裁决：canonical = PROMPT_MEMZERO
  逐字**——多数派语义 + 幻觉评测主旨（只依据记忆是幻觉可判定的前提，
  world knowledge 放宽与测量目标自相矛盾）+ 公平性；与官方 MemOS/
  Supermemory 数字的 prompt 偏差进冻结声明。裁决全文见
  [actor-prompt-h1.md](actor-prompt-h1.md) 末尾，actor 复工。
- 2026-07-11（**BEAM `frozen-v1`，B4 完成**）：E1-E5 五批（codex+GPT-5.6
  ×4、cc+MiniMax M3 ×1）+ 架构师逐批强验收；三次停工全部停对（Q2 反例、
  预埋断点、E4 卡口径错——那次纠正的是架构师）。B4 战果：10M 异构 variant
  接纳（plan-dict 展开）、evidence 三形态 + `'--'` + 重复 id 官方数据
  异常全裁决、官方有效评测面判定（零嵌入零 BLEU，event_ordering 走 LLM
  对齐）、int 截断实锤 → float+official_int 双轨、官方 commit 首次可锁。
  冻结门：**1025 passed** + compileall + 真实数据验证 + 泄漏 CLEAN +
  零真实 API。冻结记录 [beam-frozen-v1.md](notes/beam-frozen-v1.md)。
- 2026-07-11（**论文指标覆盖，用户新要求，对 5 benchmark 生效**）：各
  benchmark 论文报告的指标必须覆盖；扩展指标可做但不许乱做（如 NDCG
  需逐项相关性可定义才行）。盘点：LoCoMo（F1+recall ✅）、BEAM（10 类
  rubric 双轨 ✅）、HaluMem（B5 模板项）；**两个缺口立项**：
  ① `longmemeval-ndcg@k` + `recall_all`（官方 `eval_utils.py:12-29`
  一手实锤，ranked items 已在 artifact，artifact-only 可算）；
  ② membench **源文件维度聚合**（论文按 Factual/Reflective ×
  First/Third 报 = first_high/first_low/third_high/third_low 四格，
  conversation_id 前缀天然携带该维度，聚合即可）。两项均为**加法**
  （新 evaluator/summary 维度），不触发 frozen-v2；排 B5 后的 F 批或
  并入 B6 横向验收，spec §9 验收标准同步补条目。

- 2026-07-11（E4 停工 → **架构师已裁决**，actor=codex+GPT-5.6）：actor
  开工核证发现 event_ordering 实际走 `align_type="llm"`（成对
  `llm_equivalence`），与 E4 卡的 semantic/all-MiniLM 口径冲突——**卡是
  架构师错**（读签名默认值没读实际调用点）。架构师随后核完全部辅助函数
  调用链：**官方有效评测面 = 9 类纯 rubric judge + event_ordering 的
  judge+τ×F1（LLM alignment）；嵌入/BLEU/ROUGE/fact-level 全部是分发链
  之外的死代码**。裁决：alignment 跟官方实际 LLM 路径（semantic 作废）；
  extract_facts 死代码 quirk 留档，有效行为=split("\n")；int 截断实锤
  （prompt 定义 0.5 档）→ 主分 float 已声明偏差 + 并报官方 parity int
  聚合；**方法论规矩第二次被证明：parity 审计必须核实际调用点**。裁决
  全文见 [actor-prompt-e4.md](actor-prompt-e4.md) 末尾，actor 复工。
- 2026-07-11（**MemBench `frozen-v1`，B3 完成**）：D1-D5 五批 actor 施工
  （DeepSeek V4 Flash ×2、混合路由 ×1、MiniMax M3 ×2）+ 架构师逐批强
  验收。B3 战果：**3 个 latent bug 实锤修复**（第三人称无冒号时间戳
  19,285 条全漏配、空 target_step_id 令 full load 必崩、evidence 0/1 基
  off-by-one）+ 1 次编造纠正（repo URL）+ 1 次教科书级停工（recall 读
  键位 vs 生产序列化）。冻结门：**1000 passed** 全量 + compileall +
  真实数据抽查（+1 平移三态/str-list 两态/100k 加载/无冒号 turn_time
  e2e 非空）+ 公开泄漏扫描 CLEAN + 零真实 API。冻结记录
  [membench-frozen-v1.md](notes/membench-frozen-v1.md)，批次过程
  [plan-b3-membench.md](plan-b3-membench.md)。已知偏差两条（官方
  json_schema 结构化输出、answer 参数不可考）见冻结记录 §7。当前没有
  开放 actor 卡；下一步 B4 BEAM 由架构师先写 plan 再经用户确认派工。
- 2026-07-11（B4 plan 就绪 + E1 开卡）：[plan-b4-beam.md](plan-b4-beam.md)
  基于当日一手取证起草。核心事实：用户先验核实为真——100K/500K/1M 同构
  （20/35/35 conv），**10M 异构**（10 conv，各带 plans×10 每 plan 独立
  chat）且 **10M variant 未注册**（B4 最大新增项）；10 类问题 × 每类
  2 题 × 100 conv = 2,000 题对上论文；每题 rubric + source_chat_ids
  evidence + 按类异构 gold 字段；turn/user_questions 均带 time_anchor；
  `probing_questions` 须 ast.literal_eval；官方 metric = rubric LLM
  judge 浮点分 + event_ordering 的 Kendall τ×F1（嵌入阈值 0.65）；现有
  beam_rubric_judge 自述"修正官方 int 截断 bug"的主动偏差待 E4 核证。
  用户拍板：变体全接纳、smoke 覆盖 100k+10m、每类指标分开报。E1 卡含
  两个强制判定（10M 消费方式、evidence id 空间）。

- 2026-07-11（D5 停工 → **架构师已裁决并直修**）：actor（cc+MiniMax M3）
  在 D5 T0 对照真实生产 artifact，发现 D4 `membench-recall` 读
  `metadata["evidence"]`，但 `evaluator_private_label_record` 把
  `GoldAnswerInfo.evidence` 序列化在**顶层**（LoCoMo recall 读法正确，
  D4 错位模仿了 LongMemEval 的 metadata 键）；D4 的手写 fixture 把
  evidence 同时塞两处导致单测自洽假绿。三项证据架构师逐字复核为真——
  **同时暴露架构师 D4 验收盲区（没对生产序列化形状验）**。裁决 = 选项 a
  的架构师执行版：① `membench_recall.py` 改读顶层（+注释钉死键位出处）；
  ② fixture 改为**通过真实 `evaluator_private_label_record` 构造**，
  形状漂移结构性不可能（此法固化为 evaluator 契约测试通用规矩）；
  ③ D5 卡一字不改，actor 复工。停工质量：0 行越权代码、证据带
  文件:行号、三选一方案——教科书级。

- 2026-07-10（LongMemEval `frozen-v1`，B2 完成）：C1-C5 五批 actor 施工
  （cc+GLM-5.2 × 2、codex+GPT-5.6 × 3）+ 架构师逐批验收，一次停工裁决
  （turn gold 通路）、两次架构师勘误（role 计数算术错、匹配键 id 空间）。
  冻结门：**923 passed** 全量 + compileall + 真实数据抽查（abstention/
  异常 role/`_m` 流式）+ 公开泄漏扫描 CLEAN + 零真实 API。冻结记录见
  [longmemeval-frozen-v1.md](notes/longmemeval-frozen-v1.md)，批次过程见
  [plan-b2-longmemeval.md](plan-b2-longmemeval.md)。**已知偏差：judge 用
  gpt-4o-mini（论文 gpt-4o）**。当前没有开放 actor 卡；下一步 B3 MemBench
  由架构师先写 plan 再经用户确认派工。
- 2026-07-10（smoke 设计原则升级，用户拍板）：**smoke = 最小路径覆盖切片**
  ——先枚举 benchmark 的运行时路径清单（runner/provider 交互分叉），标准
  smoke 全覆盖；离线分支归契约测试。默认口径 = 唯一认证口径，CLI 旋钮只作
  调试。已写入 spec §6.7。B1/B2 用新尺回核：均单运行时路径，frozen-v1
  仍成立，不返工。
- 2026-07-10（B3 plan 就绪）：[plan-b3-membench.md](plan-b3-membench.md)
  基于当日一手取证起草，含一个**现场实锤的 latent bug**：第三人称
  LowLevel 数据 19,285 条消息时间格式无冒号（`time'…'`），#7 的正则
  （`membench.py:498`）全部漏配——官方数据两文件格式不一致，#7 只在第一
  人称上验证过。D1-D5 五批 + 冻结；**未派工，等用户确认**。

- 2026-07-10（架构师回任 Fable 5 + B2 plan 就绪）：接任第一手核查复现
  890 passed；GPT-5.6 验收修正经用户批准落盘（`2965037`）。用户拍板三项：
  ① 新增通用 `f1` evaluator、`locomo-f1` 保持官方 parity 原名；② 可复现性
  身份=内容，路径只作记录（已修，`b7599a9`，891 passed，playbook 原则 #12）；
  ③ 真实校准不急，smoke 跑通即可拿预算。B2 LongMemEval plan 已基于当日
  一手取证起草：[plan-b2-longmemeval.md](plan-b2-longmemeval.md)（数据形态/
  官方 answer+judge 契约/框架缺口全部现场核实），**未派工，等用户确认**。
- 2026-07-10（LoCoMo `frozen-v1`）：A6 actor commit `6f0039f` 只新增一条离线
  registry/probe 全链路；架构师复跑 `4 passed in 2.86s`，定向总验收
  `326 passed in 31.80s`，compileall 通过，全量回归在修正一条 2026-06 的旧
  MemoryOS/LoCoMo answer 参数断言后为
  `890 passed, 3 deselected, 2 warnings, 4 subtests passed in 143.70s`。冻结记录见
  [locomo-frozen-v1.md](notes/locomo-frozen-v1.md)。当前没有开放的 actor 卡；不得提前
  施工 LongMemEval，下一步先由架构师写 B2 plan/prompt 再交用户确认。
- 2026-07-10（A5 架构师验收）：actor commit `64d2651` 完成 LoCoMo artifact-level
  retrieval recall 与 auxiliary judge 身份；架构师补齐未声明 provenance=N/A、artifact
  question ID 对齐、空 source ids fail-fast 三个边界后，A5 定向复验
  `133 passed in 3.60s`。A5 已关闭；下一批唯一入口为
  [actor-prompt-a6.md](actor-prompt-a6.md)，只补一条离线注册链路并复用既有 resume 测试。
- 2026-07-10（A4 架构师验收）：actor commit `3c68c5d` 完成最小 smoke + LoCoMo
  unified answer；架构师修掉 evidence 派生的 public metadata 泄漏后复跑 A4 定向测试
  `139 passed in 25.32s`，并抽查真实 URL+caption/caption-only turn。A4 已关闭；下一批
  唯一入口为 [actor-prompt-a5.md](actor-prompt-a5.md)，只做离线 metric，不碰 A6。
- 2026-07-10（额度纠偏）：actor 已完成 T1-T3（`1341cb1`、`edefd9a`、`7600076`）
  后按用户要求暂停。架构师完成关键 diff 审读、两处 T3 直修与定向复验
  （`254 passed in 31.48s`），T1-T3 已验收，不再交 actor 重跑。原 10-task 重型 plan
  已改为额度友好 v2：剩余只分 A4/A5/A6 三批，每批一个 5h 窗口内完成；actor 只施工
  + 一次定向自检，架构师负责验收/全量/冻结。下一批唯一入口是
  [actor-prompt-a4.md](actor-prompt-a4.md)。
- 2026-07-10（新任架构师 GPT-5）：完成接任第一手核查：`uv run pytest -q`
  实测 `807 passed, 3 deselected, 2 warnings`，compileall 通过；测试被确认是
  “现行契约 + 兼容行为 + 历史断言”的混合证据，不能单独作为黄金标准。
- 只读核查 2026-07-09 真实实验资产：16 个带 manifest 的新 run 中 10 个有最终
  summary、6 个没有；HaluMem 四格均无 summary，BEAM/A-Mem 未进入这批真实尝试；
  已完成 LoCoMo/LongMemEval 仍为 native prompt。因此本文原“25 格阻断全部清零”
  只保留“已修复已知代码阻断”的含义，不代表 25 格已经验证。
- 用户批准“放慢脚步”：未来 method/benchmark 必须先完成官方仓库一手审计、接口
  选择与排除理由、特殊处理、效率观测设计、真实数据离线契约验证，再允许写实现
  plan 或申请真实 API。
- 用户进一步批准“先稳定一边”：先把五个 benchmark 当作测量仪器，按
  **LoCoMo → LongMemEval → MemBench → BEAM → HaluMem** 严格串行整治；每个都要
  彻底核清官方资产、真实数据、执行流程、公私边界、prompt/metric、smoke、resume、
  artifact 与效率口径并经架构师冻结，前一个未验收，后一个不开工。五个全部冻结
  后 method 侧才解冻。
- 当前冻结：不新增 method/benchmark，不运行新真实 API smoke，不启动 full，不批量
  重写 tests。正式设计 [spec.md](spec.md) 已于 2026-07-10 获用户批准；LoCoMo B0+B1
  已按 [plan](plan-b0-b1-locomo.md) 达到 `frozen-v1`。B2 LongMemEval 尚未写 plan，也
  未向 actor 派工。

## 为什么有这个 workstream（第一手发现）

2026-07-09 用户第一次真跑 5×5 smoke（用注册 method + 位置参数 `smoke` 形式），
一次性暴露了一批只有真跑才会现形的 bug。ws02.5 关闭的是"接口保真"前置门，本
workstream 关闭的是"**能跑通 + 数字可信**"两道门。核心教训（写进
`docs/reference/architect-playbook.md`）：**很多漏洞从实验结果里都看不出来，只有真
跑 + 逐条第一手核代码才现形——二手结论（cc/opencode/deepseek）必须证伪/证实，不
照单全收。**

## 锁定决策（用户拍板 + 架构师裁决，2026-07-09）

1. **输出布局**：位置参数 `smoke/formal` 是唯一正规入口 → 分层
   `outputs/runs/{method}/{benchmark}/{mode}/{run_id}`。**废弃 `--profile` 旗标**
   （用户同意）。Phase A 已先把 legacy `--profile` 也改成 hierarchical（杜绝扁平
   散落）；旗标彻底删除另起 actor 卡（涉及 legacy-only 组合的测试删改）。
2. **answer LLM prompt 默认 unified**（用户拍板第 3 点）。理由：**记忆模块的职责
   是返回记忆，不是自己拼 answer prompt**；unified = benchmark 官方 prompt = 同一
   把尺子，跨 method 才可比。**native 保留为可选对照**（`--prompt-track native`）。
3. **answer LLM 模型+配置：同一 benchmark 下所有 method 必须一致**（用户强调）。
   → `resolve_answer_llm_settings` 现在按 `(method, benchmark)` 返回不同
   temperature/max_tokens/role，**这是公平性 bug**，改为按 benchmark 归一（与
   unified prompt 同源，Phase B）。
4. **smoke 裁剪轴**（用户拍板第 2 点）：隔离空间可裁（locomo=conversation、
   membench=tid）；隔离空间内部——**对话流（第一人称）裁 round，membench 第三人称
   裁 turn**。membench 还要能选跑哪几个源文件（`--membench-sources`，不用
   `1/12/13` 拼字符串）。
5. **smoke 只看跑通、不看答对**：不为"不可回答 smoke""跨 session/round 越界"等
   极端边界写重兜底，越界就 clamp + warning，不崩即可。重兜底留给 full。
6. **turn-level resume 废弃**（架构师赞成）：状态机复杂、只个别 method 支持、smoke
   不需要、full 用 conversation 级 resume 已够。ws03 正式移除，先标 deprecated。
7. **网络兜底统一**：框架 client 与 answer LLM 统一 `60s / 8 次`。
8. **注入粒度跟随 method 原生接口**：拆分（session→pair/turn）由框架
   GranularityAggregator 做，不由 adapter 私拆；异常 session（assistant 先说/连续
   同角色/落单）打 `orphan`/`dangling` 标记但**不丢弃**（否则丢 haystack 干扰信息）。

## 逐条核对（一手证据，标注真伪）

| # | 问题 | 结论 | 根因 | 归属 |
|---|------|------|------|------|
| 1 | 结果扁平存放 | 真（历史遗留双入口）：legacy `--profile`→flat，位置参→hierarchical | `cli/main.py:496` vs `:563` | ✅Phase A |
| 2 | BEAM 直接崩 | 真：指纹把目录当文件 open | `storage/fingerprint.py:75` | ✅Phase A |
| 3 | halumem 4 method 全崩 "active scope" | 真且更重：`operation_level.py` 根本没接效率 collector/scope，provider 仍记录→崩 = **halumem 零效率数据** | `runners/operation_level.py:49`（无 scope） | Phase B |
| 4 | lightmem×membench 崩 | 真，membench adapter 的锅：把 `turn_time/session_time` 全塞 None，但数据每 turn 尾有 `(place…; time…)` | `benchmark_adapters/membench.py:523/466`；`lightmem_adapter.py:1418` | Phase B |
| 5 | locomo/longmemeval 走 native 不走 unified | 真：registry 只给 membench/halumem/beam 设 unified | `benchmark_adapters/registry.py:231,509-538` | Phase B |
| 6 | 网络重试不一致 | 真：框架 30s/2，answer 60s/8 | `config/settings.py:19-22` | ✅Phase A |
| 7 | "LLM 调用次数未聚合" | **❌ opencode 错**：`aggregate_efficiency` 有 `call_count`（stage×model + by-conv + by-question） | `analysis/efficiency.py:48,138,278,290` | 无需改 |
| 8 | lancedb 没进依赖 | 真：opencode 只 `uv pip install`，没进 pyproject | `pyproject.toml` | ✅Phase A |
| 9 | protocol_version typo 静默通过 | 真：`_validate_protocol_version` 无 else 分支 | `runners/prediction.py:1249` | ✅Phase A |
| 10 | answer LLM 各 method 不一致 | 真（公平性 bug）：按 (method,benchmark) 返回不同参数 | `config/settings.py:242-287` | Phase B（并入 unified） |
| 11 | sentinel 泄漏给 answer LLM | 真但**latent**：只在 LegacyProviderBridge 触发，5 个 method 全是 v3，当前不触发 | `core/provider_bridge.py:83` | Phase B |

opencode 其余待核项（A-Mem `str(context)`、token 双来源、items=None、Mem0 无
`clean_failed_ingest_state`、框架级 ingest/retrieve 重试）**尚未逐一验证，不采信**，
放进 Phase B 审计卡逐条证伪/证实。

## 效率指标现状（一手，回答用户"是否完善"）

**已落地 4 类原始 observation（`observability/efficiency/entities.py`）**，覆盖用户
要的三大类：① 记忆构建延迟（`ConversationEfficiencyObservation`）+ memory_build
阶段 token；② 检索延迟 + `injected_memory_context_tokens`（=formatted_memory
token）；③ 每次 LLM 调用一条 `LLMCallObservation`（次数可聚合）。
`MeasurementSource` 已区分 `API_USAGE`/`TOKENIZER_ESTIMATE`——**"能拿 api_usage
就不估计"这条规则 schema 已支持**。

**两个洞**：
- **洞 A（已确认）**：halumem operation-level runner 零效率观测（见 #3）。
- **洞 B（待逐 adapter 审计）**：method 内部 LLM 调用（记忆构建那步）由第三方库自己
  发请求，要拿真实 api_usage 必须 adapter 拦截响应——每个 method 实现不同，很可能
  有的只填了 tiktoken 估算。Phase B 核心审计卡。

## 计划分期

**Phase A — 解阻断 + 机械修复（架构师直接改）**
- [x] BEAM 指纹支持目录（walk+sorted hash） — `storage/fingerprint.py`
- [x] protocol_version fail-fast else 分支 — `runners/prediction.py`
- [x] 网络重试统一 60s/8 — `config/settings.py`
- [x] lancedb 进 pyproject（0.34.0 floor） — `pyproject.toml`
- [x] legacy `--profile` 输出改 hierarchical（footgun 消除） — `cli/main.py`
- [ ] `--profile` 旗标彻底删除（actor 卡：删/改 legacy-only 测试）

**Phase B — 可信度门（actor 卡，架构师写 spec + 验收）**
- [x] halumem operation-level runner 接效率观测（S1 discriminator 原语 + S2 wiring +
  S3 交错 scope + S4 测试）— 架构师直接做，25 格阻断清零，807 passed
- [x] membench adapter 解析 `(place; time)`→`turn_time`（不改 text，双写；session_time
  兜底取首个带时间戳 turn）— 架构师直接改，解掉 lightmem×membench 阻断
- [x] LoCoMo 补 unified_prompt_builder（官方模板）+ 默认 unified；LongMemEval 待 B2
- [x] LoCoMo answer LLM 配置按 benchmark 归一（跨 method 一致）；其他 benchmark 待各卡
- [ ] 效率完备性逐 adapter 审计（api_usage vs 估计）+ formatted_memory 一致性
- [ ] membench 裁剪重设计（`--membench-sources` + 第三人称 `--turns`）
- [ ] sentinel 泄漏改中性占位

**Phase C — 面向 full 的健壮性（不阻塞 smoke）**
- [ ] A-Mem 迁移到通用版 `third_party/A-mem`（正式迁移，像 MemoryOS）
- [ ] resume 两模式落文档 + turn-level resume 标 deprecated（ws03 移除）
- [ ] Mem0 `clean_failed_ingest_state`、框架级 ingest/retrieve 重试（逐条先核）

## #6 halumem 效率 runner —— 第一性原理实现设计（2026-07-09 已定，待施工）

**第一性原理**：效率指标是 benchmark 无关的同一套；halumem 崩+无数据的根因是它走
独立 `operation_level.py`，整套 scope/observation 机制没接。正解 = 让 operation-level
runner 参与**和标准 runner 完全相同**的 scope/observation 机制，而不是绕过或特殊化。

**已第一手核实的两个硬约束**：
1. **必须保留 per-session 交错**（ingest→extraction→update-probe→该 session 的 QA→下一
   session）。官方 `eval/eval_memzero.py:168-256` 就是这个交错顺序，记忆累积、QA-after-
   session-N 只看 1..N。**不能重构成"先全 ingest 再全 QA"**——那会改变 halumem 的
   update/hallucination 语义（答案对错依赖 ingest 时序）。
2. **observation_id 会撞**。`storage.py:94-120` 按 id 幂等合并、**同 id 不同内容直接
   raise**；`_aggregate_observation_id` 用固定 `call_index=0`。per-session 开
   conversation_scope（同 conversation_id）→ 每 session 的 memory_build observation
   id 相同、latency 不同 → 致命冲突。LLM/embedding call 同理（每个 scope 的
   call_index 从 0 重置）。

**实现步骤**：

- **S1 collector 加 scope discriminator 原语（backward-compatible）**：
  `conversation_scope`/`question_scope`/`_scope` 加可选 `scope_discriminator: str|None=None`，
  存入 `_ScopeState`，在 `_build_observation_id` 里**仅当非 None 时**才塞进 payload
  （None 时 payload 不变 → 标准 runner 的 id 一字不改，无测试/resume 破坏）。
  operation-level 传 `session_id` → 每 session 的 id 唯一。conversation_id 字段保持
  干净（不塞 session），by-conversation 聚合仍按 conversation_id 求和（正确总量）。
- **S2 wire collector/store 进 operation-level runner**：
  `run_operation_level_predictions` 签名加 `efficiency_collector`、`model_inventory`、
  `instrumentation_identity`；`run_prediction.py:645` 的 dispatch 把它们传进去（标准路
  径 658-669 已有，照抄）。enabled 时建 `EfficiencyArtifactStore.for_prediction(paths)`
  + `write_model_inventory`。
- **S3 `_run_operation_conversation` 交错开 scope**（每个 provider 调用都要在某个 scope 内，
  否则 "requires active scope" 复现）：
  - 每 session：`with conversation_scope(conv_id, scope_discriminator=session_id)`：
    包住该 session 的 `ingest` + `end_session` + update-probe `retrieve`（默认 stage
    =memory_build），计时后 `record_memory_build_total_latency`。
  - 每 question：`with question_scope(conv_id, question_id)`：
    `operation_stage(RETRIEVAL)` 包 qa `retrieve` + `record_retrieval_result`
    （latency + injected_memory_context_tokens）；`operation_stage(ANSWER)` 包
    `generate_answer` + `record_answer_generation`。
  - `end_conversation`：包一层 `conversation_scope(conv_id, scope_discriminator="end")`
    并 record 一个 memory_build latency（捕获 flush 期可能的 LLM 调用）；`cleanup`
    是 teardown，留在 scope 外（若某 provider 在 cleanup 里 record，视为该 adapter 的 bug）。
  - 每个 scope 退出后把 `scope.records` 收集，`efficiency_store.merge_observations(...)`。
- **S4 测试**：operation-level 一条 conversation 多 session，断言：①不再崩；②产出
  per-session ConversationEfficiencyObservation（id 唯一）；③per-question
  QuestionEfficiencyObservation 带 retrieval/answer latency；④by-conversation 聚合
  latency = 各 session 之和。用 fake provider（可控 record）避免真实 API。

**注意**：injected_memory_context_tokens 的口径要和标准 runner 一致（用同一
`_count_answer_context_tokens` 或 adapter 上报），避免 halumem 与其它 benchmark 的
token 口径不一致——这条并进 Phase B #10 效率完备性审计一起验。

## 项目细节.md 全量映射（确保一条不落，用户 2026-07-09 强调）

用户在 `项目细节.md` 列的 17 条 + 跨消息的要求，逐条归位（**不遗漏**）：

| 项目细节# | 内容 | 归位 | 状态 |
|-----------|------|------|------|
| 1 | 效率指标 3 类（构建延迟+token/检索延迟+token/LLM 次数）+ token 必须 api_usage 非估计 | #6（halumem）+ #10（逐 adapter api_usage 审计） | S1 done，余待做 |
| 2 | answer LLM prompt 默认 unified | #8 | 待做（决策已定：默认 unified，native 可选） |
| 3 | smoke 裁剪：隔离空间可裁 + 内部 round(第一人称)/turn(第三人称)；**halumem 改主意：不再单独 session 级裁剪**（不裁也能跑 extraction 算指标，smoke 只看跑通）；membench 要能选跑哪几个源文件 | #11 + halumem 裁剪重审 | 待做 |
| 4 | 网络兜底：所有 API 调用处都要有超时兜底 + 统一 | Phase A 重试常量统一（done）+ #13 框架级 ingest/retrieve 重试 | 部分 done |
| 5 | formatted_memory 一致性（时间戳/地点等附带信息公平）+ A-Mem str(context) 不可审计 + token 双来源 + items=None | #10 | 待做（逐条证伪/证实 opencode） |
| 6 | **max_workers 默认 1（smoke+full 都是），不设上限，CLI 可覆盖**；配置文件只放 method 可调超参 | 新增 #14a（config/CLI） | **新捕获**，待做 |
| 7 | resume：smoke 不 resume；full 两模式（全量 / 最大隔离空间数）；failed 默认不重试除 `--retry-failed`；turn-level resume 废弃 | #12 + turn-level deprecate | 待做（落文档设计） |
| 8 | 并行：当前隔离空间级并行，未启并发 | 现状确认 | 无需改 |
| 9 | CLI v2（smoke/official-full 互斥等边界） | 已落地 | done |
| 10 | **异常处理：致命异常要捕获详细信息 + 写日志便于 debug** | 新增 #14b（可观测性/异常） | **新捕获**，待做 |
| 11 | 每个 turn 有自己时间戳，无则用 session | #7（membench 已做）+ 通用原则 | membench done |
| 12 | sentinel 泄漏 + LLM 次数已聚合(opencode 错) + smoke_round_limit 对非 locomo 语义 | sentinel→Phase B；LLM 次数已澄清；round_limit→#11 | 部分澄清 |
| 13 | longmemeval 异常 session（顺序倒/连续同 role/单 role）+ memoryos-pypi pair 注入 | 决策 #8（orphan/dangling 标记不丢，框架拆分） | 待做 |
| 14 | **recall@k 等检索级指标：需 method 返回 evidence（turn/session/step id）** | 新增 #14c（需 method 侧支持，较大，可能独立 workstream） | **新捕获**，待评估 |
| 15 | 注入粒度跟随 method 原生接口，拆分由框架做 | 决策 #8 | 待做 |
| 16 | membench 第三人称若 method 原生不支持 turn 级注入怎么办 | 并入 #15/决策 #8 | 待评估 |
| 17 | 其它细节实验中碰壁再补 | 持续 | — |

**新捕获的 #14a/b/c（之前计划遗漏，现补入）**：
- **#14a**：`max_workers` 默认 1（smoke+full），无上限，CLI `--workers`/`--smoke-max-workers`
  覆盖；配置文件只放 method 可调超参。（Phase B/C，需核实现状 CLI 是否已支持覆盖。）
- **#14b**：致命异常统一捕获详细信息（traceback + 上下文）并落 run 日志。（Phase C 可观测性。）
- **#14c**：retrieval-level 指标（recall@k）需 method 在 retrieve 时返回 evidence
  （turn/session/step id，各 benchmark 口径不同）。**依赖 method 侧支持**，是较大能力项，
  可能独立 workstream；先记账，评估后再排期。

## 未来：新 method/benchmark 接入检测流程（用户提议）

用户提议做一个可自动运行的"接入体检"（可用 LLM 跑）：新 method/benchmark 接入后
自动检测潜在漏洞，例如**检测 method 的 token 记录是否用了 api_usage 而非估计**、
formatted_memory 是否可审计、注入粒度是否与原生接口一致等。记入 ws06 或独立
workstream，作为"施工规范"的可执行版。

## 进度日志

- **2026-07-09**：建 workstream。Phase A 落 5 项（BEAM 指纹目录、protocol fail-fast、
  重试统一、lancedb 入依赖、legacy `--profile`→hierarchical），commit `d8200e4`，
  804 passed。
- **2026-07-09**：Phase B 先解剩余阻断 #7——membench adapter 内嵌时间戳解析
  （`benchmark_adapters/membench.py:_membench_turn_time` + session_time 兜底），
  加回归测试 `test_membench_extracts_embedded_turn_time_and_session_fallback`，
  commit `33422a6`，805 passed。
- **2026-07-09**：#6 第一性原理调查完成（核实官方 eval 交错语义不可 2-phase、
  storage 层 id 冲突约束），实现设计定稿写入本文档。落 **S1**（collector scope
  discriminator 原语，backward-compatible，`observability/efficiency/collector.py`
  + 单测）。
- **2026-07-09**：#6 **S2–S4 完成**——`operation_level.py` 接 efficiency_collector/
  model_inventory/instrumentation_identity + 建 EfficiencyArtifactStore；
  `_run_operation_conversation` 拆出 `_ingest_and_probe_session`/
  `_answer_operation_question`，per-session conversation_scope（discriminator=session_id）
  + per-question question_scope，效率口径对齐标准 runner 的
  `_answer_question_retrieve_first`（api_usage 优先）；`run_prediction.py` dispatch 传参；
  加 `test_halumem_operation_level_records_efficiency_observations`。**807 passed，
  25 格 smoke 阻断全部清零**。
- **2026-07-09**：架构师角色交接 Claude→GPT-5.6，写
  `docs/reference/architect-onboarding.md`（跨模型冷启动上岗手册）。
