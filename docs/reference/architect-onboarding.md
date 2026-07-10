# 架构师交接与上岗手册（新架构师从这里开始）

> **本文件的存在理由**：本项目的"架构师"角色会跨模型交接（Claude → GPT-5.6 → …）。
> **新架构师无法读取上一任的私有 memory（`~/.claude/...`），所以一切必须在仓库里**。
> 这份文档是你（新架构师）冷启动时的第一入口，让你不像"刚进公司的新人一样懵逼"。
>
> 交接人：Claude Opus 4.8（2026-07-09）。接任人：GPT-5.6。
> **你上任后也要持续维护本文件 + 下面列的手册**，为再下一任交接。

---

## 0. 30 秒速览：现在是什么状况

- **项目**：Agent Memory benchmark 统一评测框架（把 5 个记忆 method × 5 个 benchmark
  拉到同一套接口/prompt/效率口径下公平对比）。仓库 `memoryBenchmark`，分支 `main`。
- **人类负责人**：张泽鹏（zzp，北邮研究生，做 Agent Memory 方向），每周向导师汇报。
  预算强约束——真实实验要先攒成本表、申预算、才跑全量。
- **你的角色**：**架构师**。写 spec/plan、审查、**第一手核实一切**。你不亲手写大量
  实现代码——实现由**外部 actor**（Codex、WorkBuddy/GLM-5.2、DeepSeek V4 Pro）执行，
  由人类把你写的**任务卡**转达给它们。但小的、机械的、低风险的修复你可以直接改。
- **当前主线**：**5×5 = 25 格极小 smoke 矩阵**（Phase 1 目标，里程碑 2026-07-20），
  每格跑通极小规模、记成本，汇总成本表 → 申预算 → 全量。
- **当前活跃工作**：`ws02.6 first-smoke-hardening`——首次真跑 smoke 暴露的一堆 bug 的
  加固。**读 [`docs/workstreams/ws02.6-first-smoke-hardening/README.md`](../workstreams/ws02.6-first-smoke-hardening/README.md)
  是你上任后的第一件事**，那里有完整的 triage、决策、Phase A/B/C、进度日志。

---

## 1. 上任第一步：按顺序读这些（30 分钟）

1. **`AGENTS.md`**（仓库根）——规则、协作模式、文档导航的**唯一事实源**。先读它。
2. **`CLAUDE.md`**——命令速查 + 代码结构地图（source 目录表、关键入口）。
3. **`docs/roadmap.md`**——Phase 1 目标、workstream 索引、全局约束。
4. **`docs/workstreams/ws02.6-first-smoke-hardening/README.md`**——当前活跃工作全貌
   （含 17 条 项目细节.md 映射、#6 实现设计、Phase B/C 清单）。
5. **`docs/reference/architect-playbook.md`**——历任架构师踩过的坑与纪律（**持续更新**）。
6. **`docs/reference/actor-handbook.md`**——写给 actor 的施工手册（**持续更新**）。
7. **`docs/reference/method-interface-inventory.md`**——5 个 method 的接口/超参一手清单。

读完你应该能回答：主线是什么、当前卡在哪、下一步做什么、哪些是硬规则。

---

## 2. 铁律级工作方式（人类反复强调的，违背会被当场纠正）

这些是这段合作里人类**反复强调**的，比任何技术细节都重要：

1. **证据高于权威（evidence over authority）**。核实**每一条**断言——actor 说的、
   人类说的、你自己的假设——都要**第一手**落到 `file:line` / 真实数据再行动。
   二手结论（cc/opencode/deepseek 的报告）**必须证伪或证实**，不照单全收。
   本会话就抓到 opencode 三条错报中的一条（"LLM 次数没聚合"其实早就聚合了）。
2. **第一性原理**。先搞清楚"为什么"再动"怎么做"。例：#6 halumem 效率 runner，
   先核实官方 eval 的交错语义（不能 2-phase）+ storage 层 id 冲突约束，才定方案。
3. **决策力**。"下一步做什么由你决定，你是架构师，要学会做决定，且每个决定有理有据。"
   **不要每轮甩给人类一个菜单**。给建议+理由+推进；跑偏了人类会纠正。
4. **思想碰撞**。"我的想法你是可以抨击的，就像我抨击你的想法一样。" 不要橡皮图章式
   附和；人类的假设你也要核实、也可以反驳（有据）。
5. **把 actor 当刚进公司的新人**。任务卡要**自包含**：含文件路径、上下文、验收标准、
   为什么。**禁止** "纪律照旧/规矩同上" 这种简写——新人看不懂。
6. **跨模型交接靠仓库**。你读不到上一任的 memory，下一任也读不到你的。**所有该传承的
   东西都写进仓库**（本文件 + 手册 + workstream 文档）。**你也要持续更新它们**。
7. **额度经济**。会话很长时：先落盘 commit 防断电、减少无谓工具调用、写好断点再收尾。
8. **不自动 commit**（除非人类明确要求）。当前在 `main` 上直接提交是人类的既有习惯
   （看 git log 全是 main 直提）；但"预告+推进"过——本会话我预告了要 commit、人类没
   反对，才提交。拿不准就问。
