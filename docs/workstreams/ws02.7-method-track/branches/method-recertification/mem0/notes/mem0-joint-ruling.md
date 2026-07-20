# Mem0 current-main 六线联合裁决

> 状态：架构师裁决已落盘，生产修复尚未施工；本文件取代六份 preflight 各自的局部
> `READY/BLOCKED` 作为 Mem0 下一步唯一口径。六份原 note 保留一手探针和历史判词，不能把
> 单格 `READY_FOR_JOINT_RULING` 误读为可跑真实 smoke。

## 1. 合流证据与总判词

六份 Sonnet 5 docs-only 审计已由架构师逐份核对文件边界、关键源码锚、互相矛盾处和
`git diff --check`，并线性进入 main：

| 审计 | actor commit | main commit | 联合验收结论 |
|---|---|---|---|
| 产品 messages/namespace/time | `d77855c` | `40e82ac` | core 接受任意合法 role 序列；缺 role/content 才 fail-fast |
| LoCoMo | `59eb0e0` | `74379e6` | caption 裸拼阻塞；另有显式 speaker 映射漏项 |
| LongMemEval | `c80f559` | `7d0aeb6` | 输入可达；角色文本重复、blank/order 与官方脚本差异待裁 |
| MemBench | `04ced63` | `a3a84bc` | singleton 可达；native readout profile 被误标为 LongMemEval |
| BEAM | `d1e3ad1` | `e5139a0` | role-aware pair/singleton 可达；不照抄官方异常窗口的 positional 错配 |
| HaluMem | `4a8c572` | `73b4791` | 单趟交错语义可达；Mem0 update 检索请求与 failed-ingest resume 仍有缺口 |

**总判词：`BLOCKED_ON_TWO_CODE_CARDS`。**Mem0 不需要 placeholder；当前真正阻塞 B11 的是：

1. Mem0 输入/readout 保真：LoCoMo role 映射、caption wrapper、role-native benchmark 的重复
   文本前缀、MemBench prompt-profile 误标；
2. HaluMem operation runner：failed-ingest clean retry；Mem0 自身另需忠实执行其官方
   update probe 的 `top_k=10` 请求。二者不能再伪装成同一项 method-neutral 修复。

两批修改文件不重叠，可以在两个隔离 worktree 并行。两批强验收、合流门和全量门关闭前，
不得生成 Mem0 真实 smoke 命令，更不得写 frozen。

## 2. 中心裁决：role-aware 不等于 pair-required

OpenCode 引用的三段代码事实成立：默认 V3 `ADDITIVE_EXTRACTION_PROMPT` 明确区分 user 与
assistant 的抽取语义；`Memory.add()` 默认把 `parse_messages(messages)` 交给这套 prompt；
`parse_messages()` 把每条合法消息渲染成 `user:`/`assistant:` 前缀。由此只能推出：

> **Mem0 的 extraction 是 role-aware，输入应是带合法 role 的 conversation fragment。**

不能推出“每次 `add()` 必须同时含 user+assistant”或“消息数必须为偶数”。一手反证是：

- current-main LoCoMo harness 的 `CHUNK_SIZE=1`，官方自己逐条提交 singleton user 或 singleton
  assistant；
- 默认 prompt 写的是 current conversation `turn(s)`；
- core 不校验 role 交替、首条必须 user、偶数长度或 pair 完整性；assistant-first、连续同 role、
  singleton、odd tail 均能进入同一 V3 pipeline；
- `parse_messages()` 要求每条消息有 role/content 键并识别 system/user/assistant，但不会因为
  另一侧缺失而报错；项目 adapter 仍只发当前已声明的 user/assistant，不借本轮扩 role 集合。

因此 **MemBench ThirdAgent 的每条第三人称 observation 保持 singleton user add，绝不补
placeholder**。FirstAgent 也保持两个 canonical child 分别 turn add；不要为了“看起来像对话”
把它强改为 pair。LoCoMo current-main 同样保持逐 turn add。BEAM 已注册为 pair，但真实 dangling
tail 仍作为 singleton add，不补另一侧。

空 placeholder 也不是免费操作：它会进入 `parse_messages`/last-message/embedding/extraction
上下文；非空的 “I get it!” 更是在 benchmark 中制造从未发生的 assistant 发言。两者都会改变
被测 method，违反无损输入与私有事实边界。**占位只适用于接口结构上硬性要求 pair 的 method，
不能因为 prompt 描述了 user/assistant 就泛化到 Mem0。**

另一个边界也要锁住：一次 `add([user, assistant])` 与两次
`add([user]); add([assistant])` 不是算法等价变换。后一次调用会看到已有记忆/last messages，
事实抽取批边界也不同。`consume_granularity` 是 method×benchmark 的公开 build identity，不能
为了统一外观擅自改写。

