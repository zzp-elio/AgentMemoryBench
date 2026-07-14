---
id: ws02.7
parent: ws02
status: in-progress（Method Track M0 启动；benchmark 侧五家已 frozen-v1 + B6 完成）
created: 2026-07-12
---
# ws02.7 Method Track M0（method 侧解冻后逐个接入）

benchmark 侧五家 frozen-v1 + B6 横向总验收完成（ws02.6，2026-07-12），
method 侧解冻。本 workstream 按 `docs/reference/method-integration-checklist.md`
的 B1-B11 标准，逐个 method 审查 + 双轨接入 + 极小 smoke。

**接入顺序（用户 2026-07-12 拍板）**：LightMem 首（外部校准器，原则 #16）
→ 其余按 method-interface-inventory 排 → **EverOS 最后**。

## 当前断点（2026-07-14）

- 2026-07-14（**M3-mem0 + M0-13 验收合入（1153 passed）+ timestamp
  Platform-only 疑问结案**，Fable 5，批处理回合）：① **M3 ff 合入**
  （37640ef）：Phase A 硬答案=官方三套 benchmark 的 answer 上下文**全带
  时间**、读取字段均为 `created_at`（locomo 渲染 `(weekday, Month DD,
  YYYY)`/lme 按日期分组标题/beam `[YYYY-MM-DD]` 前缀）,其值=ingest 时
  显式传入的对话 epoch;修复=adapter 边界把 metadata 对话时间提升进
  created_at 槽（session_time→first_turn_time→turn_time→timestamp→
  created_at 回落链+timestamp_source 标记,墙钟另存 storage_created_at）,
  formatted_memory 取旧论文 `- {timestamp}: {memory}` 格式、无时间行为
  字节不变,reader prompt v2→v3。② **M0-13 cherry-pick 合入**（c5ba750）：
  op-level 复用 `_method_manifest_with_protocol` 盖章 +
  `_manifests_match_for_resume` 兼容旧 halumem run;真实复证挂账=下次
  halumem predict 后抽 manifest。**主树 1153 passed（基线+2）;文档标准
  盲点第四例未出现（两卡新函数全带中文 docstring,actor 已内化）。**
  ③ **timestamp 疑问结案（用户带 GPT 调查来问）**：GPT 方向正确且比其
  结论更彻底——OSS Python `Memory.add()` 无 timestamp 参数
  （mem0/memory/main.py:573 签名实锚）;**OSS REST server 的 MemoryCreate
  schema 也无该字段（server/main.py:178-187）→ 官方 harness OSS 模式发的
  timestamp 被 Pydantic 静默丢弃,真正消费它的只有 Cloud V3**
  （mem0_client.py:189-191 注释自证）——即官方 OSS 模式自己也丢对话时间,
  **登记 upstream issue 候选第 3 件**。我们的解=add 侧对话时间进
  metadata（OSS add 原生支持,M2 已在）+ M3 检索侧提升,零 third_party
  diff 达成官方 Cloud/论文语义,比官方 OSS 模式更完整。④ s2 五格
  predict 命令交用户（复证 M3 时间口径 + halumem manifest 盖章）;付费评
  按既定序推迟到 s2 后一次性做。⑤ assembly-line §五回填中期校准数
  （架构师批处理回合 5/计划 ≤6,意外 3 件均在缓冲带宽内）。
- 2026-07-14（**mem0 五格 predict 全通 + 开箱验收三发现 + 全框架首个非零
  recall**，Fable 5）：① 五格 predict 零报错,但**开箱验货**（playbook #22
  新原则,用户拍板"稳扎稳打"落档）查出三处:(a) **lme/beam 空检索结案=
  官方语义**——store 层验尸(sidecar 有记忆+qdrant 点在+run_id 匹配+自查
  filter 命中 score=1.0)→ 根因=mem0 `_search_vector_store` 把 threshold=
  None 强制回落 **0.1 相关性门槛**（main.py:1343-1346),官方 harness 同样
  不传 threshold=同姿势,声明性语义非缺陷;locomo 空=抽取真 0 条(sidecar
  空,诚实);(b) **B4 真缺陷**:formatted_memory 无对话时间,
  item.timestamp=实验墙钟 created_at,而 payload 里 session_time 明明在,
  规范化丢弃——**M3-mem0 卡写就**（先取证官方上下文时间口径再修,禁自造
  格式）;(c) **operation-level manifest 不盖 provenance 章**（M0-10 只修了
  generic 路径)——**M0-13 小卡写就**。② **免费评九项落盘**：
  **membench-recall=0.167(n=4)=全框架首个非零 recall,sidecar 首战即中**;
  membench choice/source 0.5;locomo f1 0.4/recall 0.0(n=1 真实);lme
  recall/rank 0.0(n=1);beam-recall n=0——**beam 与 lme evaluator 对
  "空检索问题"计数语义不一致(n=0 vs n=1),登记待查**。③ **UserWarning
  结案**：qdrant 本地模式 payload index 无效告警——replay 实证无索引时
  filter 仍正确生效(自查命中),纯性能层提示,零正确性影响,不动。
  ④ 日志全归位(9 份 evaluate 进 run 目录,5 份 predict 从 staging 搬入)。
  ⑤ 待办:M3+M0-13 可并行派(文件不相交);付费评命令交用户(locomo-judge/
  lme-judge/beam-rubric-judge×2 + halumem 三件+memory-type 后评)。
- 2026-07-14（**🧊 LightMem method-frozen-v1 + M2-mem0 验收合入（1151
  passed）**，Fable 5，批处理回合）：① **M2 通过 ff 合入**（559d7c9）：
  BEAM→pair、halumem→整 session 单次 add（判别键=session_memory_report
  旗）、clean hook 三件套（delete_all+新 third_party `delete_messages`+
  sidecar 清除,scope 格式 `run_id=<key>` 一手锚 `_build_session_scope`）、
  provenance sidecar（原子写+schema 校验+旧 state fail-fast）;**偏差接受
  并留观察项**：检索命中缺 sidecar 映射=fail-fast（严于 M1 §4 的逐项回落,
  真实 smoke 若绊住再放宽为回落+计数）。架构师补一行 docstring（worktree
  盲点第三例）→ 主树 **1151 passed**。upstream PR 素材第二件已备
  （m2 note §4）。② **LightMem 冻结**：B2/B4/B8/B11 收口（B8=检索纯读
  锚死 lightmem.py:648-710;B4 带 lme 无非零样本例外声明）,
  `notes/lightmem-frozen-v1.md` 落档（冻结语义+七项声明缺口）,status 总表
  LightMem 行全绿 method-frozen=**v1**;mem0 行同步（B1 🟡 upstream commit
  待溯）。③ **scope 命名答复（用户问为啥不是 conversation_scope）**：
  `session_scope` 是 mem0 messages 表自己的列名（storage.py schema）,
  第三方 diff 须随上游命名以利 PR;我们塞进去的值=isolation_key（=隔离
  空间级）,删的正是隔离空间,名与实的错位来自 mem0 的词汇表不是我们的。
  ④ 下一步:mem0 五格 smoke 命令交用户（`mem0-<bench>-unified-s1` 系列）。
