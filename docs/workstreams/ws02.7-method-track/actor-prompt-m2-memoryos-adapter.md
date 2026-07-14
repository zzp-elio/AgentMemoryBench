# Actor 卡 M2-memoryos：施工（speaker 内化 + provenance + 降级审计 + native bundle）

> 派发日 2026-07-14。取证底=`notes/m1-memoryos-evidence.md`(七节锚表,先读)。
> 允许修改:`src/memory_benchmark/methods/memoryos_adapter.py`、新建
> `src/memory_benchmark/methods/memoryos_native_prompts.py`、新建
> `src/memory_benchmark/methods/image_text.py`(R7 共享 helper)、
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

- **R1 locomo speaker 注入(2026-07-14 二次修订,用户方案胜出)**:
  **ingest 裸文本 + 检索出口身份映射**,完全镜像官方 eval 姿势
  (`main_loco_parse.py` 架构师逐段核过):
  1. ingest:维持 session 粒度 adapter 自配对(speaker_a→user_input 槽/
     另一 speaker→agent_response 回填,官方 :159-200 同构);content
     **不加任何 speaker 前缀**(官方裸文本);image caption 按官方拼
     `{text} (image description: {caption})`(官方 :180-181)。
  2. speaker 映射持久化:locomo conversation metadata 已有 speaker_a/
     speaker_b(`benchmark_adapters/locomo.py:160-161`);映射须随
     method state 持久化(建议并入 R4 sidecar 同文件加 `speaker_map`
     字段),resume 后缺失 **fail-fast**——检索时才用得到它,不能靠
     ingest 期内存缓存。
  3. formatted_memory 出口映射(改造点=M1 §7 锚的 :1244-1299 构造处):
     STM/检索 page 按官方 `{speaker_a}: {user_input}\n{speaker_b}:
     {agent_response}\nTime:({timestamp})` 拼法(官方 :88-96);
     profile/knowledge 段按**官方三正则**回写身份:
     `re.sub(r'(?i)\buser\b', speaker_a, ...)`、
     `(?i)\bassistant\b→speaker_b`、`\bI\b→speaker_b`(官方 :105-113)。
     非 locomo benchmark(真 user/assistant 身份)formatted_memory 维持
     现状文本,不引入映射。
  4. native prompt_messages:R6 资产化的官方 answer prompt 本就带
     speaker 占位(system 角色扮演),运行时用同一份映射填充。
  历史记录:上版 R1(content 前缀 `{speaker}: {text}`)**作废**——前缀会
  进抽取/摘要/embedding 改变方法内部行为;官方自己就是"槽位隐含身份+
  出口拼名字",无须发明。"只喂 user_input 侧+改 STM→MTM 闸口"方案
  维持驳回(third_party 算法红线、assistant KB 恒空、画像混一)。
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

- **R7 image 注入口径(2026-07-14 三次对峙后改判,用户方案胜出)**:
  **image→文本=数据表示问题,框架级统一,同一把尺子**(与 unified
  prompt 同哲学;改判依据:多数 method 无 locomo image 官方姿势可抄,
  框架默认不可避免,默认取语义最优——"sharing"准确表达对话中图片的
  分享行为)。统一格式=**`[Sharing image that shows: {caption}]`**
  (恰为 mem0 官方 blip-only 分支原文,`memory-benchmarks/benchmarks/
  locomo/run.py` session_to_chunks;mem0 零偏差);**`query` 字段全局
  禁用**(数据构造副产物,非对话可观测内容)。落地:
  1. 新建共享 helper(建议 `src/memory_benchmark/methods/image_text.py`,
     函数如 `turn_text_with_images(turn) -> str`:text 与逐图
     `[Sharing image that shows: {caption}]` 以空格拼接,无 caption 的
     图跳过,纯图 turn 允许只有 photo_tag;中文 docstring+独立测试);
  2. memoryos ingest(R1 第 1 点)改用该 helper——**不用官方
     `(image description:...)` 格式**,该处与官方 eval 的偏差在 note 与
     native bundle 注释里声明;
  3. mem0/lightmem 改造=解冻件,后续用同一 helper(不在本卡,已登记)。

## 2. 施工顺序建议
①R1(裸文本确认+speaker_map 持久化+出口映射三处:page 拼法/三正则/
image 官方格式)+既有测试调整;②R4 sidecar+items+注册声明;③R5 标记;
④R6 prompts 资产+bundle+parity 锁(角色扮演 system 的 speaker 占位
运行时填充);⑤新老测试全绿(出口映射需 locomo 与非 locomo 双形态测试)。

## 3. 完成门
目标测试+compileall 全绿(报数字);note=裁决执行记录+锚表+native 偏差
声明。主树全量与文档标准复查归架构师验收。

## 4.5 停工裁决①（2026-07-14,judge_profile 结构门,actor 停工正确）

**裁决:`judge_profile` 允许 `None`(显式哨兵=该 method 无 native judge
资产),消费端 None 时回落框架默认 judge。禁 fail-fast。**
理由:judge 是 benchmark 的尺子不是 method 的资产——method 没有自己的
judge,native run 就用与 unified 同一把框架尺子评(与 R7"无官方姿势→
框架默认"同一逻辑);fail-fast 会让 memoryos native 格评不出 judge 数字,
错。实施:
1. `ConfigTrackBundle.judge_profile` 类型改为
   `LightMemNativeJudgeProfile | Mem0NativeJudgeProfile | None`,
   memoryos bundle 显式传 None(带注释:官方评测=本地 F1 无 judge);
2. **允许清单追加 `src/memory_benchmark/cli/commands.py`**(仅 judge
   覆盖分支,M5 锚 :213-222):bundle 存在但 `judge_profile is None` 时
   跳过覆盖,保持 `create_evaluator` 默认实例;
3. 测试:memoryos native manifest + locomo-judge 走默认 judge 不崩;
   lightmem/mem0 既有 bundle 覆盖行为不回归;
4. lme/beam native judge 路由缺口(mem0 R0 前置包)不在本卡,不要顺手修。

## 4. 停工条件
- ~~ConfigTrackBundle 无法表达"无 native judge"~~（已由 §4.5 裁决解除）;
- page 文本反查出现无法无损映射的形态(如 pypi 改写 page 文本导致反查
  失配)→停工报形态,禁模糊匹配。

## 施工报告（actor 填写）
（待填）