## 3. 五格输入裁决

| benchmark | 投递粒度 | role/content 裁决 | 时间与图片 | metric 资格 |
|---|---|---|---|---|
| LoCoMo | `turn` | 单 namespace；`speaker_a=user`、`speaker_b=assistant` 取自 conversation metadata，不按首现猜；content 保留真实 speaker name 前缀 | `turn→session→None` 折入 content；caption 用共享 `[Sharing image that shows: …]` | Recall valid/turn；ranking pending |
| LongMemEval | `session` | canonical blank 逐条跳过后按现有 position chunk；结构化 role 直接进 message role，content 不再重复 `user:`/`assistant:` | 保持 raw haystack 顺序；同 session time 只折入一次 | Recall valid/session；rank pending |
| MemBench | `turn` | FirstAgent 两 child 各自 singleton；ThirdAgent singleton user；全部无 placeholder；content 保留原始 place/time | 内嵌 time marker 阻止重复 header；缺时保持 None，question time 永不进 ingest | Recall valid/turn；choice/source 可测；ranking pending |
| BEAM | `pair` | 正常 user→assistant 一批；dangling tail singleton；不跨 session、不造 placeholder | source time 按现有有效值折入；缺时保持 None | Recall N/A（pair lineage 不能冒充单 message qrel）；rubric judge 可测 |
| HaluMem | `session` | 整 session 一次 add；结构化 role 保留，content 不重复 role 文本 | 每 session add 返回只作当前 session extraction report；长期 store 保留 | extraction/update/QA 可测；retrieval Recall/NDCG N/A |

### 3.1 LoCoMo 显式 speaker 映射勘误

preflight 只写“按首现与 `speaker_a/b` 通常一致”，证据不够。架构师对 source-locked
`locomo10.json` 独立复算：10 个 conversation 中，整个 conversation 第一条来自
`speaker_a` 的只有 **4/10**；其余 **6/10** 先由 `speaker_b` 发言。当前
`_build_speaker_roles()` 的 first-seen 算法会在这 6 个 conversation 把官方角色整体翻转。
生产修复必须从公开 `Conversation.metadata["speaker_a"/"speaker_b"]` 构造映射，并对缺失、
空白、相同 speaker 或出现第三个未声明 speaker fail-fast；不得静默回到首现猜测。

current-main 官方独立 benchmark 仓库（核验时 HEAD=`4b61c5d3`）采用单 namespace、
`speaker_a=user/speaker_b=assistant`、`CHUNK_SIZE=1`。Mem0 主仓（核验时
HEAD=`9383e9a2`）仍保留论文 harness 的双 namespace/双视角实现，但后者还绑定
`MemoryClient(version="v2")`、只从 user role 抽取的 custom instruction、双份写入和双路检索
融合。它不是“同一实现换一组 TOML 参数”，而是另一条存储/检索算法流；若未来复现，只能作为
显式 implementation variant 单独接入，不能混入统一主配置，也不能只挂一个
`author_locomo` section 假装完成复现。当前 vendored `mem0/configs/prompts.py` 与核验时最新
upstream 文件 SHA-256 同为 `10bc8a34…a5c`；V3 prompt 已明确从两侧 role 抽取，并专门说明
assistant role 可承载具名真实 speaker 的个人事实，故旧双库的 user-only 补偿理由不再成立。

### 3.2 caption 计数勘误

LoCoMo 共 **1,226 个带 caption 的 turn**，其中 **316 个 caption 没有 URL**；316 是 1,226
的子集，不是另一批 316 个“独立路径命中”。当前真实数据无 caption-only/multi-caption，仍要
用合成强反例锁住共享 helper 的通用契约。也不能写“每次 smoke 都会命中 caption”：是否命中
取决于裁剪位置。修复有效性由确定性测试承重，真实 smoke 只验证选中样本的实际路径。

### 3.3 LongMemEval 差异裁决

- **blank**：保留 canonical 的逐条 skip，再对 survivor 作确定性 chunk；不照抄官方脚本
  “pair 任一侧 blank 就整 pair 丢弃”的 collateral data loss，也不补 placeholder。
- **order**：保留 raw haystack order。官方脚本按完整 HH:MM 重排，与项目已经稳定记录的
  LongMemEval 日内时间不可靠事实冲突；不能为追脚本表象重写 source order。
- **content**：role 已经是结构化 message 字段，正文再前置 `user:`/`assistant:` 只会让 LLM
  实际看到 `user: user: ...`；这是 method adapter 的重复渲染，应删除。

这两项 blank/order 属诚实披露的 framework normalization，不声称逐字复现官方 harness；但比
丢真实内容或依赖不可靠时钟更符合 benchmark source contract。

### 3.4 MemBench 与 BEAM 差异裁决

