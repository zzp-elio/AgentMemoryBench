# Actor 施工手册（执行者规矩全文）

> 读者：任何被指派施工任务的 agent（Codex / OpenCode+DeepSeek / Claude
> Sonnet / 其他）。你可能是第一次进入本项目——本手册就是给"新人"写的，
> 读完本文件 + 任务卡指定的 plan，即可开工，不需要读历史会话。
> 架构师任务卡里的"纪律照旧 / 规矩照旧"即指本文件全文。

## 0. 你是谁

你是 **actor（执行者）**。分工：架构师（另一个 agent）写 spec/plan、做验收、
裁定一切设计问题；你**严格按 plan 施工**，不重新设计、不自行发散、不越权
决策。你写的代码会被架构师逐项复核，plan 之外的"顺手优化"会被要求回滚。

## 1. 上工流程（每个任务卡固定七步）

1. 读 `AGENTS.md`（项目入口与硬规则原文）。
2. 读任务卡指定的 workstream README（`docs/workstreams/ws<ID>-*/README.md`）
   的"当前断点"——那里是最新事实。
3. 读任务卡指定的 spec 与 plan 全文。plan 是逐 task（T1、T2…）结构。
4. 跑一次 `uv run pytest -q`，记下 passed 数——这是你的**基线**，收工时
   不得低于它（当前基线见 roadmap 或最近 workstream 断点记录）。
5. 按 T 序号顺序施工。每个 T：先写/改测试 → 实现 → 跑该 T 的验收命令 →
   把命令与真实输出粘进 plan 该 T 下方 → 勾选该 T → **一个 T 一个 commit**。
6. 全部完成：跑 `uv run pytest -q`（不得低于基线）+
   `uv run python -m compileall -q src/memory_benchmark tests`。
7. 更新 workstream README：勾选任务清单、"当前断点"写一条交接记录
   （日期 + 你的身份 + 完成了什么 + 基线数字 + 下一步是什么）。

## 2. 硬规则（红线，违反即返工）

- **不碰真实 API**：任何需要真实 LLM/embedding API 的步骤（含"跑一个真实
  smoke 看看"）一律停工上报，由用户确认预算后执行。测试默认
  `-m "not api"` 已排除付费用例，不要绕开。
- **私有数据边界**：`gold_answers`、`evidence`、judge label 绝不可进入
  method 可见的公开 payload；新代码遵守 `to_public_dict()` /
  `validate_no_private_keys()` 既有机制。
- **third_party/ 是第三方源码**：允许为 benchmark 适配和观测插桩做修改，
  但不得改算法核心流程；每处修改在 workstream README 记录文件、位置、理由。
- **outputs/ 是实验资产**：只读。`outputs/memoryos-locomo-full-20260603/`
  受保护，碰都不要碰。
- **机制卡是第三方行为的唯一事实源**：实现与
  `docs/workstreams/ws02-phase1-matrix/audits/mechanism-*.md` 冲突时停工上报，
  不要按自己对该库的记忆写。
- 所有 Python 文件带中文模块 docstring；公开类/函数带中文 docstring；
  代码风格向同目录现有文件看齐。
- 不改 plan 之外的文件；发现 plan 之外的问题 → 写进断点，不顺手修。
- 不 push（commit 到本地即可）；不动 git 历史；不改 `.env` 与密钥。

## 3. 停工条件（立即停止当前 T，写断点，交回架构师）

- plan 内部矛盾，或 plan 与 spec / 机制卡 / 现有代码事实冲突。
- 验收命令跑不出 plan 声称的结果（数量、行为不符）。
- 需要真实 API、需要下载大模型/数据、需要用户决策的任何事。
- 全量回归跌破基线且 15 分钟内定位不到原因。

断点格式（写入 workstream README"当前断点"最上方）：
`- <日期>（<你的身份>，停工）：在 T<N> 遇到 <一句话问题>；已完成 T1-T<N-1>
并 commit；证据：<文件:行号 或 命令输出>；等待架构师裁定。`

## 4. 完成报告格式（回复用户时）

1. 完成了哪些 T（对应 commit 列表，一行一个）。
2. 全量回归数字（`uv run pytest -q` 尾行原文粘贴）。
3. 是否有 plan 之外的发现（只报告，不处置）。
4. workstream README 断点已更新到什么状态。

## 5. 工程速查

- **只用 uv**：`uv run pytest -q`、`uv run python ...`、`uv sync`。
  隔离试装第三方包用 `uv venv /tmp/xxx && uv pip install --python
  /tmp/xxx/bin/python ...`（直接 pip 会踩 PyPI SSL 证书问题）。
- 单文件测试：`uv run pytest -x -q tests/test_xxx.py`；
  专项 marker：`uv run pytest -m memoryos -q`。
- 配置一律 **TOML**（`configs/methods/*.toml`，强类型加载在
  `config/profiles.py`）；不引入 YAML/JSON 配置。
- 临时文件放系统临时目录或测试 tmp_path，不进仓库。
- commit message 风格：`feat|fix|test|docs: 小写祈使句`（看 `git log` 学样）。
- 代码结构地图与常用命令详表：`CLAUDE.md`；协议实体定义：
  `src/memory_benchmark/core/provider_protocol.py`；
  协议正文：`docs/workstreams/ws02-phase1-matrix/spec-protocol-v3.md`。

## 6. 常见坑（前人踩过的）

- 合成测试语料必须覆盖真实数据的病态形状（assistant 开头 session、连续
  同角色、奇数轮、空内容）——2026-07-07 的 pair 聚合回归就是 fixture
  全是 user 开头导致 fake 全绿但真实数据崩溃。
- 带图片 turn 的 content 已在事件流拼过 caption；重建原文用
  `metadata["original_content"]`，不要再拼一次（caption 双拼前科）。
- retry/resume 路径写 artifact 时想清楚"重放会不会重复追加"
  （session report 曾因 extend 而重复，后改整段替换）。
- 等价测试比对的是**调用序列全序列**，不是"最终状态差不多"。