9. **全局巡检**。CLI 成熟度、各 benchmark 数据形态、隔离并行策略这类跨切面问题要主动
   巡检，不等人类点出局部问题。

---

## 3. 项目怎么跑（数据流与三注册表）

完整版见 `CLAUDE.md` 的 Architecture 段。极简版：

```
BenchmarkAdapter.load() → Dataset（公开 Conversation+Question，无 gold）
  → run_predictions()/run_operation_level_predictions()
    → GranularityAggregator 按 method 声明的粒度聚合
    → provider.ingest(unit) / end_session / end_conversation
    → provider.retrieve(RetrievalQuery) → FrameworkAnswerReader → answer
  → artifacts（method_predictions.jsonl 等）
  → run_artifact_evaluation() → evaluator.evaluate() → scores
```

- **协议**：v3 `MemoryProvider`（`core/provider_protocol.py`）。旧协议经 `LegacyProviderBridge` 兼容。
- **三注册表**（声明式）：BenchmarkRegistry / MethodRegistry / EvaluatorRegistry，运行时做兼容校验。
- **两条 runner**：普通 conversation-QA 走 `runners/prediction.py`；**operation-level
  （目前只有 HaluMem，`operation_level=True`）走 `runners/operation_level.py`**——这是个
  独立 runner，容易被忘记（#6 的坑就是它当初没接效率观测）。
- **prompt 双口径**：`native`（provider 自己的 prompt_messages）vs `unified`（benchmark
  官方 prompt builder）。**决策：默认 unified，native 保留可选对照**（理由见 §5）。
- **效率观测**：`observability/efficiency/`——4 类 observation（conversation/question/
  llm_call/embedding_call），`MeasurementSource` 区分 `api_usage` vs `tokenizer_estimate`。

命令速查（`CLAUDE.md` 有全量）：
```bash
uv run pytest -q          # 全回归（默认排除 real API）；当前基线见下方"基线数字"
uv run python -m compileall -q src/memory_benchmark tests
```

---

## 4. 立即接手清单（你上任后的 TODO，按优先级）

**当前 25 格 smoke 阻断已全部清零**（本会话 ws02.6 Phase A + #6/#7 解决）：
- ✅ BEAM×all（目录指纹）、✅ membench×lightmem（内嵌时间戳）、✅ halumem×4method（#6 效率 runner）。

**A. 你直接做 / 验收**：
- 待预算批准后，跑真实 25 格 smoke（**先跑 1 格 `mem0×locomo` 校准成本再铺开**）。
  命令模板见 ws02.6 README 附近 + 本会话历史（`predict <bench> --method <m> --variant <v>
  --conversations N --rounds/--sessions N --confirm-api --run-id <id> smoke` +
  `evaluate --run-id <id> --metric <m> --confirm-api`）。
  ⚠️ 用**位置参数 `smoke`**（分层输出），不要用 legacy `--profile`。

**B. 写成 actor 任务卡转派**（设计已在 ws02.6，直接展开成卡）：
- **#8+#9 同一张卡**：locomo/longmemeval 补 unified_prompt_builder（官方模板：locomo
  `gpt_utils.py`、longmemeval `run_generation.py`）+ answer LLM 配置按 benchmark 归一
  （现在 `config/settings.py:resolve_answer_llm_settings` 按 (method,benchmark) 返回不同
  参数，是公平性 bug）。二者同源（"benchmark 是同一把尺子"）。
- **#11**：membench 裁剪重设计（`--membench-sources first_high,third_low` 选源文件 +
  第三人称 `--turns`、第一人称 `--rounds`）。
- **`--profile` 彻底删除**（本会话只做了"legacy 也走分层"止血；彻底删除涉及 legacy-only
  组合测试的删改，是碎活，适合 actor）。
- **#10 效率完备性审计**：逐 adapter 核内部 LLM 是否用 `api_usage` 而非估计；
  formatted_memory 一致性（A-Mem `str(context)`、items=None、token 双来源）——**逐条
  证伪/证实 opencode 的说法，别照单全收**。

**C. 面向 full 的健壮性（不阻塞 smoke）**：
- A-Mem 迁移到通用产品版（人类已 clone 到 `third_party/A-mem`，复现版在
  `third_party/methods/A-mem`，迁完删复现版）。像 MemoryOS 那样正式迁移。
- resume 两模式落文档 + turn-level resume 标 deprecated（ws03）。
- #14a max_workers 默认 1+CLI 覆盖、#14b 致命异常捕获+落日志、#14c recall@k 需 method
  返回 evidence（较大，可能独立 workstream）。详见 ws02.6 的 17 条映射表。

---

## 5. 已定的关键决策（别推翻，除非有新证据）

- **接口保真（ws02.5）**：所有 method 一律用**通用产品接口**（pip 装的那套），不用任何
  benchmark 专用评测副本（那会造成主场优势、不可比）。MemoryOS 已从 `eval/` 迁到 pypi。
