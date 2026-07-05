---
id: ws02
doc: plan (Track A2)
status: approved
created: 2026-07-06
---
# ws02 Track A2 实施计划：6 个新 method 机制深读

执行者：Codex。目的：为最终协议设计提供 method 侧输入——Track A 回答了
"装不装得上"，本轮回答"**它的记忆机制到底怎么运转**"。产出将与 5 benchmark
调研卡片一起构成架构师的"粒度需求双向矩阵"。

## 施工纪律

1. 沿用 Track A 全部纪律：零真实 API、零 key、不修改 third_party 与主环境。
2. **隔离试装一律改用 uv**（PyPI SSL 问题已由架构师实测解决）：
   `uv venv /tmp/mech-<method> && uv pip install --python /tmp/mech-<method>/bin/python <pkg>`。
   仍禁止 `uv add` / 改 `pyproject.toml`。
3. 结论必须给源码证据（文件:行号）；推断和事实分开写；不确定就进"未确认项"。
4. 每完成一个 method 立即勾选并 commit（`docs: add <method> mechanism card`）。

## 关键素材（先读）

- 各 method 官方仓库：`third_party/methods/<dir>/`。
- **MemoryData 框架的实际集成代码**（最高价值参考——它已把这 6 个 method
  全部跑起来过）：`第三方框架参考/MemoryData/methods/<name>/` 的 adapter 与
  `MemoryData/utils/agent.py` 中对应分支（如何喂 chunk、何时 finalize）。
- Supermemory 另参考其官方评测框架 `第三方框架参考/memorybench/`。
- Track A 卡片（`audits/<method>.md`）作为起点，不重复其内容。

## 机制卡片格式

每 method 写 `audits/mechanism-<method>.md`，固定 6 节：

1. **写入后内部发生什么**：从原生 ingest API 进入后的完整 pipeline
   （抽取？分层？图构建？向量化？何时调 LLM/embedding？同步还是后台？）。
   用一段流程描述 + 关键源码位置。
2. **原生 ingest 形态**：确切函数签名；输入单位（单 message / message pair /
   自由文本 chunk / 文档 / session 批）；必需与可选字段（时间戳、角色、
   speaker 名、会话 id、用户 id）；是否有显式 flush/finalize/commit 边界；
   MemoryData 是怎么喂它的（贴其 adapter 调用形态）。
3. **检索机制**：检索入口签名；内部检索流程（向量/图/分层/关键词/LLM 重排）；
   返回结构（能否拿到条目级 provenance：来源 id、时间、分数）；
   检索是否调 LLM（对照协议规则 R1：检索服务型 LLM 允许，作答型禁止）。
4. **状态与边界行为**：状态存哪（内存/本地文件/DB/服务端）；多用户/多会话
   隔离的原生机制；有无后台任务（对照 R3 完成判据：如何知道"写入已可检索"）；
   清空/重建状态的官方方式（clean retry 需要）。
5. **对协议设计的含义**：该 method 最舒服的消费粒度是什么（turn / session /
   conversation / 文档 / chunk）；哪种粒度会让 adapter 被迫做别扭的拼接或拆分；
   需要哪些边界信号。**只陈述事实含义，不替架构师做协议选型。**
6. **未确认项**。

## 任务清单

顺序照旧（从轻到重）：

- [ ] mechanism-simplemem.md
- [ ] mechanism-langmem.md
- [ ] mechanism-supermemory.md（含 memorybench 中 provider 实现的调用证据）
- [ ] mechanism-memos.md
- [ ] mechanism-cognee.md
- [ ] mechanism-letta.md
- [ ] 更新 `audits/summary.md`：追加"原生粒度一览"列（6 新 method +
  从 `docs/reference/method-interface-inventory.md` 摘取的 4 个已接入 method，
  凑齐 10 行，供架构师直接做矩阵）
- [ ] 更新 ws02 README 断点，通知架构师

## 验收

- 6 张机制卡片 6 节齐全，每个机制结论有 `文件:行号` 证据。
- summary 的"原生粒度一览"覆盖全部 10 个 method。
- `git status --short` 无主环境依赖文件变更；全程零 API 调用。

## 明确不做

- 不写任何 adapter 代码；不下协议选型结论（第 5 节只陈述事实含义）。
- 不重做 Track A 的安装/配置面内容；不调研 benchmark 侧（架构师负责萃取）。