- 2026-07-14（**M1-mem0 取证验收合入 + 六项裁决 + M2-mem0 施工卡写就**，
  Fable 5）：① M1 note 验收=流水线首张标准取证卡,质量标杆（七节硬答案+
  严格反证）。② **裁决 R1-R6**：native 注册面=locomo/lme/beam
  （memory-benchmarks harness;membench/halumem 无 native 格）;**当前
  harness answer/judge 默认 gpt-5→第一阶段不做其榜单校准复现,旧论文
  LoCoMo 路径（4o-mini）=未来校准候选**;B2 修 BEAM(turn→官方 2-turn
  chunk)+HaluMem(切块→整 session 一次 add),locomo/lme 已对齐不动;
  **B3=保留 worker 内逻辑隔离**（run_id namespacing 是官方复现自身姿势=
  方法身份,mem0 无本地大模型物理化收益小）,"清得干净"缺口走第二个
  B5+ third_party 最小 diff（SQLiteManager 增 `delete_messages(session_scope)`
  纯新增 API）+clean hook 挂接+污染场景测试;补生产 Qdrant 零 API 泄漏
  测试;并行维持 worker 间物理;history tombstone 声明无害;B5=id 映射
  sidecar 按 M1 §4 原案;B6=五格零 flush;**capability 枚举缺 session-report
  项=框架 backlog**（registry 无法静态拒绝,不阻运行,另立小卡）。
  ③ **M2-mem0 施工卡写就待派**（B2×2+B3 修复+B5 sidecar+测试,含批准的
  第二个 third_party diff）。④ **upstream 更新焦虑答复（用户问 mem0 官方
  repo 持续更新咋办）**：vendored 快照无嵌套 .git,source_identity=package
  version+文件列表+聚合 SHA-256（mem0_adapter.py:203-217）=内容寻址版本锁,
  上游更新与我们无关;**唯一遗留=快照的上游 commit 来源待溯**,请用户
  提供当初下载的 release/commit 号,提供不了则声明 content-hash 为准;
  接入顺序不因更新频率改变。
- 2026-07-14（**流水线文档落成 + M1-mem0 取证卡写就 + 额度战略**，Fable 5，
  用户周额度已用 54%）：① **`docs/reference/method-onboarding-assembly-line.md`
  新建**：LightMem M0 蒸馏——一次性资产白嫖清单（协议/provenance 链/
  halumem 样板/容忍变体/五件套判据/纪律件）、方法论泛化四则（B6=镜像官方
  复现脚本;B2=抄官方 wrapper 喂法;B9=模型统一;B3=逻辑隔离须过等价性
  三项）、标准卡序（M-1 取证→裁决→M-2 施工→验收→五格 smoke→frozen,
  架构师动作/method ≤6）、额度经济学（9×~4%+14% 缓冲;**mem0=二号煎饼
  校准 run,计量外推,超预算先报告不闷头烧**）。② **M1-mem0 取证卡待派**
  （零生产代码;核心=逻辑隔离等价性三项取证（用户点名,B8 clean-retry 缺口
  并案）+ B5 id-sidecar 落点 + halumem end_session 差距清单）。③ **halumem
  full 并行化设计裁决=继续缓行**：设计必要性取决于 cost-probe 的串行
  wall-clock 数字,full 本身在预算门后,预算批复前设计=可能白干的架构师
  额度。④ 用户战略拍板落档：**剩余 ~50% 周额度目标=接完其余 9 method**;
  frozen-v1 专场仍是 LightMem 收尾件（B2/B4/B8 🟡 收口）,可与 mem0 M-1
  并行推进（互不动同文件）。
- 2026-07-14（**🏁 LightMem 五格通关**（halumem ② 四指标收口）+ 三问答复
  落档，Fable 5）：① **通关达成**：halumem 四指标全落盘（extraction 0.0/108、
  update 0/7、qa **1.0**（Memory Boundary 题不知为不知=真金）、memory-type
  0.0/3;score 记录逐条核过=真实测量,judge 实读捕获记忆）,B11 smoke 半场
  五格全绿（详 lightmem.md B11 ⑧）。**下一件事=frozen-v1 note 专场**
  （B2/B4/B8 残留 🟡 收口核对 + 声明缺口清单：真实 resume 缓期/native build
  profile 未实现/halumem ⑤ N/A/op-level 并行化待设计）。② **@k 前缀答复
  （用户问）**：可行且已是现役做法——longmemeval-retrieval-rank 就是单次
  检索排序的离线前缀评（k∈[1,3,5,10,30,50]，3000 例官方零失配）;顺序不变
  是天然的（评测不重跑检索,只切一次落盘的有序 items）;**唯一预算前置=
  predict 时 top_k ≥ 未来最大 k**;真排序是前提,LLM 重组散文式记忆的
  method 对 @k = N/A（provenance items 为 ordered tuple 的原因）。
  ③ **smoke evaluate 精准性答复**：结构性保证——裁剪在 predict 前的
  Dataset 层,gold 与 prediction 是同一次裁剪的双生子同落 run 目录
  （private labels），evaluate artifact-only 按 id join,从不回原始数据集
  找子集。④ **命名瑕疵登记**：evaluate summary 的 total_questions/
  correct_count 对非 QA 指标是术语复用（extraction 的"question"=gold memory
  point,update 的=probe;correct_count=null=非二值指标）——cosmetic
  backlog（total_items 更贴切）,不动行为。⑤ **op-level 并行保障线**：
  halumem full 今天结构上只能串行（CLI+runner 双层硬校验）,不存在未冒烟
  并行进 full 的可能;将来立 op-level 并行化设计卡时,M0-12 固定 2-user
  形状复活为该设计的验收件;是否做,等 cost-probe 给出串行 wall-clock 再定。
- 2026-07-14（**M0-10 验收合入（1143 passed）+ M0-12 停工裁决（⑤=N/A）+
  halumem s2 流通 + 三项用户拍板落档**，Fable 5）：① **M0-10 通过 ff 合入**
  （e0af293）：MethodRegistration 加可选 provenance_granularity（LightMem=
  "turn"），并行协调路径按 system_factory 身份静态解析盖章，实例回退与
  fail-fast 保持;resume 兼容有测试钉死。实况修正：并行路径 system 实为
  `_UnusedRootSystem` sentinel 非字面 None，根因不变。**真实复证挂账：下一次
  任意 workers>1 predict 后 manifest 抽查**（lme par2 recall 假阴性平反同步）。
  ② **M0-12 停工裁决（卡 §5 已写）**：operation-level runner 设计上单
  worker（入口硬校验+串行循环）→ **halumem 五件套⑤=N/A（声明）**;
  operation-level 并行化=full 阶段前独立设计项。actor 停工 note=教科书级
  （1 分钟精准停工+完整证据链）。③ **halumem s2 predict 流通**（M0-11 解封
  后）：五件套①③④已验（详录 lightmem.md B11 ⑦），session report 真实数据
  首秀（s4 捕 3 条 ok/s1-s3 empty 如实）;**评测依赖序实锤：memory-type
  （免费合成指标）必须后于 halumem-extraction+update**——付费三项命令已交
  用户，跑完架构师补评 memory-type =通关线。④ **用户拍板×3 落档**：
  (a) native answer/judge **模型不 native**（第一阶段只复现官方结果本就是
  gpt-4o-mini 的实验;模型 native 留未来）;(b) hook 已装
  （`.claude/settings.json` PreToolUse/Bash：git commit 时注入 §14+显式路径
  提醒，管道实测双向通过）;(c) 派发经济学+actor"新人标准"入 playbook
  #20/#21。⑤ **隔离 id 映射裁决（用户提议序号别名）**：产物/checkpoint 层
  **不做映射**——原始 conversation_id 是 resume 键、跨 artifact join 键、
  provenance id 空间的载体,二套命名=对账事故温床;**展示层可加序号**
  （progress/summary 顺带 conversation_index），登记低优先 UX 项,不阻通关。