- **超参政策**：用 method **repo/产品默认**（非 benchmark 专用调参），跨全部 benchmark
  同一套；paper≠repo 时优先 repo 默认 + 显式记录。统一**商品化基座**（LLM 模型名 +
  embedder all-MiniLM-L6-v2），保留**算法配置**（top_k 等）为 repo 默认（top_k 跨 method
  语义不可比，不统一）。
- **LLM 统一的边界**：只统一"模型名"；method 内部 LLM 的温度等参数不动；框架 answer LLM
  配置完全统一（且**同一 benchmark 下所有 method 必须一致**，见 #9）。
- **prompt 默认 unified**：记忆模块的职责是**返回记忆**，不是自己拼 answer prompt；
  unified=benchmark 官方 prompt=同一把尺子。native 保留可选对照。
- **注入粒度跟随 method 原生接口**：拆分（session→pair/turn）由框架
  GranularityAggregator 做，不由 adapter 私拆；异常 session（assistant 先说/连续同角色/
  落单）打 `orphan`/`dangling` 标记但**不丢弃**（否则丢 haystack 干扰信息）。
- **检索触发的状态变更是算法、不是污染**：如 MemoryOS 检索会更新 mid_term 热度/访问数
  （驱动记忆升级），**必须保留**（参考官方 eval）；只防止真正的额外写污染。
- **smoke 只看跑通、不看答对**：不为极端边界（不可回答/跨 session 越界）写重兜底，
  越界 clamp+warning 即可，重兜底留给 full。

---

## 6. 陷阱与教训（历任栽过的跟头，别再栽）

- **"东西在哪"先 grep 再规划**。本会话/上会话有**三次**"计划前提错"被 actor/人类抓到：
  (1) 以为 HaluMem 存的是 evidence index（其实是 memory_content）；(2) 以为 MemoryOS
  检索无写副作用（其实热度变更是算法机制）；(3) 以为 config 归一"改 TOML 即可"（其实
  3/5 硬编码在 adapter）。**教训：规划前先第一手核实前提**。
- **operation-level runner 容易被忘**。它是独立于 `prediction.py` 的第二条 runner。任何
  "对所有 benchmark 生效"的改动，记得检查 `operation_level.py` 是否也要改（#6 就是它漏接
  了效率观测）。
- **actor 会误标自己的身份**。WorkBuddy/GLM-5.2 曾自称"Claude Sonnet"，被直接抄进文档。
  **actor 的自述身份也要核实**。
- **二手报告有错**。opencode 报的"LLM 次数没聚合""某某是 bug"里有假阳性。**逐条核**。
- **storage 层 id 唯一性很敏感**。效率 observation 按 id 幂等合并、**同 id 不同内容直接
  raise**。任何"同一 scope 多次进入"的场景要用 `scope_discriminator`（#6 S1 的原语）。

---

## 7. 硬规则（AGENTS.md 有全文，这里是高频项）

- **不改 `third_party/`**（method/benchmark 官方源码只读参考）。
- **私有数据边界**：`gold_answers` 等 12 个黑名单 key 不能进公开 artifact；4 层防护
  （data model / runner rebuild / key scan / manifest check）。
- **真实 API 要人类确认预算+规模+run_id**；默认 `-m "not api"` 排除付费测试。
- **中文 docstring**；`outputs/` 里受保护实验（如 `memoryos-locomo-full-20260603/`）不动。
- **不自动 commit**（§2.8）；review 只看本次改动范围。

---

## 8. 需要你持续维护的文档清单（交接责任）

改了对应内容就同步更新，别让文档漂移：
- **本文件**（`architect-onboarding.md`）——交接/上岗手册。
- `docs/reference/architect-playbook.md`——架构师纪律与踩坑。
- `docs/reference/actor-handbook.md`——actor 施工手册。
- `docs/reference/method-interface-inventory.md`——method 接口/超参清单。
- `docs/roadmap.md` + 活跃 workstream README——方向与进度。
- `AGENTS.md` / `CLAUDE.md`——规则与代码地图。

---

## 9. 基线数字与 git 断点（交接时刻）

- **测试基线**：见 `docs/roadmap.md` / ws02.6 进度日志的最新数字（本会话从 804 增到
  807：Phase A 保持 804 → +membench 时间戳测试 → +collector discriminator 测试 →
  +halumem 效率测试）。**上任先跑 `uv run pytest -q` 确认当前实际数字**（别信文档里
  的旧数，自己核）。
- **ws02.6 已落 commit**（本会话）：`d8200e4` Phase A、`33422a6` #7 membench 时间戳、
  `bf9c42c` #6 S1、`2cfffb4` 17 条映射、以及紧随其后的 #6 S2–S4 commit。
- **#6 状态**：S1–S4 全部完成，halumem 效率 runner 已接通（fake 全链路测试过）；
  **真实 halumem smoke 待预算**。

欢迎上任。有据地决策，别怕碰撞。——Claude Opus 4.8
