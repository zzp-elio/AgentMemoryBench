# HaluMem benchmark frozen-v1

冻结日期：2026-07-11
冻结范围：Phase 1 HaluMem operation-level benchmark 侧（B5，双 variant）
状态：通过架构师验收；未调用真实 API
版本条款：推翻本记录任何契约须 frozen-v2 + 影响分析

## 1. 冻结结论

HaluMem 已具备可复验的官方来源身份、双 variant 真实数据契约、官方
三阶段（提取/更新/QA）metric parity（四套 judge prompt 逐字 + 聚合
公式 + 官方路由语义）、固定形状零旋钮 smoke 与 conversation 级
resume、三操作离线 e2e。可作为 Method Track 的稳定测量仪器（唯一
operation-level benchmark）。不授权真实 API 运行。

## 2. 来源锁（[halumem-source-lock.json](halumem-source-lock.json)）

- 官方仓库 `https://github.com/MemTensor/HaluMem`（README issues badge
  反推）；arXiv 2511.03506（title 以 bibtex 为准，README h1 是宣传
  副标题）；数据发布页 HF `IAAR-Shanghai/HaluMem`；license
  CC-BY-NC-ND-4.0（README badge，快照无独立 LICENSE 文件）
- 快照无 `.git`，官方代码 commit **来源待溯**（如实记录，合规）
- 数据 `data/halumem/HaluMem-{Medium,Long}.jsonl` SHA-256+字节数已锁
  （架构师独立重算一致）；框架只加载 `data/`，third_party 数据不加载

## 3. 数据契约（详见 [halumem-h1-audit.md](halumem-h1-audit.md) 与 datasets 契约卡）

- Medium 20 user/1,387 session/60,146 turn/3,467 题；Long 20 user/
  2,417 session/107,032 turn/3,467 题（多出的 1,030 个 session 全带
  `is_generated_qa_session=True`：**questions 键存在但恒空、无
  memory_points，官方评测端整体跳过 evaluation.py:51-52**，框架 e2e
  断言只 ingest 不产探针/QA）
- 491/1,387 普通 session 无 `questions` 键（缺键 ≠ 空列表，健壮读取）
- `is_update` 是字符串 "True"/"False"（truthy 判断必错）；"True"
  6,244 条全带非空 original_memories（官方探针双条件耦合全库无反例，
  eval_memzero.py:210-222）
- questions `evidence` = 原生 list，4,651 元素全为
  `{memory_content, memory_type}`，**无 turn id**；官方用途 = QA judge
  的 Key Memory Points（evaluation.py:178-185）
- question_type 六类（828/746/769/746/198/180）；memory_points 三类
  （Persona 9,116/Event 4,550/Relationship 1,282）
- 时间三层齐全（turn timestamp/session start·end_time，
  `%b %d, %Y, %H:%M:%S`）；官方 QA prompt 无 question-time 槽（不注入）
- dialogue 全库严格 user/assistant 交替（Medium 0/1,387、Long 0/2,417
  异常）

## 4. Smoke 与 resume

- **固定形状零旋钮**（用户拍板）：首 conversation 三操作最小前缀
  4 session × 每 session 前 2 turn × QA 1 题 = 8 turn ingest +
  112 提取探针 + 7 更新探针 + 1 QA；首 conv s3 天然缺 questions 键 →
  四路径全覆盖；一切 CLI 裁剪参数 fail-fast（operation-level 交错评测
  下通用旋钮语义不通）；20 user 前缀分布 4×18/2/5 真实数据锚测试钉死
- **smoke 验收口径 = 三操作运行时调用各 ≥1（非聚合桶非空）**：裁剪下
  update 检索可空 → 官方路由回 integrity → update 桶空是合法结果
- resume：smoke 禁用；formal conversation 级 checkpoint + question 级
  answer checkpoint；artifact-only evaluation 可独立重跑（e2e 断言
  重跑一致）

## 5. Prompt 与 metric（官方 parity 面）