- 2026-07-14（**M0-11 验收合入（1139 passed）+ offline_update 覆盖面核证 +
  TOML 双轨归属核证 + playbook #20**，Fable 5）：① **M0-11 通过 ff 合入**
  （77ec269,actor 5min 交卡）：collector 容忍变体在 question scope 委托原
  严格方法（等价性测试逐字段断言）,五处机械替换,operation-level 回归测试
  真实走 update probe 路径。架构师补一行嵌套 helper 中文 docstring
  （文档标准测试不在 actor 定向范围,worktree 盲点又一例）→ **主树权威复跑
  1139 passed 全绿**;worktree/分支已清。**s1 现在解封,用户可重跑（换新
  run_id 避开残留 run 目录）**。② **offline_update 覆盖面核证（用户追问
  问出来的,结论=无缺口,姿态是官方镜像）**：locomo 官方主流程集成
  offline update（add_locomo.py:445-451,官方 0.9 论文值）,lme 官方主管线
  **不含**（run_lightmem_gpt.py=complete pipeline;offline_update.py=官方
  自称 utility script 演示件）→ 我们 locomo 跑/lme 不跑=镜像官方;
  membench/beam 无官方实验采 lme 轻姿态;已写进 lightmem.md B2。
  ③ **TOML 双轨归属核证**：configs/methods/lightmem.toml 头注释即证据
  （ws02.5 方案 B:extract 0.5/offline 0.8 = repo 默认,旧 paper 硬编码
  0.1/0.9 已弃用;retrieve_limit=60 是 LoCoMo 报告口径=混合,留档
  method-interface-inventory）;native bundle 显式声明
  hyperparam_ref="lightmem.repo_default"（config_track.py:45-46）→ 已跑的
  native run = 口径面 native + build 面 repo 默认,**声明过的缺口非疏漏**。
  ④ playbook **#20 派发经济学**落盘（用户叮嘱:必留=裁决/强验收/跨切面
  设计,其余写卡派出）。⑤ hook 机械化提案待用户拍板（commit 前 §14 三问
  提醒 hook,见会话讨论）。
- 2026-07-14（**halumem smoke 双失败取证 + M0-11/M0-12 双卡写就 + 双轨政策
  议程登记**，Fable 5，压缩后新会话）：① **s1 失败根因实锤（M0-11 卡待派，
  通关线阻塞项）**：halumem 走 operation-level runner，update probe 在
  conversation scope 内调 retrieve（operation_level.py:364-374），而 LightMem
  adapter `_retrieve_question` 无条件 `record_retrieval_result`（question-scope
  专用断言，adapter:844-851 → collector.py:437-441）→ 崩。**跨 method 通用
  陷阱**：amem:490/memoryos:790/mem0:902,981 同姿势,谁上 halumem 谁炸。裁决=
  collector 新增 scope 容忍变体 + 五处机械替换（卡 §2，runner 编排不动）。
  ② **par2 拒绝 = 固定形状 by design（用户设计正确）**；裁决=不开放自由裁剪，
  增加**第二个固定形状**（workers>1 → 恰好前 2 user，M0-12 卡写就,前置
  M0-11 合入）。③ **halumem × offline_update 姿态裁决已进 lightmem.md B2**：
  offline_update 只在 locomo 路径跑（adapter:512/:668 有 `_is_native_locomo`
  守卫）,halumem 不跑=在线姿态测量,声明语义非缺陷（逐 session 全库 update =
  O(n²) 且更失真）。④ **extraction 精准性复核（用户三问三答）**：捕获窗口=
  恰好一次 add_memory 调用（adapter:579-585）,两端 force 刷洗保证 buffer 空;
  session 超 buffer 阈值 → 该次调用内部自然多轮抽取仍在窗口内,不足 → force
  兜底,两向不多不少。⑤ **双轨政策议程登记（用户 2026-07-14 提出,待办勿忘）**：
  (a) native answer/judge **模型**是否 native（simplemem 论文用 gpt-4.1/4o）——
  架构师建议=模型统一、参数/prompt native,论文数字校准是第三种一次性用途
  （lightmem 校准先例）,**待用户拍板**; (b) simplemem native 范围=仓库有啥算
  啥（现状仅 locomo,默认 SimpleMem text 版）; (c) memoryos native=论文超参
  （作者说法）,adapter 现状待一手核对; (d) prompt 文件组织收敛
  （lightmem_native_prompts.py 在 methods/、judge prompt 在 evaluators/ 太平
  铺）→ 提议 `src/memory_benchmark/prompts/` 统一包,ws03 清理项; (e) evaluator
  可复用化（recall@k/llm-judge 去 per-benchmark 文件化）,ws03; (f) 根 README
  门面化更新,挂 LightMem 通关里程碑。⑥ **派发序**：M0-11 →合入→ 用户重跑
  s1 → M0-10（并行 manifest）→ M0-12 → par2 → halumem 五件套 → 通关。
- 2026-07-13（**M0-8 验收合入（1133 passed）+ lme ⑤ 收官 + M0-10 bug 卡**，
  Fable 5，用户额度 14%）：① **M0-8 通过**：SessionBatch ingest → 整 session
  一次 add_memory(force×2) → 只读旁听 `embedding_retriever.insert`（实例属性
  影子+finally 恢复）→ `end_session` pop 出 `SessionMemoryReport`（capture_status
  ok/empty 如实）；registry halumem 行 consume=session + session_memory_report
  旗。**精准性不变量**：每 session 末 force 刷洗 ⇒ buffer 永不跨 session ⇒
  捕获窗口=恰好本 session（不多不少），两 session 隔离有测试钉死。
  **halumem smoke 命令已交用户**（memory-type 免费架构师评；extraction/update/
  qa 付费）。② **lme par2 2/2 双 worker → lme 格⑤关闭**；f1 n=2 已评。
  ③ **发现框架 bug（M0-10 卡待派）**：workers>1 路径 manifest 不 stamp
  provenance_granularity（prediction.py:1209-1246 只在有 system 实例时写）→
  lme par2 的 recall n=0 是 manifest 缺键所致（artifacts 里 items 带合法
  source_turn_ids）；修复后需一次并行 run 复证。④ 日志已归档。
  **格局：locomo ✅ membench ✅ beam ✅ lme ✅ halumem 差 smoke 实跑 = 通关线。**
- 2026-07-13（**M0-9 验收合入（1130 passed）+ 架构师记录勘误**，Fable 5）：
  ① M0-9 结论核实为真：**M0-7b 当时已把两个消息构建器全部打上 external_id**
  （locomo 构建器 :1200,1208 + lme pair `_turn_to_role_message`:1263），v3
  turn/pair 复用这两个构建器 = 天然全覆盖；四个 recall 类 evaluator 契约
  逐家核查"确定对齐无 gap"。actor 因此**零生产代码改动**，只补测试（真实 id
  形态 "17"/"p1:s1:t1"/lme pair）+ 取证文档——纪律加分。② **勘误**：架构师
  此前断点与 integration-status 写"仅 locomo 路径附 id"是读 M0-7b diff 漏看
  后半截所致，已改正（status 页已更）；教训=验收读 diff 必须读完整,不许
  head 截断。③ **cost-probe 缓期（用户拍板）**：等 5 benchmark × 10 method
  全矩阵 smoke 跑通后再议。④ 下一步照序：用户跑 lme par2 → 派 M0-8。
