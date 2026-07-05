# Agent Memory Benchmark 接入规划

<style>
table {
  border-collapse: collapse !important;
  table-layout: auto !important;
  width: max-content !important;
  max-width: none !important;
}
th, td {
  padding: 0 2px !important;
  line-height: 0.95 !important;
  vertical-align: top !important;
  white-space: nowrap !important;
}
td, th { font-size: 10px !important; }
</style>

## 目标

本文件基于 `agent_memory_benchmark_list_v0_4.md` 中已有的一手信息做第一轮接入规划：Benchmark 标题、论文摘要、中稿信息、总覆盖方法数，以及 Single-Agent / Multi-Agent / Latent-Context / Multimodal 四类 method 覆盖。

本轮排序不考虑工程接入难度，先回答“哪些 benchmark 最值得纳入系统整体规划”。后续真正实现 adapter / runner / evaluator 时，还需要逐篇深读论文、代码和数据。

## 分层原则

- 第一层只按模态分为 `Text-only/Text-primary` 与 `Multimodal`。这不是价值高低，而是系统输入形态不同。
- `Text-only/Text-primary` 是当前框架最贴近的主线，包含对话、QA、tool-use、web/code/planning 等主要以文本或结构化文本驱动的 benchmark。
- `Multimodal` 单独规划，包含 video/image/egocentric/3D/embodied/GUI 等需要视觉或多模态输入的 benchmark。多模态 benchmark 可能同样高价值，只是不应该和 text-only 在同一接入阶段里混排。

## 排序规则

同一模态内优先级按以下研究价值信号综合排序：

1. 标题和摘要是否明确说明 benchmark 面向 agent memory / long-term memory / memory systems。
2. 中稿信息是否说明其已被会议、期刊或正式 benchmark 集合认可。
3. 社区使用信号：优先看 Single-Agent 和 Multimodal 方法覆盖，其次 Multi-Agent，最后 Latent/Context。
4. 人工校准：LoCoMo 和 LongMemEval 固定前二；高相关且具有代表性的 MemBench、MemoryBench、HaluMem、MemoryAgentBench、BEAM、PersonaMem、MemoryArena 前置。

`记忆来源范式` 和 `任务/工具形态` 只作为接入形态信息，不参与主排序。覆盖数只用于相关度相近时的档内排序，不让弱相关通用 benchmark 压过专门的 agent memory benchmark。

## 新增分类列说明

- `记忆来源范式`：只分 `离线` / `在线`。`离线` 表示 benchmark 先提供固定历史、固定轨迹或固定材料，再把这些信息灌入记忆并评测；`在线` 表示 agent 进入环境后，通过观察、行动、反馈逐步生成和更新记忆。
- `任务/工具形态`：只分 `纯文本输出` / `需要工具交互`。`纯文本输出` 不需要 benchmark 提供可交互环境；`需要工具交互` 需要 benchmark 提供工具、API、网页、代码仓库、GUI、模拟器或具身环境。

## 接入阶段含义

- `第一阶段`：最贴近当前主线的 text-only / text-primary agent memory benchmark，优先深读和接入。
- `第二阶段`：强相关 benchmark，尤其是记忆驱动行为、个性化、多模态长期记忆等；价值高，但可排在核心 text-only 之后。
- `第三阶段`：作为下游 agent task 或能力 proxy 接入，用于检验 memory system 是否提升真实任务表现。
- `暂不接入`：保留在调研资料中，但不纳入当前接入路线图。

## 汇总

<table style="border-collapse:collapse;table-layout:auto;width:max-content;max-width:none;font-size:10px;line-height:0.9;">
<thead>
<tr>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">维度</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">数量</th>
</tr>
</thead>
<tbody>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Text-only/Text-primary</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">76</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Multimodal</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">24</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">28</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">20</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">18</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">34</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">75</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">25</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">58</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">42</td>
</tr>
</tbody>
</table>

## Text-only / Text-primary 接入规划

