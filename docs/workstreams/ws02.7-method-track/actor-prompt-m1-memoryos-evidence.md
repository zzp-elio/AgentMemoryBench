# Actor 卡 M1-memoryos：接入取证（三号煎饼,零生产代码）

> 派发日 2026-07-14。**纯取证卡**:只读代码+写
> `docs/workstreams/ws02.7-method-track/notes/m1-memoryos-evidence.md`,
> 不改生产代码/测试/third_party,不调真实 API。流水线上下文见
> `docs/reference/method-onboarding-assembly-line.md`(mem0=二号煎饼判例,
> 对应取证卡 `m1-mem0-evidence.md` 是格式标杆——七节硬答案+严格反证)。
> 本卡按 mem0 终账两条教训扩模板:B8+ 调用点清单内置(§6)、native
> bundle 预研内置(§7),后续 M2 施工卡不再返工取证。

## 0. Git 纪律
```
git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m1mos -b actor/m1-memoryos-evidence
cd /Users/wz/Desktop/mb-actor-m1mos && uv sync
```
禁 push;note 写完本地 commit 一次。验证脚本放 scratch 不入库,note 贴
关键行+输出。**`outputs/memoryos-locomo-full-20260603/` 受保护,只读。**

## 1. 背景(架构师已锚,你验证并展开)

- adapter=`src/memory_benchmark/methods/memoryos_adapter.py`,已接
  **memoryos-pypi 通用产品引擎**(模块 docstring 自述;ws02.5 接口保真
  迁移,plan 在 `ws02.5-method-interface-audit/plan-memoryos-migration.md`)。
- `configs/methods/memoryos.toml`:参数=pypi 官方默认(注释锚
  memoryos.py:30-44),**与旧 eval/ LoCoMo 调参不同**。
- vendored 源:`third_party/methods/MemoryOS-main/`,含 `eval/`(改过
  代码的 LoCoMo 专用评测副本:evalution_loco.py、long_term_memory.py 等)
  与 `memoryos-pypi/`(产品版)等多变体目录。
- clean hook 已挂(2026-07-14 五家全员到齐);provenance 现状="none",
  B5+ 初判"文本反查可无损改造"
  (`ws02.7/notes/memorydata-recall-retrofit-survey.md`)。

## 2. 取证面(七节硬答案,每节锚表)

### §1 官方评测面与 eval/ 代码副本差距
eval/ 与 memoryos-pypi 的**代码级差异清单**(重点:检索路径、答题上下文
构建、记忆分层参数消费),每条 `文件:行号` 对照;官方 LoCoMo 评测流程
(evalution_loco.py)的喂法(什么粒度 add、何时检索、prompt 怎么拼、
answer/judge 用什么模型——**核实际调用点,签名默认值不作数**)。

### §2 超参三岔口(assembly-line 预告考点)
三份配置逐参对比表:**paper 正文 vs eval/ 实配 vs pypi 默认**(现 TOML=
pypi 默认)。每参一行:三值+失配标记。失配且无作者指引的参数按
dual-track-config-policy §5 标 DISPUTED 候选,裁决留架构师。

### §3 注入粒度
官方喂法粒度(evalution_loco.py 的 add 单元)vs adapter 现状
(consume_granularity 声明+registry 行);QA 对/turn/session 哪种;异常
session 处理。

### §4 隔离与 clean
adapter 隔离形态(物理目录?每 isolation_key 什么资源);clean hook 行为
锚+测试名;并行安全三项(清得干净/漏不出去/并行不打架)各给证据或缺口。

### §5 检索副作用与 B5+ 落点
mid_term heat/N_visit 更新=算法机制必须保留(既定裁决,验证 adapter 未
误防);provenance 文本反查方案的具体落点(检索返回结构里有什么可反查
字段,file:line)。

### §6 B8+ 外部调用韧性清单(新模板节,判据=checklist B8+)
全部网络调用点逐行:调用点/用途/timeout(`api_timeout_seconds=120` 从
TOML 落到哪个客户端,实际传参链)/retry/失败 state 语义;embedding 本地性;
模型首次下载点。参照 `notes/m5-mem0-audit.md` §1 的表格形状。

### §7 native 注册面与模型口径(预研,注册本体归 M2)
官方实验的 answer/judge prompt 与模型(paper 或 eval/ 里,一手锚);
memoryos 的 native 格应是哪几个 benchmark(官方只做过 LoCoMo?其余
benchmark 无官方实验=单轨 collapse);adapter retrieve 是否已产
prompt_messages;时间口径(formatted_memory 现在带不带对话时间,对照
mem0 B4 判例)。

## 3. 完成门
note 七节锚表+本地 commit;不跑 pytest(纯文档)。

## 4. 停工条件
- eval/ 与 pypi 差异大到"逐条清单不可行"(整体重写级)→ 停工给差异
  概貌+抽样对照,余下留架构师裁范围;
- 任一节 40 分钟内无法锚定 → 停工列卡住的调用链。

## 施工报告（actor 填写）
（待填）