- 2026-07-13（**通关冲刺：M0-8/M0-9 双卡写就，串行派发序定**，Fable 5，用户
  额度 23%）：目标=LightMem 五格通关。**派发序（两卡都动 adapter 必须串行）**：
  ① M0-9（小卡：external_id 铺开到 lme/membench/beam 注入路径 + 逐 benchmark
  recall evaluator 契约核查）→ 验收 → ② 用户跑 lme par2（`--conversations 2
  --workers 2`，一箭双雕：关 lme ⑤ + 点亮 lme provenance）→ ③ M0-8（halumem
  wrapper：session 注入+force 刷洗+只读捕获→SessionMemoryReport，方案已裁决，
  Phase C 必须钉死增量语义测试）→ 验收 → ④ halumem smoke 五件套 → 通关。
  **实验结果留档确认（用户关切）**：evaluate 是 artifact-only 设计——每 run 的
  predictions/answer_prompts(含 formatted_memory+retrieved_items+provenance)/
  private labels/answer_scores 全部落盘,未来接 BLEU 等新指标直接对旧 run 离线
  评,零 API 重跑;M0-7b 之后的 run 才带 provenance items（旧 run 无法回填）。
- 2026-07-13（**provenance 实验门通过 + beam 格五件套全齐（第三格）**，Fable 5）：
  ① **locomo-recall n=1 首次点亮**（lm-locomo-unified-prov1）：score=0.0 产物级
  核验=真实测量（source_turn_ids=[D1:2,D1:1,D1:2] vs evidence=[D1:3]，id 空间
  逐字对齐，检索未覆盖 D1:3）——**LightMem=首个 provenance 生产者**，upstream
  PR 素材+机制实证齐备；integration-status 横向事实已更新。② **beam ⑤ par2b
  2conv×2workers 2/2 通过** → beam 格五件套全齐；观察：par2b 终端/日志尾缺
  最终 JSON summary（artifacts 完整无损，疑 CLI 打印路径在 --conversations
  覆盖+workers 组合下的小 UX 问题，低优先待查）。③ 日志归档就位：三份 run 日志
  已入各自 run/terminal-logs/，staging 清空，失败残 log（datasets 事故一行）已
  核内容后删除。**格局：locomo ✅(+prov) membench ✅ beam ✅ lme 差⑤(随
  cost-probe) halumem 待 wrapper 施工。**
- 2026-07-13（**M0-7b 验收合入（首个 third_party diff 落地）+ datasets 依赖
  治本 + beam judge 双过**，Fable 5 强验收）：① **M0-7b 通过并 cherry-pick 合入**：
  external_id → `MemoryEntry.source_external_id`（可选默认 None，序列化条件写入
  仿 bam_tags）→ payload → `RetrievedItem.source_turn_ids`；平行列表与时间戳同
  循环构建保证索引一致；**all-or-nothing 语义**（任一命中缺 id 整次回落 none，
  不造部分 recall）；provenance_granularity="turn"；离线 locomo recall 合成验证
  n=1/score=1.0；**主树权威复跑 1128 passed**。当前只有 locomo 批次构建器附
  external_id（lme pair 等路径优雅回落 none，后续扩）。**真实 API 验证
  （locomo 新 predict → locomo-recall n>0）= upstream PR 前实验门,命令已交
  用户**。② **beam-rubric-judge 双 variant 0.1/0.1 落盘**（用户跑）→ beam 差
  ⑤（par2b 首跑因 datasets 被 uv sync 剪掉而失败——根因:从来不是声明依赖,
  beam.md 已知限制#7 的病根；已 `uv add datasets` 治本,命令重发）。
  ③ **tee 目录归属细化**（用户提议）：evaluate 日志直接进 run 目录,predict
  日志 staging→验收时架构师搬运（playbook #19 更新,beam 两份 judge 日志已
  归位示范）。④ 修复 lightmem.md B6 标题丢失（架构师前一日编辑事故,actor
  如实保留未越权修）。
- 2026-07-13（**BEAM smoke 双 variant 通过 + M0-7 停工裁决 + tee 日志纪律**，
  Fable 5）：① **BEAM smoke**：100k/10m predict 各 1/1、sentinel=0（用户跑）；
  免费评架构师跑完：100k f1=0.0 / 10m f1=0.4 / beam-recall 双双 n=0 条件 N/A
  正确 / par2 f1=0.4；效率+时间戳全绿——**100k 记忆时间戳 `15 March 2024` =
  M0-6 月名转换产物级端到端验证**。待办：beam-rubric-judge（付费,命令已给用户）；
  **⑤并行冒烟无效**（smoke 切片=1 conv,par2 第二个 worker 空转,架构师给命令时
  的失误）→ 补 `--conversations 2` 的 par2b。已知观察：transformers `531>512`
  截断警告（embedding 侧,产物无痕,全量前复查,tee 判例）。② **M0-7 Phase A
  正确停工**（sid 每 invocation 重置+buffer 跨调用）→ **裁决=方向 1 消息携带
  `external_id` 透传**（卡 §5 增补,边界 ≤~25 行,M0-7b 待派;上游 sid 多 batch
  不一致=issue 候选）。③ **playbook #19 tee 纪律**（用户提议:不再粘贴终端,
  命令预包 tee,架构师自读 outputs/terminal-logs/）+ #18 补 M0-6 actor 自发补
  资产judgment。**smoke 全局格局：locomo ✅ membench ✅ beam 差 judge+⑤(par2b)
  lme 差⑤ halumem 待 wrapper。**
- 2026-07-13（**M0-6 验收合入 → BEAM 解封 + M0-7 provenance 改造卡派出**，
  Fable 5 强验收）：① **M0-6 通过**：月名→ISO 通用转换（无 BEAM 分支名）、
  缺时 fail-fast 保持、真实数据扫过无单数日不造 fixture、测试直达官方
  normalizer；**主树权威复跑 1122 passed**（架构师在裸 worktree 复跑挂 73 个
  = gitignored 资产缺失假信号，判例入 playbook #18：代码卡权威测试门=合并后
  主树复跑，actor 只跑目标测试）。10m smoke 不触达全缺时 conv7/p1:s1、smoke
  切片最长 turn 694 tokens 无超长风险 → **BEAM 100k/10m 可进真实 smoke**
  （命令已交用户：两 variant 各一 run + 100k par2；beam-rubric-judge 付费=用户，
  f1/beam-recall 免费=架构师）；formal 缺时 session 政策仍待裁决。
  ② **B5+ recall@k 改造批准 + M0-7 卡派出**（LightMem source_id 透传，
  third_party 最小 diff 首例）：边界=可选字段默认 None（bam_tags 先例）、
  零行为变化可测表达、diff 留档做 upstream PR 素材；sid 语义取证前置；
  locomo-recall 契约对齐；无 API 测试链。真实 API 验证 = PR 前实验门。
  其余四家 adapter 层改造（策略②③①）仍按深耕制排 LightMem 之后。
