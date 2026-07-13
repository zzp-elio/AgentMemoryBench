# Actor 卡 M0.2：LightMem native 配置三方取证（paper / repo 复现目录 / repo 默认）

> 派发日 2026-07-13。自包含卡。**纯取证卡：禁止修改任何 `src/`、`tests/`、
> `third_party/` 代码；唯一交付物是一份 notes 文档。** 禁止调用任何真实 API。

## 0. Git 纪律（先读，违反即停工）

- 你在**独立 worktree + 独立分支 `actor/m0-2-config-audit`** 上工作（用户已建好）。
- 只 commit 到本分支；**禁止 push、禁止 merge/rebase main、禁止碰其他分支/worktree**。
- 本卡不跑测试套件（docs-only），但引用的每个行号都必须现场打开文件核实。

## 1. 背景与目标

双轨政策 `docs/reference/dual-track-config-policy.md` §5 要求对每个 native 格做
**reproduce-vs-paper 三方一致性检查**。LightMem native 格 = locomo、longmemeval。
本卡产出**证据表**，架构师据此裁决：native 内部超参是否 ≠ repo 默认（build 轴
分叉 → 记忆不可复用 → 构建成本 ×2，policy §2）。

## 2. 取证对象（四份配置，逐轴列表）

对 **locomo** 与 **longmemeval** 各做一张表，行 = policy §2 的 7 轴
（answer LLM / answer prompt / judge LLM / judge prompt / judge 语义 /
embedding model / method 内部超参——内部超参逐个列：topic segment 阈值、
buffer/batch 大小、top_k、summary 开关、pre-compressor 设置等，以代码里实际
存在的为准），列 = 四个来源：

- **(a) paper**：`third_party/methods/LightMem/lightmem.pdf`（已 vendored，离线可读）。
  只抄论文明文写出的配置；PDF 里没有的写"paper 未声明"。
- **(b) repo 复现目录**：`third_party/methods/LightMem/experiments/locomo/`、
  `third_party/methods/LightMem/experiments/longmemeval/`（脚本、readme、默认参数、
  argparse 默认值都算；**注意"签名默认值 ≠ 实际调用点"**——以脚本实际传参为准，
  两者不一致时两个都记）。
- **(c) repo 默认**：`third_party/methods/LightMem/src/lightmem/configs/base.py` 及
  各组件 config（memory_manager / text_embedder / topic_segmenter / pre_compressor /
  retriever 子目录）里的 dataclass/字段默认值。
- **(d) 我们框架当前所用**：`configs/methods/lightmem.toml` +
  `src/memory_benchmark/methods/lightmem_adapter.py` 的构造默认 +
  `src/memory_benchmark/methods/config_track.py`（native readout 已定的部分）。

## 3. 硬规则

- **每个单元格都要 `文件:行号` 锚**（PDF 用页码/节号）；查不到 = 写"**来源待溯**"，
  **禁止编造、禁止用训练记忆里的"常识"填表**（playbook 原则 #4/#11；已有 actor
  编造 repo 名的前科，验收会逐锚抽查）。
- 已知裁决直接引用不要重查：locomo native answer prompt = `ANSWER_PROMPT`
  （summary OFF 是 headline，Task1 裁决）；StructMem/`--enable-summary` 不在范围。
- egolife 实验目录不在范围。
- 表后写一节"**失配清单**"：逐轴列出 (a)(b)(c) 互相不一致的地方，只陈述事实
  **不做裁决**（裁决是架构师的活）。

## 4. 交付物

`docs/workstreams/ws02.7-method-track/notes/lightmem-native-config-threeway.md`：
两张表（locomo / longmemeval）+ 失配清单 + "来源待溯"清单。本分支一个 commit。

## 5. 停工条件

- experiments 目录里发现**多套互斥配置**且无法从 readme 判断哪套产生了论文数字
  → 停工，把两套都列出，写进报告等架构师裁决。
- PDF 无法离线解析 → 停工报告（不要去网上找"同款论文"替代）。

## 施工报告（actor 填写）
（待填：commit / 表格完成度 / 来源待溯计数 / 停工事项）
