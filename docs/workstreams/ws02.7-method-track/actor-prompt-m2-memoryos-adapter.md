# Actor 卡 M2-memoryos：施工（speaker 内化 + provenance + 降级审计 + native bundle）

> 派发日 2026-07-14。取证底=`notes/m1-memoryos-evidence.md`(七节锚表,先读)。
> 允许修改:`src/memory_benchmark/methods/memoryos_adapter.py`、新建
> `src/memory_benchmark/methods/memoryos_native_prompts.py`、
> `src/memory_benchmark/methods/config_track.py`、
> `src/memory_benchmark/methods/registry.py`、tests、新建
> `notes/m2-memoryos-adapter.md`。**禁改 third_party**(本卡零例外,含
> eval/——它不被运行,是史料)。禁真实 API。

## 0. Git 纪律
```
git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m2mos -b actor/m2-memoryos-adapter
cd /Users/wz/Desktop/mb-actor-m2mos && uv sync
```
禁 push;只跑目标测试+compileall。所有新增函数/嵌套 helper/测试函数带
中文 docstring(主树全量会查)。

## 1. 架构师裁决（R1-R6,2026-07-14,与用户对齐后定）

- **R1 locomo speaker 注入**:维持 session 粒度 adapter 自配对
  (speaker_a→user_input 侧,官方 eval 同构,M1 §3);**新增:两侧 content
  一律加身份前缀 `{speaker}: {text}`**(mem0 官方同款姿势;身份从 prompt
  层的角色扮演移到数据层内化——unified 轨没有角色扮演,记忆文本必须
  自带归属)。native 轨随之偏离官方 eval 的裸文本,**在 note 与 native
  bundle 注释里声明该偏差及理由**。"只喂 user_input 侧+改 STM→MTM
  闸口"方案**驳回**:要改 third_party 算法核心(红线)、assistant KB 恒空、
  两名 speaker 画像混一。
- **R2 unified prompt 不动**:公平性=同一把尺子,角色扮演只存在于 native
  轨的官方 answer prompt 资产里。
- **R3 超参**:unified 轨维持 pypi 默认(现 TOML 不动);**native LoCoMo
  bundle 超参取 paper 值**(作者 issue"paper 优先",URL 来源待溯已声明):
  STM=7、queue=10、α/β/γ=1/1/1、heat τ=5、topic θ=0.6、top-m=5;
  **MTM 容量语义歧义(200 段长 vs 段数)标 DISPUTED,沿用 2000+注释**;
  filter 阈值论文未给,取 eval 实配 .1/.1/.1+DISPUTED 注释(M1 §2 表)。
  **不物理改 eval/ 文件**——native 跑的是 adapter+pypi 引擎,bundle 配置
  即"用论文参数"的落地点。
- **R4 provenance 升 "turn"**:按 M1 §5 三步——add 侧持久化
  `规范化 page 文本 → source turn ids` sidecar(原子写+schema 版本,镜像
  mem0 M2 样板);检索 `_retrieve_native` 补 `RetrievedItem` items
  (page 原文反查,重复文本映射全部 source ids);旧 state 缺 sidecar
  **fail-fast**,禁 rank 伪造;registry 声明 provenance_granularity="turn"。
- **R5 降级可审计**:retrieve 三路 embedding 异常被 pypi 静默降级为空列表
  (M1 §6)——adapter 层在检索结果异常空+捕获到 embedding 异常迹象时,
  在 RetrievalResult metadata 记 `degraded_retrieval` 标记并计数(零
  third_party diff;做不到精确捕获就在 adapter 包裹调用处 try/log/标记)。
- **R6 native bundle 并入本卡**(流水线新模板):LoCoMo 单格
  (其余四格 single-track collapse 不注册);answer prompt 从
  `eval/main_loco_parse.py:83-142` 逐字资产化(**含角色扮演 system**),
  settings=gpt-4o-mini/temperature 0.7/max_tokens 2000(模型名与统一
  政策无冲突,M1 §7);**judge=无**(官方本地 token-set F1=框架既有免费
  f1,bundle judge_profile 需表达"无 native judge"——若 ConfigTrackBundle
  结构装不下,停工给方案);parity 锁测试逐字;benchmark identity 用显式
  注册配置(mem0 M4 判例:factory 传 context.benchmark_name),禁数据形态
  启发式。

## 2. 施工顺序建议
①R1 前缀(两条 ingest 路径:_ingest_pair 与 session 配对处)+既有测试
调整;②R4 sidecar+items+注册声明;③R5 标记;④R6 prompts 资产+bundle+
parity 锁;⑤新老测试全绿。

## 3. 完成门
目标测试+compileall 全绿(报数字);note=裁决执行记录+锚表+native 偏差
声明。主树全量与文档标准复查归架构师验收。

## 4. 停工条件
- ConfigTrackBundle 无法表达"无 native judge"(结构不匹配)→停工给选项;
- page 文本反查出现无法无损映射的形态(如 pypi 改写 page 文本导致反查
  失配)→停工报形态,禁模糊匹配。

## 施工报告（actor 填写）
（待填）