- 2026-07-13（**membench 格五件套全齐（第二格）+ 逻辑隔离改造裁决=不做**，
  Fable 5）：用户跑 predict 两条（s1 4/4 + par2 4/4，sentinel=0，run_id 带
  `-0-10k` 后缀）；架构师跑免费五件套②③④：choice-accuracy 0.5 /
  source-accuracy 0.5 / recall n=0 条件 N/A 正确；效率三类齐（api_usage 实证、
  injected mean=108.25）；formatted_memory 4/4 带时间戳全真实记忆。
  **隔离裁决**（用户问）：membench 每 tid 一个物理隔离空间=是；LightMem 原生无
  namespace（MemoryEntry 字段表无此项、检索 filters=None）→ 逻辑隔离**不改造**
  （零评测能力收益+红线级存储改动；向量总量两种隔离相同，真实代价是 per-conv
  embedding 模型重载 ≈2s，full 若成瓶颈走 adapter 层 embedder 共享缓存，零
  third_party）。详见 lightmem.md B11⑤/B3 附带裁决。**当前格局：locomo ✅
  membench ✅ lme 差⑤ beam 卡 M0-6（未派）halumem 待 wrapper。**
- 2026-07-13（**M0-4/M0-5 双卡验收 + HaluMem "牵强"裁决落定 + M0-6 派发**，
  Fable 5 强验收）：两卡均 codex 自建 worktree（新规矩入 playbook #18：卡 §0 写
  自建命令模板，架构师验收核基点/范围/未 push 三项），ff+cherry-pick 线性合入。
  ① **M0-4 验收通过**（架构师独立复扫 BEAM 100K：90/5,732 非空 anchor、
  `April-02-2024` 格式，与 note 分毫不差；首扫 0 是架构师自己的嵌套形态错误，
  actor 对）——**MemBench 四源全绿可进真实 smoke**；**BEAM 两 variant 被
  `%B-%d-%Y` 时间格式确定性阻断**（官方 normalizer 只收 regex/ISO）+ 10m
  conv7/p1:s1 全无时间 + 33 万字符单 turn sensory buffer 无进展风险。
  ② **M0-5 验收通过**（78 锚抽验 2 处全中）→ **B2 "牵强"裁决落定（lightmem.md
  B2）：方案公平、采纳**——官方六 wrapper 全 session 级批量注入；Memobase 官方
  自己就是 force `flush(sync=True)`+时间窗 DB 增量（比我们更深）；Zep 先例=收集
  不完整照跑但声明指标不准（兜底政策官方背书）。halumem.md 同步。
  ③ **M0-6 卡已写待派**（BEAM 时间适配层施工 + smoke 切片风险核查，代码卡，
  缺时 fail-fast 保持、conv7 缺时政策 formal 前另裁）。④ **membench smoke 命令
  已交用户**（见 lightmem.md B11 进度更新后的当前格局：locomo 全齐、lme 差⑤、
  membench 待跑、beam 卡 M0-6、halumem 待 wrapper）。三指标全免费，predict
  用户跑、evaluate 架构师跑。
- 2026-07-13（**两卡待派发 + 框架差异化内核文档立档**，Fable 5）：用户重申
  "能派 actor 就派、架构师只做裁决/验收；一个 method 深耕不着急开下一个"。
  ① **M0-4 卡**（membench/beam × LightMem 离线兼容核查，纯取证零成本，产出
  `notes/m0-4-membench-beam-lightmem-compat.md`）与 **M0-5 卡**（HaluMem 官方
  harness 喂法取证，为 B2 "牵强"裁决供证，产出 `notes/m0-5-halumem-harness-feeding.md`）
  已写好待用户派发；**两卡零文件交集，可 worktree 并行**。M0-4 验收通过后架构师
  给 membench/beam 两格 smoke 命令（五件套口径，beam=100k+10m 两次 run）。
  ② **`docs/reference/framework-differentiators.md` 立档**（用户提议：论文/资金
  申请的"内核"）：D1 算法保真红线（MemoryData 绕管线判例）/ D2 评测元数据不进
  被测系统 / D3 效率不混算不重复计数（对方五处 prompt_tokens+estimate 重复计数
  实锚）/ D4 answer 口径统一 / D5 resume 工程 / D6 声明式能力矩阵；纪律=负面
  断言必须一手锚，判例组累积式。
- 2026-07-13（**MemoryData recall 改造判例取证**，Fable 5 压缩后续会话）：用户指路
  `第三方框架参考/MemoryData`（几乎全 method 支持 Recall@k）。架构师一手取证结论
  （全文 `notes/memorydata-recall-retrofit-survey.md`）：血缘 loader 侧 in-band
  header 标注 + 三条 adapter 侧回收策略（①in-band 文本解析=LightMem/A-Mem/
  SimpleMem；②原生 id 映射 sidecar=Mem0，LLM 改写不破坏；③文本反查表=MemoryOS），
  全部零 third_party 改动。**关键真相**：其 LightMem 格 `ingest_mode: direct`
  整条绕过抽取管线（verbatim chunk + offline_update）才换来 recall——真实管线下
  他们也没解决 provenance，且 vendored 源码 diff 证实上游抽取本就产出 fact 级
  source_id、构造 MemoryEntry 时丢弃（与 M0-3 一致）→ **维持原判：LightMem 走
  third_party 最小 diff（两处 ~5 行）+ 上游 PR 候选，差异化价值获判例佐证**；
  mem0/memoryos/amem/simplemem 四家初判"可无损改造"（策略②/③/①对应）。
  顺带发现待核：我们 vendored 的 LightMem 多出 bam_tags/BoundMem utils，与
  MemoryData 的副本版本分叉，PR 基准分支选择前需核 pristine 上游。已更新
  lightmem.md B5、checklist B5+ 判例库引用。
- 2026-07-13（**今日收官：locomo 格五件套全齐 + HaluMem 裁决判据 + 交接**，Fable 5，
  额度告警下收尾）：① **并行冒烟通过**（`lm-locomo-unified-par2`：2 conv ×
  workers=2，answers 2/2、judge 0.5 首个非零分）→ **locomo 格 = 首个五件套全齐
  格**；lme 格差 ⑤（低风险，随 cost-probe 顺带补）。② **HaluMem "牵强"质疑
  （用户）→ 裁决判据落档**（lightmem.md B2）：force=官方旋钮 + wrapper 只读不越
  红线，但使用节奏是否失真 → **前置取证 HaluMem 官方 harness 对无 session 概念
  method 的喂法**，同姿势=公平、做不到=N/A；裁决推迟到该格实施时。③ 交接更新 +
  handover 瘦身方向记录（见 handover 更新记录）。④ **五件套②补全**（用户点出遗漏
  ——smoke 要"全部适用指标"不只 judge）：架构师本地跑免费指标（requires_api=false
  零成本）：locomo=locomo-f1/f1/locomo-recall、lme 双轨=f1/recall/retrieval-rank；
  recall 类 n=0 = provenance=none 条件路径**正确**输出。**教训：开新认证口径的
  同一轮就该把免费部分自己跑完，不留给用户发现（§14 三问的"横向信号"没扫自己）。**
  **下一任第一件事：membench/beam
  × LightMem 离线兼容核查（不花钱）→ 给用户两格 smoke 命令；然后 B5+ 两项裁决
  （HaluMem 官方 harness 取证卡可派 actor）+ native build profile 实现。**