- unified answer prompt = **PROMPT_MEMZERO 逐字**（2,104 字符；裁决：
  严格记忆族 3/5 多数派 + 幻觉评测主旨 + 公平性；PROMPT_MEMOBASE 是
  官方死代码——memobase 实 import MEMZERO）；运行时 AST parity 测试；
  formatted_memory 原样代入不拼装；answer LLM 官方未设采样参数 →
  API 默认如实标注（llms.py:25-34,60-69）
- 四套官方 judge prompt **逐字**（integrity 2,568/accuracy 4,891/
  update 2,259/QA 3,834 字符，eval_tools.py:4-283）+ 运行时 AST
  parity 测试四套参数化
- 论文 12 项主指标全实现 + 官方 valid 分母/update Other 诊断字段；
  聚合公式逐项与 evaluation.py:214-362 实际调用点核对一致
- **官方路由语义**：update point 检索空 → 归 integrity、不进 update
  分母（H5 停工揪出的生产 parity bug 已修：空检索曾被双计+分母虚增；
  `skipped_empty_retrieval_count` 诊断计数）；0 分母输出 None+计数
- `halumem-memory-type` 合成指标：官方共享分母
  （evaluation.py:364-383，integrity+update 共 total_num）经
  `evaluate_run_artifacts` 钩子读两份上游 scores artifact 合成，零
  judge 调用，上游缺失 fail-fast；阶段内 per-type breakdown 另报
  （denominator_scope 标注两口径）
- QA category_breakdown 按六 question_type 分报

## 6. 实现与验收证据

Actor commits（H1-H5 全部 codex+GPT-5.6）+ 架构师验收/直修：

- `67eb1a2` H1 来源锁+剖面+三判定（两次停工：Q3 prompt 裁决；актор
  纠正架构师探针 bug——evidence 原生 list/is_update 字符串布尔）
- `b89dedd` H2 固定形状 smoke + 声明式 policies（smoke v2 用户二次
  拍板；验收核三层 fail-fast 链路）
- `9f77216` H3 运行时 prompt parity + answer 归一（零缺陷）
- `5b4e358` H4 三阶段 metric parity + 四套官方 judge prompt（一次
  停工 → 合成指标裁决；验收直修 registry 清单测试）
- `20ee6b7` 架构师直修 update 空检索路由（H5 停工揪出的生产 bug）
- `a55a3de` H5 三操作离线 e2e（六项断言；顺带修正旧 resume 测试的
  SMOKE 概念错误）

验收方法：每批架构师亲自复跑 diff 审读 + 独立复算（剖面数字全量脚本
复算、四套 prompt 长度 AST 复算、官方行号逐一现场核对）+ 定向 + 全量。

## 7. 已知限制与声明偏差

1. **retrieval recall = N/A**：evidence 无 turn id，官方 12 指标无
   retrieval recall，禁止文本相似度制造 gold 映射（裁决留档 audit §H4）
2. **prompt 偏差**：官方按 method 分五脚本，MemOS/Supermemory 用宽松
   prompt（允许 world knowledge，prompts.py:90）；框架统一 MEMZERO
   严格语义——与官方该两 method 数字对比时须声明
3. **judge/answer LLM**：官方 MODEL 为环境变量不可考；框架统一
   gpt-4o-mini（Phase 1 政策）；answer 采样参数官方未设 → API 默认
4. `is_generated_qa_session` 跳过语义：Long 1,030 生成 session 只
   ingest 不评测（官方 evaluation.py:51-52 同款）
5. memory_type 合成指标依赖 extraction+update 两份上游 artifact
   （文件级依赖，缺失 fail-fast 明示）；官方共同分母口径原样复刻
   （integrity_acc+update_acc=memory_acc）
6. 官方代码 commit 来源待溯（快照无 .git）

## 8. 冻结门数字

全量 **1058 passed**（B4 冻结门 1025 → B5 净增 33）+ compileall 通过
+ 真实数据抽查（Long 流式首行结构/缺 questions 键 session/is_update
耦合边界/generated session questions 恒空）+ e2e privacy 三层扫描
CLEAN + 零真实 API。