<table style="border-collapse:collapse;table-layout:auto;width:max-content;max-width:none;font-size:10px;line-height:0.9;">
<thead>
<tr>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">序号</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">接入阶段</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">记忆来源范式</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">任务/工具形态</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Benchmark</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Benchmark论文标题</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">中稿信息</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">覆盖拆分</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">排序信号</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">备注</th>
</tr>
</thead>
<tbody>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LoCoMo</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Evaluating Very Long-Term Conversational Memory of LLM Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：2024 ACL</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总18 / Single 17 / Multi-agent 1 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">代表性优先：高相关核心 benchmark；标题/摘要明确 agent memory 评测；已中稿；Single-Agent 覆盖 17；Multi-Agent 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">多会话对话记忆，含 QA / summary / dialogue generation</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">2</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LongMemEval</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：ICLR 2025</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总13 / Single 13 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">代表性优先：高相关核心 benchmark；标题/摘要明确 memory benchmark；已中稿；Single-Agent 覆盖 13</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">长程交互记忆，常用于 MemoryOS/A-Mem/Mem0/LightMem 等评测</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">3</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemBench: Towards More Comprehensive Evaluation on the Memory of LLM-based Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">代表性优先：高相关核心 benchmark；标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">区分 factual memory / reflective memory；评估 effectiveness / efficiency / capacity</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">4</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemoryBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemoryBench: A Benchmark for Memory and Continual Learning in LLM Systems</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">代表性优先：高相关核心 benchmark；标题/摘要明确 memory benchmark</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">注意与 MemBench 不同</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">5</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">HaluMem</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">HaluMem: Evaluating Hallucinations in Memory Systems of Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">代表性优先：高相关核心 benchmark；标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">operation-level memory hallucination evaluation；GitHub 待确认</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">6</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemoryAgentBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv / OpenReview</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">代表性优先：高相关核心 benchmark；标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">四类能力：accurate retrieval, test-time learning, long-range understanding, selective forgetting</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">7</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">BEAM</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Beyond a Million Tokens: Benchmarking and Enhancing Long-Term Memory in LLMs</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：ICLR 2026</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">代表性优先：高相关核心 benchmark；标题/摘要明确 memory benchmark；已中稿</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Beyond a Million Tokens；超长对话记忆</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">8</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">PersonaMem</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Know Me, Respond to Me: Benchmarking LLMs for Dynamic User Profiling and Personalized Responses at Scale</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总1 / Single 1 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">代表性优先：高相关核心 benchmark；标题/摘要明确 personalized memory / dynamic user profiling；Single-Agent 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">动态用户画像与个性化响应</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">9</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemoryArena</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemoryArena: Benchmarking Agent Memory in Interdependent Multi-Session Agentic Tasks</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv / OpenReview</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">代表性优先：高相关核心 benchmark；标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">项目页：https://memoryarena.github.io/；高相关，强调 Memory-Agent-Environment loop</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">10</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Minerva</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Minerva: A Programmable Memory Test Benchmark for Language Models</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：ICML 2025（arXiv comments）</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 memory benchmark；已中稿</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">自动生成可解释 memory capability tests；覆盖 search / recall / edit / match / compare / state maintenance</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">11</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LOCCO</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Evaluating the Long-Term Memory of Large Language Models</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：Findings of ACL 2025</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 memory benchmark；已中稿</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Long-term Chronological Conversations (LOCCO) dataset；3,080 sessions / 2,981 Q，评估 Accuracy 与 MRS</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">12</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LongMemEval-V2</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LongMemEval-V2: Evaluating Long-Term Agent Memory Toward Experienced Colleagues</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LongMemEval 扩展版本</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">13</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Memora</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">From Recall to Forgetting: Benchmarking Long-Term Memory for Personalized Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">From Recall to Forgetting；FAMA 指标</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">14</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LifeBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LifeBench: A Benchmark for Long-Horizon Multi-Source Memory</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">多源生活轨迹记忆</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">15</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">AMA-Bench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">AMA-Bench: Evaluating Long-Horizon Memory for Agentic Applications</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Agent Memory with Any length；agentic application trajectories</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">16</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">StructMemEval</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Evaluating Memory Structure in LLM Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">评估长期记忆结构组织能力</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">17</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Evo-Memory</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Evo-Memory: Benchmarking LLM Agent Test-time Learning with Self-Evolving Memory</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">streaming benchmark；ReMem / ExpRAG</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">18</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">CloneMem</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">CloneMem: Benchmarking Long-Term Memory for AI Clones</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">基于 diaries / social posts / emails 的个人轨迹记忆</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">19</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MEMTRACK</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MEMTRACK: Evaluating Long-Term Memory and State Tracking in Multi-Platform Dynamic Agent Environments</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Slack / Linear / Git 等多平台动态状态追踪</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">20</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Mem2ActBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Mem2ActBench: A Benchmark for Evaluating Long-Term Memory Utilization in Task-Oriented Autonomous Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv（2026）</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">评估 agent 是否能主动利用长期记忆完成 tool-use/action 参数 grounding；400 memory-dependent tool-use tasks</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">21</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">RealMem</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">RealMem: Benchmarking LLMs in Real-World Memory-Driven Interaction</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">真实项目场景中的 long-term memory</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">22</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemSim</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemSim: A Bayesian Simulator for Evaluating Memory of LLM-based Personal Assistants</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Bayesian simulator；MemDaily dataset</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">23</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MSC</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Beyond Goldfish Memory: Long-Term Open-Domain Conversation</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：ACL 2022</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总6 / Single 5 / Multi-agent 0 / Latent 0 / Multimodal 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 memory benchmark；已中稿；Single-Agent 覆盖 5；Multimodal 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Multi-Session Chat；长期对话一致性</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">24</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MT-Mind2Web</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">On the Multi-turn Instruction Following for Conversational Web Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：2024 ACL Long Paper</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总2 / Single 2 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测；已中稿；Single-Agent 覆盖 2</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Multi-Turn Mind2Web；GitHub 待确认</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">25</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">PerLTQA</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">PerLTQA: A Personal Long-Term Memory Dataset for Memory Classification, Retrieval, and Fusion in Question Answering</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：2024 SIGHAN-10 / ACL Workshop</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 memory benchmark；已中稿</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">中文个人长期记忆数据集</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">26</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemGym</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemGym: a Long-Horizon Memory Environment for LLM Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">2026 新 benchmark；覆盖 tau2-bench / deep research / SWE-Gym / WebArena-Infinity 等</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">27</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Mem-PAL</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Mem-PAL: Towards Memory-based Personalized Dialogue Assistants for Long-term User-Agent Interaction</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">提出 PAL-Bench / PAL-Set；评估长期服务型人机交互中的个性化能力</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">28</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MPR</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Explicit v.s. Implicit Memory: Exploring Multi-hop Complex Reasoning Over Personalized Information</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Explicit vs. Implicit Memory；注意 MPR 也可能被误解成方法名</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">29</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Madial-Bench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MADial-Bench: Towards Real-world Evaluation of Memory-Augmented Dialogue Generation</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 memory benchmark</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">也写作 MADial-Bench / MADail-Bench，拼写需统一</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">30</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">StoryBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">StoryBench: A Dynamic Benchmark for Evaluating Long-Term Memory with Multi Turns</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 memory benchmark</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">动态故事/交互小说环境</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">31</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemoryRewardBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemoryRewardBench: Benchmarking Reward Models for Long-Term Memory Management in Large Language Models</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 memory benchmark</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">评估 reward model 对 memory management 的判断能力</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">32</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LongBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LongBench: A Bilingual, Multitask Benchmark for Long Context Understanding</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：ACL 2024 Long</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总4 / Single 0 / Multi-agent 0 / Latent 4 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 memory benchmark；已中稿；Latent/Context 覆盖 4</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">长上下文静态评测</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">33</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">AgentLongBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">AgentLongBench: A Controllable Long Benchmark For Long-Contexts Agents via Environment Rollouts</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">environment rollouts；dynamic context synthesis</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">34</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">WebChoreArena</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">WebChoreArena: Evaluating Web Browsing Agents on Realistic Tedious Web Tasks</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">项目页：https://webchorearena.github.io/</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">35</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LifelongAgentBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LifelongAgentBench: Evaluating LLM Agents as Lifelong Learners</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv / OpenReview</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Database / OS / KG 三类环境</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">36</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">BABILong</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">BABILong: Testing the Limits of LLMs with Long Context Reasoning-in-a-Haystack</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总1 / Single 0 / Multi-agent 0 / Latent 1 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 memory benchmark；Latent/Context 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">长版 bAbI 风格任务</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">37</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">ConvoMem</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Convomem Benchmark: Why Your First 150 Conversations Don&#x27;t Need RAG</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 memory benchmark</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">75,336 QA；对比 full-context 与 RAG memory</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">38</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">EpisodicGen</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Episodic Memories Generation and Evaluation Benchmark for Large Language Models</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv（2025）</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 memory benchmark</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">基于合成 episodic events；评估 cue-based recall、entity state tracking、chronological ordering 等</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">39</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">DuLeMon</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Long Time No See! Open-Domain Conversation with Long-Term Persona Memory</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：Findings of ACL 2022</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要含 memory 信号；已中稿</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Long Time No See! open-domain conversation with long-term persona memory</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">40</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">PersonaMem-v2</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">PersonaMem-v2: Towards Personalized Intelligence via Learning Implicit User Personas and Agentic Memory</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要含 memory 信号</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">隐式 user persona 与 agentic memory</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">41</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemoryBank</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemoryBank: Enhancing Large Language Models with Long-Term Memory</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要含 memory 信号</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">SiliconFriend 场景；GitHub 待确认</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">42</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">SHARE</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">SHARE: Shared Memory-Aware Open-Domain Long-Term Dialogue Dataset Constructed from Movie Script</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv（2024）</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要含 memory 信号</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">从 movie scripts 构造 shared memory-aware open-domain long-term dialogue；提出 EPISODE framework</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">43</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">ALFWorld</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">ALFWorld: Aligning Text and Embodied Environments for Interactive Learning</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：ICLR 2021</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总7 / Single 3 / Multi-agent 3 / Latent 1 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；已中稿；Single-Agent 覆盖 3；Multi-Agent 覆盖 3；Latent/Context 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">text-based embodied environment</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">44</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">WebShop</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">WebShop: Towards Scalable Real-World Web Interaction with Grounded Language Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：NeurIPS 2022</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总4 / Single 2 / Multi-agent 1 / Latent 1 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；已中稿；Single-Agent 覆盖 2；Multi-Agent 覆盖 1；Latent/Context 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">web shopping</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">45</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">AppWorld</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">AppWorld: A Controllable World of Apps and People for Benchmarking Interactive Coding Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：ACL 2024 Long</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总2 / Single 2 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；已中稿；Single-Agent 覆盖 2</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">API-centric app world</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">46</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Mind2Web</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Mind2Web: Towards a Generalist Agent for the Web</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：2023 NeurIPS Datasets and Benchmarks</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总2 / Single 2 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；已中稿；Single-Agent 覆盖 2</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Web navigation grounding</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">47</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">WebArena</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">WebArena: A Realistic Web Environment for Building Autonomous Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：ICLR 2024</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总2 / Single 2 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；已中稿；Single-Agent 覆盖 2</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">self-hosted web environments</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">48</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">ScienceWorld</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">ScienceWorld: Is your Agent Smarter than a 5th Grader?</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：EMNLP 2022</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总1 / Single 0 / Multi-agent 1 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；已中稿；Multi-Agent 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">interactive science tasks</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">49</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">τ-Bench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">$\tau$-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：ICLR 2025</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；已中稿</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">tau-bench</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">50</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">StreamBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">StreamBench: Towards Benchmarking Continuous Improvement of Language Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：2024 NeurIPS Datasets and Benchmarks</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；已中稿</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">input-feedback sequence；连续改进</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">51</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">GAIA</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">GAIA: a benchmark for General AI Assistants</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：ICLR 2024</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总4 / Single 3 / Multi-agent 0 / Latent 1 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy；已中稿；Single-Agent 覆盖 3；Latent/Context 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">deep research / tool use</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">52</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">SWE-Bench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">SWE-bench: Can Language Models Resolve Real-World GitHub Issues?</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：ICLR 2024</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总3 / Single 2 / Multi-agent 0 / Latent 1 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy；已中稿；Single-Agent 覆盖 2；Latent/Context 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">real GitHub issue repair</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">53</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">ToolBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：ICLR 2024</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy；已中稿</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">API/tool use</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">54</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">BrowseComp</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">BrowseComp: A Simple Yet Challenging Benchmark for Browsing Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">OpenAI benchmark / arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总2 / Single 1 / Multi-agent 0 / Latent 1 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；Single-Agent 覆盖 1；Latent/Context 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">OpenAI BrowseComp；paper/arXiv 链接已核验</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">55</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">PrefEval</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Do LLMs Recognize Your Preferences? Evaluating Personalized Preference Following in LLMs</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总1 / Single 1 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；Single-Agent 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">项目页：https://prefeval.github.io/</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">56</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">DialSim</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">DialSim: A Dialogue Simulator for Evaluating Long-Term Multi-Party Dialogue Understanding of Conversational Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv / OpenReview</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总1 / Single 1 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；Single-Agent 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LongDialQA；多方长对话理解</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">57</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">AgentBoard</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">AgentBoard: An Analytical Evaluation Board of Multi-turn LLM Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总1 / Single 0 / Multi-agent 1 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；Multi-Agent 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">多场景 multi-turn LLM agent analytical evaluation；fine-grained progress rate</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">58</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">ImplexConv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Toward Multi-Session Personalized Conversation: A Large-Scale Dataset and Hierarchical Tree Framework for Implicit Reasoning</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">长期多会话个性化隐式推理</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">59</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Latent Information Discovery Benchmark</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Do LLMs Recognize Your Latent Preferences? A Benchmark for Latent Information Discovery in Personalized Interaction</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Do LLMs Recognize Your Latent Preferences?</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">60</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">xBench-DS</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">xbench: Tracking Agents Productivity Scaling with Profession-Aligned Real-World Evaluations</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">xBench 的 Deep Search / profession-aligned real-world evaluation 子集线索；当前按 xBench 论文记录，子集身份后续再细化</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">61</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LoCoBench-Agent</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LoCoBench-Agent: An Interactive Benchmark for LLM Agents in Long-Context Software Engineering</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LoCoBench 的 agent / interactive software engineering 设置</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">62</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">τ-Bench2</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">$\tau^2$-Bench: Evaluating Conversational Agents in a Dual-Control Environment</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv / OpenReview submission</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">tau-bench2</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">63</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">RECODE-H</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">RECODE-H: A Benchmark for Research Code Development with Interactive Human Feedback</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv（2025）</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">102 research coding tasks；multi-turn LLM-simulated human feedback；GitHub 当前 README 显示 Coming Soon</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">64</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">AgentGym</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">AgentGym: Evolving Large Language Model-based Agents across Diverse Environments</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需核验官方 repo</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">65</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">PaperBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">PaperBench: Evaluating AI&#x27;s Ability to Replicate AI Research</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv / OpenAI benchmark</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Paper replication / scientific agent</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">66</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">SWE-Bench Verified</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">SWE-bench Verified</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">SWE-Bench verified subset / 非独立论文</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总3 / Single 2 / Multi-agent 0 / Latent 1 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy；Single-Agent 覆盖 2；Latent/Context 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">SWE-Bench 的 verified subset；作为 SWE-Bench 集合中的子集保留</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">67</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">PDDL Planning</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Exploring and Benchmarking the Planning Capabilities of Large Language Models</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总1 / Single 0 / Multi-agent 1 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy；Multi-Agent 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">PDDL / classical planning benchmark suite；该条不是 agent memory benchmark 主线，作为 planning/procedural memory proxy 保留</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">68</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">RULER</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">RULER: What&#x27;s the Real Context Size of Your Long-Context Language Models?</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总2 / Single 0 / Multi-agent 0 / Latent 2 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy；Latent/Context 覆盖 2</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">synthetic long-context retrieval</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">69</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">HELMET</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">HELMET: How to Evaluate Long-Context Language Models Effectively and Thoroughly</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">How to Evaluate Long-Context Models Effectively and Thoroughly</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">70</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LoCoBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LoCoBench: A Benchmark for Long-Context Large Language Models in Complex Software Engineering</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">长上下文代码/软件工程 benchmark</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">71</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LongBench v2</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LongBench v2: Towards Deeper Understanding and Reasoning on Realistic Long-context Multitasks</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LongBench 后续版本</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">72</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">HotpotQA</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">HotpotQA: A Dataset for Diverse, Explainable Multi-hop Question Answering</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：2018 EMNLP</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总10 / Single 5 / Multi-agent 2 / Latent 3 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">弱相关 proxy/参考；通用能力 proxy；已中稿；Single-Agent 覆盖 5；Multi-Agent 覆盖 2；Latent/Context 覆盖 3</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">可被改造成 memory retrieval 测试</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">73</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">BabyAI</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">BabyAI: A Platform to Study the Sample Efficiency of Grounded Language Learning</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：ICLR 2019</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">弱相关 proxy/参考；通用 agent/task proxy；已中稿</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">传统 agent/RL 环境</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">74</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MuSiQue</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MuSiQue: Multihop Questions via Single-hop Question Composition</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：TACL 2022</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总4 / Single 2 / Multi-agent 1 / Latent 1 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">弱相关 proxy/参考；通用能力 proxy；已中稿；Single-Agent 覆盖 2；Multi-Agent 覆盖 1；Latent/Context 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">多跳 QA</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">75</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">2WikiMultiHopQA</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Constructing A Multi-hop QA Dataset for Comprehensive Evaluation of Reasoning Steps</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：COLING 2020</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总3 / Single 1 / Multi-agent 1 / Latent 1 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">弱相关 proxy/参考；通用能力 proxy；已中稿；Single-Agent 覆盖 1；Multi-Agent 覆盖 1；Latent/Context 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">多跳 QA</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">76</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">HumanEval</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Evaluating Large Language Models Trained on Code</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">技术报告 / arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总2 / Single 1 / Multi-agent 1 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">弱相关 proxy/参考；通用能力 proxy；Single-Agent 覆盖 1；Multi-Agent 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">与 agent memory 关系弱</td>
</tr>
</tbody>
</table>