- 2026-07-13（**lme 双轨 smoke 收官 + 注入 token 双轨口径 + smoke 五件套新门**，Fable 5）：
  ① **lme judge 双轨 evaluate 通过** → locomo+lme 两格双轨 smoke 全通（旧口径）。
  **lme 空记忆真相**：memory_build 输出 7 token≈空抽取、injected_tokens=0 为真实零
  （1 round 任务型对话抽不出记忆点，合法；两轨 build 均 unified 配置故同空自洽）。
  ② **注入 token 双轨口径成文** `docs/reference/efficiency-injected-tokens-policy.md`
  （两轨统一记"记忆载荷 token"、native 模板开销不计入；四 run 实证 locomo 双轨
  同 68 / lme 双轨 0；native 有效性审计项进 B7）。③ **HaluMem 方案被用户纠偏后
  修正**：add_memory 不返回 entries 也无 session 概念 → 完整对齐 = session 级注入
  （messages list 天然支持）+ session 末 force 刷洗 + 包装捕获，语义代价留档
  （lightmem.md B2）。④ **checklist 三处升级**：B4 get_answer 拆分流程覆盖条款、
  B7 native 注入 token 审计项、**B11 smoke 五件套认证**（predict/全指标 evaluate/
  效率观测/formatted_memory 抽查/workers>1 并行冒烟）+ **resume 真实测试缓期至
  预算批复**（用户拍板）。⑤ **playbook §14 硬化**：commit 前强制过三问+§13 清单
  （用户第二次提醒判例 + "5h 压缩、磁盘唯一持久层"动机）。
  **下一步：locomo 并行冒烟（2conv×workers2，用户跑）→ membench/beam 离线兼容
  核查（架构师）→ B5+ 两项裁决落地方案。**
- 2026-07-13（**M0-3 + MX-1 双卡验收 + 两能力硬答案 + evaluate UX 修复**，Fable 5，
  基线 **1114 passed**）：① **M0-3 通过**（`9f6400e`）：LightMem 三接口契约逐参数/
  逐返回分支/MemoryEntry 逐字段落进 lightmem.md §0.5；**actor 教科书级停工纠错**：
  架构师 §0 原写"retrieve 落到 LightMemory.retrieve()"不准确——adapter 刻意复用其
  内部路径 `text_embedder.embed + embedding_retriever.search(return_full=True)` 保
  payload（一手核实后架构师已勘误 §0）。**两个能力硬答案**：add_memory 返回**无**
  memory entries（HaluMem memory_point 缺口实锤）；MemoryEntry **无** source_id
  字段（构造时丢弃，recall@k 缺口实锤）——两者均为"多一个字段"级 B5+ 改造候选
  （前者可 adapter 层包装 offline_update 零侵入；后者需 third_party 最小 diff =
  天然上游 PR 候选），裁决待排。② **MX-1 通过**（`6ff4d7c`→`e9e0319`）：三表全锚；
  小缺口：membench-recall 未标 metric_tier（台账）。③ **LoCoMo query 字段核证**
  （用户问）：生成期图片搜索关键词，官方 eval 不用，我们收 metadata 不进正文，
  无需特殊对待（locomo 实例文档 §7 落档）。④ **lme 双轨 predict 通**；evaluate
  因 multi-variant run_id 后缀（`…-s-cleaned`）查无而触发误导性报错 → **架构师直修**
  `_resolve_run_dir`：三布局全未命中 fail-fast + 相近 run id 提示（+2 测试）。
  ⑤ registry"减负/具体匹配"用户提议：架构师立场 = 不提前重构，LightMem 行打完后
  以能力矩阵落 integration-status，攒 2-3 个 method 真实行再定重构（见断点下方
  用户消息记录）。**下一步：用户跑 lme 两条 evaluate（用带后缀 run_id）→
  membench/beam 离线兼容核查 → B5+ 两项裁决。**
- 2026-07-13（**推进策略拍板 + native smoke 实锤 + 三份新政策/卡**，Fable 5）：
  ① **用户拍板：method 深耕制**——一个 method 查透 + 5 benchmark 全 smoke 通才进
  下一个（暂不并行开其他 method 的卡）。② **locomo native smoke 产物级验收通过**
  （读出分叉实锤：官方 ANSWER_PROMPT 透传 + `lightmem_locomo_paper_native_judge_v1`
  judge；M0-1c 新路径 `smoke/native/` 首战成功）→ **locomo 格双轨全通**。
  ③ **checklist 升级**：B3 逻辑隔离四项等效判据（写入分区/检索过滤/单空间删除/
  并行安全，任一证不了→物理兜底）；新增 **B5+ 无损改造评估**（导师建议：能力缺口
  三态裁决，改造经实验验证后可提 upstream PR）。④ **指标扩展计划成文**
  `docs/reference/metric-extension-plan.md`（分层纪律 metric_tier + 盘点→匹配两步走；
  LoCoMo BLEU-1 是官方非 QA 面，加 BLEU 属 supplementary 不得称官方口径）。
  ⑤ **注册面缺口一手**：LightMem task_families 只有 CONVERSATION_QA
  （registry.py:770）→ HaluMem 现进不去，待 B5+ 评估。⑥ **两卡开出**：
  [M0-3 LightMem API 契约详解](actor-prompt-m0-3-lightmem-api-contract.md)（参数/
  返回值/自定义类逐字段，顺带取 memory_point 与 source id 两个能力证据）、
  [MX-1 指标盘点](actor-prompt-metric-inventory.md)。**下一步：用户跑 longmemeval
  双轨 smoke；两卡回来后架构师做 HaluMem 改造裁决 + 指标匹配矩阵。**
- 2026-07-13（**M0-1c + M0.2 双卡验收 + 空库悬案关闭 + build 分叉裁决**，Fable 5 强验收）：
  ① **worktree 并行首战成功**（两 actor=codex+GPT-5.6，独立 worktree/分支，零冲突；
  合并=ff + cherry-pick 保线性）。② **M0-1c 通过**（`d014152`+`7879bb8`）：新布局
  `…/{mode}/{track}/{run_id}` 生效、旧布局仅可 evaluate 不可 resume、ambiguity 测试
  钉死、unified manifest 字节纪律保持；架构师独立复跑 **1112 passed** + compileall。
  ③ **M0.2 通过**（`8bfa404` → cherry-pick `f8344be`）：三方取证表全锚，抽锚 3 处
  一致；**架构师裁决：LightMem build 轴两轨分叉实锤**（extract 0.5 vs 0.1 等）→
  两个 native 格记忆不可复用、**构建成本 ×2**；native 源=复现目录 README reported
  命令，paper 网格出入留痕不标 DISPUTED（R0 不达标再升级）；"来源待溯"5 项=repo
  schema 无 readout 配置的结构性事实，正当。④ **空库悬案关闭**（用户跑 diag-log1）：
  1 round 抽取 2 条记忆、检索命中、sentinel=0——管道功能完整，旧空库判为抽取 LLM
  单次返 0 波动。⑤ 已知限制登记：LightMem 内部 INFO 诊断不落盘（连自家日志 0 字节）。
  **下一步：native 轨 smoke（lightmem×locomo `--config-track native`）→ cost-probe
  （整条 conversation）→ method-frozen-v1；并行可派其余 method 的 M0.1 审查取证卡。**
- 2026-07-13（**两张 actor 卡开出待派发**，Fable 5）：用户明确"actor 充裕、架构师
  额度珍贵，能下放的下放"。开卡：
  [M0-1c track-aware 路径层](actor-prompt-m0-1c-track-paths.md)（实现+测试，裁决已
  写死：新布局 `…/{mode}/{track}/{run_id}`、不迁移旧目录、evaluate 靠 `**` glob 兼容
  两布局、unified manifest 字节纪律不变）、
  [M0.2 LightMem native 配置三方取证](actor-prompt-m0-2-lightmem-config-threeway.md)
  （纯 notes 取证卡：paper(vendored lightmem.pdf)/experiments 目录/configs 默认/我们
  现用四列 × 7 轴，失配只陈述不裁决）。**并行前提 = per-actor 独立 worktree+分支**
  （playbook #18；worktree 命令已交用户）。空库诊断命令（predict-only + 读
  method.log，evaluate 非必需省 judge 钱）已交用户，等批预算执行。