MemBench 所有问题带 question time 不能成为“它是 LongMemEval”的启发式证据。已知
`benchmark_name="membench"` 时，native sanity readout 必须显式写 `generic`；只有旧调用确实
没有 benchmark identity 时，才允许保留启发式兼容。主 unified answer builder 继续用
MemBench 官方 question time；该时间只进 answer prompt，不进 memory build。

BEAM 官方 REST harness 对 10M 两个异常窗口做纯 positional chunking，会把两个 user 塞进一批，
再把 assistant 与下一条无关 user 错配。框架保持 role-anchored pair + dangling singleton，标为
product-compatible extension；不能为了“native”复制数据错位。BEAM rubric 主分数的 float 路径
已存在并有回归，本轮不重开已关闭的 int 截断问题。

## 4. HaluMem 共享 runner 裁决

### 4.1 update retrieval window：撤销“全 method 强截 top-10”旧判

前一版把 `eval_memzero.py` 的 `top_k=10` 误升格成 HaluMem scorer 的 method-neutral 硬契约，
现按一手源码改判：

- Mem0、Mem0-Graph、Supermemory、MemOS、Zep 等官方 wrapper 的 update 调用确实请求
  `top_k=10`；
- 但 Memobase 官方 wrapper 用 `max_token_size=250`，没有 top-k；
- 共享 `evaluation.py` 只检查 `memories_from_system` 非空并把其内容换行拼接进 update judge，
  不检查条目数、top-k 或排序。

因此 **10 是 Mem0 等 wrapper 的检索窗口选择，不是 update scorer 的普适公式**。共享 runner
继续发出 `RetrievalQuery(purpose="memory_update_probe", top_k=10)`，其含义是 benchmark 的
请求与审计事实；但 runner 不得把所有 provider 的结构化 items 强截为 10，更不得把 opaque
`formatted_memory` 按行假装成 memory items 后截断。对不同 method 分三层处理：

1. 产品接口原生支持 top-k/limit：adapter 应在不改变其他 purpose 的前提下忠实执行请求，并
   记录实际窗口；当前 Mem0 属此类，本轮只让 `memory_update_probe` 使用 `query.top_k=10`，
   普通 QA/其他 benchmark 仍守 TOML product profile；
2. 无 top-k 但能返回原生有边界的 memory list 或 token-budget context：保留 method 原生窗口，
   如实声明 `method_native_window`，仍可做 HaluMem update，但不是 Mem0-wrapper parity；
3. 没有可分离 retrieve，或只能从 answer 黑盒猜 memory：update metric = N/A。Extraction、QA
   资格仍独立判，不能因一项 N/A 抹掉另外两项。

`items=None` 的 formatted readout 只能作为完整 opaque context 使用；除非 method adapter 自己能
证明条目边界，否则共享层不拆行、不重排、不去重。若将来要比较统一 item cap 或 token cap，
必须另立带 identity 的 framework profile，不能借本次 Mem0 修复暗改十个 method。

### 4.2 failed-ingest clean retry

当前 operation runner 在 conversation 中途异常时既不写 `failed_ingest`，resume 又会从 session 1
直接重放；CLI 已绑定 method clean hook，却只传给标准 runner。裁决：

1. operation runner 接收同型 `clean_failed_ingest_conversation`；
2. 任一 session ingest/extraction/update/QA/end-conversation 在公开 artifact 完整提交前抛错，立即
   记录 `failed_ingest`、stage/error/`ingested=False` 并 re-raise；
3. resume 默认跳过失败 conversation；显式 retry 且有 hook 时，先用 public conversation 清理
   namespace，再置 pending 后从头跑；显式 retry 但无 hook 必须 fail-closed；
4. completed conversation 继续跳过，clean hook 绝不能碰 gold/evidence；
5. 复用标准 runner 已有 helper/状态语义，禁止复制出第二套近似状态机。

operation-level artifacts 只在整个 conversation 成功后落盘，因此失败进程内的半截 report/probe/
answer list 不得写入；clean retry 后重新生成一份完整记录。

## 5. 两张施工卡与关闭条件

1. `cards/actor-prompt-mem0-input-readout-r1.md`：只改 Mem0 adapter、相关 tests、integration
   文档；版本必须 bump，五格旧 memory build 不可 resume。
2. `cards/actor-prompt-halumem-operation-runner-clean-retry-r1.md`：只改共享 operation runner、
   CLI 接线与 runner tests，关闭 failed-ingest clean retry；不再做通用 top-10 截断。

关闭顺序：两卡可并行施工 → 架构师 full diff/强反例复跑 → 线性合流 → 扩大定向门 → 主树
全量 pytest + compileall → 为 Mem0 五格逐格生成最小真实 smoke 命令 → artifact 开箱 → B11
对表 → `method-frozen-*`。真实 API 的预算、规模和 run id 仍逐格由用户批准。