## Multimodal 接入规划

<table style="border-collapse:collapse;table-layout:auto;width:max-content;max-width:none;font-size:10px;line-height:0.9;">
<thead>
<tr>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">序号</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">接入阶段</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">记忆来源范式</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">任务/工具形态</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Benchmark</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Benchmark论文标题</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">中稿信息</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">覆盖拆分</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">排序信号</th>
<th style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">备注</th>
</tr>
</thead>
<tbody>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Mem-Gallery</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Mem-Gallery: Benchmarking Multimodal Long-Term Conversational Memory for MLLM Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：ACL 2026 Long</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测；已中稿</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">多模态长期会话记忆；评估 memory extraction / reasoning / knowledge management</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">2</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemLens</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MemLens: Benchmarking Multimodal Long-Term Memory in Large Vision-Language Models</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">多模态多会话记忆</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">3</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第一阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">FindingDory</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">FindingDory: A Benchmark to Evaluate Memory in Embodied Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Habitat 场景下 embodied memory</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">4</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">M3-Bench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Seeing, Listening, Remembering, and Reasoning: A Multimodal Agent with Long-Term Memory</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv（2025）</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总1 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测；Multimodal 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">M3-Agent 提出的 M3-Bench；长视频 QA，评估视觉/听觉输入下的 long-term memory 与 cross-modal reasoning</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">5</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">3DMem-Bench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">3DLLM-Mem: Long-Term Spatial-Temporal Memory for Embodied 3D Large Language Model</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">3DLLM-Mem 中提出</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">6</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MMRC</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MMRC: A Large-Scale Benchmark for Understanding Multimodal Large Language Model in Real-World Conversation</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：ACL 2025 Long</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 memory benchmark；已中稿</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Multi-Modal Real-world Conversation；信息提取、跨轮推理、信息更新、图像管理、记忆召回、拒答</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">7</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MMInA</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MMInA: Benchmarking Multihop Multimodal Internet Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv（2024）</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总1 / Single 1 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 agent memory 评测；Single-Agent 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">原条目 MMLnA 更正为 MMInA；1,050 human-written multihop multimodal web tasks；论文包含 memory augmentation baseline</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">8</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Memory-QA</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Memory-QA: Answering Recall Questions Based on Multimodal Memories</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总1 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 memory benchmark；Multimodal 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Answering Recall Questions Based on Multimodal Memories</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">9</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第二阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LVBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LVBench: An Extreme Long Video Understanding Benchmark</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总2 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 2</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">标题/摘要明确 memory benchmark；Multimodal 覆盖 2</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">超长视频</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">10</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MineDojo</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MineDojo: Building Open-Ended Embodied Agents with Internet-Scale Knowledge</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：2022 NeurIPS Datasets and Benchmarks</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总1 / Single 1 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；已中稿；Single-Agent 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Minecraft 开放世界</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">11</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">NetHack &amp; MiniHack</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">The NetHack Learning Environment</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">NLE 已中稿：NeurIPS 2020</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总1 / Single 1 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；已中稿；Single-Agent 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MiniHack: https://github.com/facebookresearch/minihack</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">12</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">OSWorld</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">OSWorld: Benchmarking Multimodal Agents for Open-Ended Tasks in Real Computer Environments</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：NeurIPS 2024 Datasets and Benchmarks</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；已中稿</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">desktop/OS GUI</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">13</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Crafter</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Benchmarking the Spectrum of Agent Capabilities</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：NeurIPS 2021 Datasets and Benchmarks</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；已中稿</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">RL/game environment</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">14</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">EmbodiedBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">EmbodiedBench: Comprehensive Benchmarking Multi-modal Large Language Models for Vision-Driven Embodied Agents</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：ICML 2025 Oral</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy；已中稿</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需核验是否对应用户条目</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">15</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">第三阶段</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">EgoSchema</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">EgoSchema: A Diagnostic Benchmark for Very Long-form Video Language Understanding</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：NeurIPS 2023 Datasets and Benchmarks</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总3 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 3</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy；已中稿；Multimodal 覆盖 3</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Ego4D first-person video</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">16</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">ALFRED</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">ALFRED: A Benchmark for Interpreting Grounded Instructions for Everyday Tasks</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">已中稿：CVPR 2020</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy；已中稿</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">视觉语言导航/操作</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">17</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">在线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">需要工具交互</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">OdysseyBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">OdysseyBench: Evaluating LLM Agents on Long-Horizon Complex Office Application Workflows</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv（2025）</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用 agent/task proxy</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Word / Excel / PDF / Email / Calendar 等办公应用长流程；包含 OdysseyBench+ 与 OdysseyBench-Neo</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">18</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Video-MME</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Video-MME: The First-Ever Comprehensive Evaluation Benchmark of Multi-modal LLMs in Video Analysis</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总5 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 5</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy；Multimodal 覆盖 5</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">视频 MME</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">19</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">EgoLife / EgoLifeQA</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">EgoLife: Towards Egocentric Life Assistant</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv（2025）</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总3 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 3</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy；Multimodal 覆盖 3</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">EgoLife Dataset + EgoLifeQA；面向可穿戴第一视角生活助手，包含 recall / health habit monitoring / personalized recommendation 等问题</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">20</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">HLE</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Humanity&#x27;s Last Exam</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总2 / Single 2 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy；Single-Agent 覆盖 2</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Humanity&#x27;s Last Exam；高难闭卷学术 QA / 多模态能力 benchmark</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">21</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MLVU</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MLVU: Benchmarking Multi-task Long Video Understanding</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总2 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 2</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy；Multimodal 覆盖 2</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">长视频理解</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">22</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LongVideoBench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">LongVideoBench: A Benchmark for Long-context Interleaved Video-Language Understanding</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总1 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy；Multimodal 覆盖 1</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">长视频 QA</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">23</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">MM-Needle</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">Multimodal Needle in a Haystack: Benchmarking Long-Context Capability of Multimodal Large Language Models</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">通用能力 proxy</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">视觉/多模态 needle 检索</td>
</tr>
<tr>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">24</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">暂不接入</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">离线</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">纯文本输出</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">GenAI-Bench</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">GenAI-Bench: Evaluating and Improving Compositional Text-to-Visual Generation</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">未确认：仅 arXiv</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">总0 / Single 0 / Multi-agent 0 / Latent 0 / Multimodal 0</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">弱相关 proxy/参考；通用能力 proxy</td>
<td style="padding:0 2px;line-height:0.9;vertical-align:top;white-space:nowrap;font-size:10px;">与 agent memory 关系弱</td>
</tr>
</tbody>
</table>