- 2026-07-13（**实例化二次拍板补全：逐实体实例文档落盘**，Fable 5 回任执行）：用户
  指出 `integration-status.md` 总表不够——每个 method/benchmark 还要各一份按 checklist
  逐项展开的实例文档，尤其要拆开 method 接口调用黑盒。→ 新建
  `docs/reference/integration/` **11 份**（lightmem/mem0/memoryos/amem/simplemem/
  everos + locomo/longmemeval/membench/halumem/beam）：method 侧每份含**接口调用面
  表**（框架钩子→adapter 行为→third_party 调用，带行号锚）+ B1-B11 逐项（LightMem
  按 M0 实况勾选；其余四家为"代码取证预填"显式标注非验收结论）；benchmark 侧每份
  = A1-A8 锚点索引 + **"对 method 接入的含义"**节。总表改三层结构索引。**取证两个
  横向发现**：五 adapter 全 provenance=none（recall 类指标全员 N/A）；Mem0 未挂
  `clean_failed_ingest_state` 且唯一逻辑隔离（B3×B8 风险，checklist B8 例子待勘误）。
  下一步不变：空库诊断重跑（等用户批预算）→ M0-1c → M0.2 → 成本探针。
- 2026-07-13（**卡 X + 卡 Y 验收通过 + 今日收尾**，Opus 4.8 强验收）：两卡由用户派
  cc+GLM5.2 并行跑，**两 agent 在同一 git 树打架**烧光额度中断、中途换 DeepSeek 续，
  但最终 git 树线性干净（3 commit 未坏）。架构师一手复核：cd86c81(卡X)/5438064+feaa161(卡Y)
  齐、无冲突标记、**独立复跑 1106 passed 0 fail**（actor 报的"20 failed"是其环境缺 `datasets`
  模块的 BEAM 环境性失败，我环境 datasets=5.0.0 全绿，非回归）。**卡 X**：5 旧别名删净
  （calibrate 自有 flag 保留、已文档化）、smoke 默认问题帽=1、formal 仍 None。**卡 Y**：
  `method_log_scope` 上下文管理器 run 起挂 run 止摘（无泄漏）、第三方 INFO 降噪保 WARNING、
  已包裹 prediction+operation_level 两 runner。**均接受、待 push。事故记 playbook #18
  （多 actor 默认串行派、要并行须 git 隔离、收尾必一手复核 git）。** 新建
  [integration-status.md](../../reference/integration-status.md)（接入状态实例化落表）。
- 2026-07-13（**首次真实 flow-through smoke + LightMem offline 一手核 + 前置两卡派发**，Opus 4.8）：
  - **用户跑通首个真实 smoke**：`predict lightmem×locomo unified`（1 conv/1 round/1 question）
    + `evaluate locomo-judge` 全流程无崩，answers=1/1、judge mean=0.0（空记忆下瞎答，符合 smoke
    只验管道不看答对率）。产物在 `outputs/runs/lightmem/locomo/smoke/lm-locomo-unified-flowthrough/`。
  - **LightMem update 模式一手定论**：core `online_update()` 是**空壳 `return None`**
    （lightmem.py:394-395），`offline_update()` 才真持久化；**adapter 已用 offline**（:461）。
    → 用户"只用 offline"正确,且是唯一可用模式,无需动作。
  - **空库诊断（`No entries found...`）——纠正架构师草率结论**：非"数据少按阈值不生成"。
    force_segment/force_extract **已接且触发**（adapter last-batch:491-494、end_conversation:563/579-580；
    core:209-239）。空库只剩两因:segmenter 切出空 buffer(core short_term_memory.py:51 需 buffer 非空)
    或抽取返回 0。**静态代码判不了,因诊断 INFO 日志(“Created N MemoryEntry objects”等)没落盘**
    → 由**卡 Y** 落地后重跑读日志定论。
  - **两张前置卡派发**（cost-safety，服务 5×10 真实 smoke）:
    [卡 X CLI 别名去重 + smoke 默认问题帽=1](../ws04-terminal-observability/actor-prompt-cli-dedup.md)、
    [卡 Y per-run 日志落盘](../ws04-terminal-observability/actor-prompt-per-run-logfile.md)。与 M0-1c 不撞。
  - **measure-first 计划敲定（用户）**：① 先 5×10 全用极小 flow-through（1 conv/1 round/**1 question**）
    跑通=验管道(≠验记忆构建,build 在整条 conversation 阶段才真跑);② 再**逐格(method×benchmark)**
    跑一整条 conversation/instance 估成本,外推倍数按 benchmark(locomo×10、longmemeval×500);
    ③ 外推"区间 vs 点值"、如何选中位隔离空间,**待真正预算时按每隔离空间 token 数再定**（用户）。

## 当前断点（2026-07-12）

- 2026-07-12（**M0-1b + M0-eff 双卡验收通过**，Opus 4.8 强验收；含防作弊专查）：
  两 actor 并行交付、文件不重叠、**独立复跑全量 1093 passed + 3 deselected**（只升不降）。
  - **M0-1b（Actor A，config-track 机制）**：用户特别要求查"是否作弊式过测"——**结论：无作弊、第一性原理**。
    证据：① 22 处删除全是合法（longmemeval pass-through 重写 + prompt_track/answer-settings
    重构接 config_track），**零删断言、零 skip/xfail/assert True**；② unified 全程零回归——
    native 分支全部 gated 在 `config_track_bundle is not None`，unified 走原路且 manifest **不加**
    config_track 字段（既有 run 身份字节不变、resume 兼容）；③ cat5 跳过靠 evaluator 构造参数
    `_skipped_categories`（unified=空集→不跳）门控，不泄漏；④ 我此前发现的 longmemeval fidelity
    gap **已闭合**——端到端测试驱动真实 adapter retrieve→native builder，断言官方 formatter
    串在、reader-layout `formatted_memory` 不在；⑤ 被改的已验收 parity 测试是**加强**（sentinel
    formatted_memory 反证不被使用），非削弱。commits f502791/6010f77/0d93e60/2a24cd9/b26fd7c。
  - **M0-eff（Actor B，per-run 成本报告）**：`run_cost_report.py` 合并 prediction+全部 evaluator
    效率 store，`complete = cost.complete AND not missing_stores`（fail-loud，不把未采集角色当 0）+
    stage 拆分 + token-source 混比置信 + config_track 优雅降级；`cost.py` 纯加法（零删除、不改
    既有 `calculate_cost`）；ohmygpt.toml 用占位+来源待溯（未编造）。commits 890440e/788ffba/1218415/6c89476。
  - **架构师两处收尾**：① 填 ohmygpt gpt-4o-mini 实价 0.165/0.66 per-M（用户 2026-07-12 提供）；
    ② 直修 Actor B 一处脆测（`test_load_ohmygpt_pricing...` 硬 pin 占位 0.0，我填实价后暴露）→
    改断言"契约"（正价+本地跳过）而非具体价数。
  - **下一步**：M0-1c（track-aware 路径层）+ measure-first 真实 unified smoke（待用户确认预算/run_id）。
- 2026-07-12（**双卡并行派发**）：**M0-1b 已派**（用户，config-track 运行时机制，
  core-pipeline serial-freeze，架构师验收后才动下游）。**M0-eff 卡已开**
  [`actor-prompt-m0-eff-cost-report.md`](actor-prompt-m0-eff-cost-report.md)——per-run
  成本报告原语（合并两效率 store + ohmygpt 计价，价格用户后填），**离线、与 M0-1b
  文件不重叠**，可并行派第二 actor。效率**采集层审计无缺口**
  （[notes/lightmem-efficiency-audit.md](notes/lightmem-efficiency-audit.md)）。
  5×10 成本表仍归 ws05；本卡只做单元格来源原语。
- 2026-07-12（**M0-1 Task2-4 验收通过**，Opus 4.8 强验收）：actor（Codex/
  GPT-5.6）交 `lightmem_native_prompts.py` + `test_lightmem_native_prompts.py`
  （commits c57cabe/2ca91d4/6fcf1f0）。**独立复跑 41 passed**；scope 干净（零
  third_party/adapter/算法/现有 judge/unified 改动）；parity 测试运行时 AST 读真源
  逐字比对（非硬编码），locomo ANSWER_PROMPT/ACCURACY_PROMPT、longmemeval
  system+user、answer 参数 (0/2000/0.8)、longmemeval judge 复用现有 evaluator、
  cat5 跳过、负空间断言全部核实无编造。**接受。**
  **一处 fidelity 发现（架构师 owns，我卡欠规格，折进 M0-1b 不重派）**：longmemeval
  native builder 从 `formatted_memory` 重建，而 `formatted_memory` 走
  `_format_lightmem_memory`（reader 布局 `:1532`），官方 longmemeval 用
  `_format_lightmem_memory_as_official_retrieve`（`:1572`，docstring 明写对齐
  `run_lightmem_gpt.py:186`）→ 运行时会与官方分叉；locomo builder 靠透传 adapter
  `prompt_messages` 已规避。**M0-1b 修**：两个 native builder 都透传 adapter
  `prompt_messages`（native 单一真源）+ 端到端 parity 测试。
- 2026-07-12（**架构师裁 Task1 + 双轨政策成文 + 杂项**，Opus 4.8）：
  ① **Task1 裁决**——native locomo answer=`ANSWER_PROMPT`（标准），StructMem 不接
  （一手核 `experiments/locomo/readme.md`：`--enable-summary` 改 build+检索+embedding
  三处、非纯 answer；paper headline 数字是 summary OFF）。actor 卡 Task1 已改成"已裁决
  直接照用"，**可派新 actor 续 Task2-4**。② **双轨政策落盘**
  [`docs/reference/dual-track-config-policy.md`](../../reference/dual-track-config-policy.md)
  （7 轴 build/readout 二分、native 配置来源决策树、reproduce-vs-paper 一致性检查、
  single-track collapse、算法代码单一化）；checklist B10 与本 plan §3 已引用。
  ③ **改正记忆复用口径**：非无条件，仅两轨 build 轴全同才复用。④ **A-Mem 双仓库一手核**：
  `third_party/methods/A-mem`=复现版（adapter 接的这份，对）、`third_party/A-mem`=通用库版
  （adapter 未用），M 阶段再定通用版去留（policy §7）。⑤ GitHub 用户名 buctzzp→zzp-elio，
  active 文件已改（README/scripts），archive 保留历史。⑥ 运行时 config-track 机制拆成
  **M0-1b**（架构师设计后派，不丢欠规格机制给 actor）。
- 2026-07-12（Codex / GPT-5.6，M0-1 Task 1 停工）：LightMem LoCoMo 的
  `ANSWER_PROMPT` 与 `ANSWER_PROMPT_StructMem` **都是实际可达的活跃分支**，
  任务卡要求交回架构师裁定，不能由 actor 自选。证据：
  `search_locomo.py:258-280` 在 `enable_summary=True` 时格式化 StructMem
  prompt，在 False 时格式化标准 prompt；`process_sample` 将该配置原样传入
  builder（`:441-447`）；CLI 暴露 `--enable-summary` 的 `store_true` 开关，
  默认 False（`:566-570`），并据此选择带 summary 的 entry loader
  （`:616-620`）。候选方案：A. native locomo 默认 profile 锁官方 CLI 默认
  `ANSWER_PROMPT`，StructMem 另列可选 native 子 profile；B. native locomo
  选 StructMem，但这还要求同时定义 summary retrieval/`session_summaries`
  输入契约，已超出本卡纯 answer profile 范围。等待架构师裁定后再做 Task 2-4；
  当前零生产代码改动、未运行自检、未提交。
- 2026-07-12（**M0 立项 + LightMem M0.1 审查完成 + 首 actor 卡开**）：
  ① 标准清单落盘 `docs/reference/method-integration-checklist.md`
  （benchmark A1-A8 + method B1-B11 的 Definition of Done）。
  ② **一手核实 native 配置矩阵**（更正架构师此前先验错误——见下表，
  Mem0/SimpleMem 都被漏报）。③ LightMem M0.1 审查完成
  [notes/lightmem-m0-audit.md](notes/lightmem-m0-audit.md)：物理隔离/
  offline flush/provenance=none/api_usage 已做/native={locomo,longmemeval}
  全部一手锚，零阻塞。④ 双 embedding 省钱想法**否决**（method 内部
  embedding 无法分叉、检索耦合构建会分叉文本，见 plan §3）。⑤ 首 actor
  卡 [actor-prompt-m0-lightmem-config.md](actor-prompt-m0-lightmem-config.md)
  = config-track 机制 + LightMem locomo native profile（离线实现+测试）。
  **下一步：用户派发 actor 卡 → 架构师验收 → 架构师跑真实 unified smoke
  （measure-first：先 LightMem×LoCoMo 一个，读成本，再铺开）。**

## 一手 native 配置矩阵（2026-07-12 架构师逐仓库核实）

| method | locomo | longmemeval | beam | membench | halumem |
|--------|:--:|:--:|:--:|:--:|:--:|
| Mem0 | ✓ | ✓ | ✓ | – | – |
| MemoryOS | ✓ | – | – | – | – |
| A-Mem | ✓ | – | – | – | – |
| LightMem | ✓ | ✓ | – | – | – |
| SimpleMem | ✓ | ✓ | – | ✓ | – |
| MemOS | ✓ | ✓ | – | – | – |
| EverOS | ✓ | – | – | – | – |
| Letta/LangMem/Supermemory | 未见 | 未见 | 未见 | 未见 | 未见 |

证据出处见 plan §2。**边界**：Letta/LangMem/Supermemory 是工程产品，
grep 目录/py 未见 academic 实验配置，各自 M0 时深挖确认；"有实验目录"
≠"能完整抽出 native config"，逐格抽取 + 架构师验收才算数。native 轨
只在 ✓ 格存在；unified 轨所有格都要。

## 里程碑

- **M0.1** 逐 method 接口审查（架构师一手）→ audit note。
- **M0.2** 双轨接入（config-track 机制 + native profile 抽取，actor 实现）。
- **M0.3** 极小 unified smoke（架构师跑真实 API，measure-first）→ 成本观测。
- **M0.4** native 轨 smoke（有配置的格子）+ method-frozen-v1。
- 之后：I0 离线矩阵 → R0 真实校准（lightmem 论文对齐，见
  ws02.6 judge-config-audit §6；用户批预算）。
