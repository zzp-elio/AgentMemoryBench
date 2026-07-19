# LightMem × HaluMem session boundary R1 实现记录

日期：2026-07-19  
基线：`cc8b893`  
分支：`actor/lightmem-halumem-session-boundary-r1`  
环境：隔离 worktree `/Users/wz/Desktop/mb-actor-lightmem-halumem-flush-r1`；零真实 API、零模型下载、
未创建 `outputs/`。首次总门发现 worktree 缺 gitignored HaluMem 数据后，按卡给 `data/` 建了
指向主工作区同名目录的只读使用软链；未修改或暂存目标资产，未给 `models/` 建软链。

## 1. 机制分类与施工边界

两条 current-main 失败都属于现有 `force_segment` 语义内的状态 bookkeeping 错误，不需要新增
reset/session API，也不需要改变 boundary、threshold、compression、prompt、extraction batching、
online-soft 或 LTM：

1. forced tail 已把 current buffer 全部输出，清理游标却从 message index 误换成 boundary count；
2. 同次 `add_memory()` 的 automatic segments 已由 `add_messages()` 返回，force 分支却用 tail
   重赋值覆盖。

因此本批继续执行最小修复。若 real-core 反例在该修复后仍不能给出 session-local report，停工并
建议 extraction/memory-type N/A 的条件会命中；实际没有命中。

## 2. 补丁前零 API 复现

### 2.1 真实 sensory manager

使用真实 `SenMemBufferManager`、空白 tokenizer、固定 boundary=1 与正交向量，第一 session 放入
两个 pair 后 force flush。stdout：

```text
session1_segments= [[('user', 'u1'), ('assistant', 'a1')], [('user', 'u2'), ('assistant', 'a2')]]
after_session1_buffer= [('assistant', 'a1'), ('user', 'u2'), ('assistant', 'a2')]
after_session1_big_buffer= []
token_count= 1
session2_error= IndexError list index out of range
```

### 2.2 真实 `LightMemory.add_memory()` 调度

用真实 `LightMemory.add_memory()` 驱动最小 fake sensory（`AUTO` / `TAIL`）与 recording STM，
在进入任何抽取调用前返回。stdout：

```text
shortmem_received= [[{'role': 'user', 'content': 'TAIL'}]]
```

补丁写入前把两条反例和 source-identity 断言落成测试，承重子集得到：

```text
5 failed, 1 warning in 5.81s
```

其中四条是本卡目标失败；production-chain fixture 另先被测试自身对
`custom_prompts is truthy` 的过强断言挡住。该断言随后按真实默认 `None` 收紧，不改变生产代码
或目标契约。

## 3. 实现

- `sensory_memory.py`：forced tail append 后令清理位置等于 append 前 current buffer 的 message
  数；随后复用既有 delete + token recount。非 force 分支仍保留最后一个未输出 tail。
- `lightmem.py`：force 分支改为把 `cut_with_segmenter()` 返回值顺序 `extend` 到
  `add_messages()` 已返回的 automatic segments；不倒序、不去重、不合并文本。
- `lightmem_adapter.py`：method source identity 新增
  `src/lightmem/factory/memory_buffer/sensory_memory.py`。`LIGHTMEM_ADAPTER_VERSION` 保持
  `conversation-qa-v7`，没有旧 hash 兼容口。
- `tests/test_lightmem_adapter.py`：新增 forced/non-force、连续 session、AUTO+TAIL、source
  identity 和 HaluMem production adapter 链反例。

生产链测试实际调用 vendored `LightMemory.add_memory()`、`SenMemBufferManager`、
`ShortMemBufferManager.add_segments()`、真实 extraction-result conversion 与
`LightMemory.offline_update()`；fake 只替换远端 extraction 返回与本地 insert 边界。第一 session
有两个真实 pair 并形成非空 boundary，第二 session 有一个 pair。修复后结果：

```text
session1_report = ['memory:s1-u1,s1-a1', 'memory:s1-u2,s1-a2']
session2_report = ['memory:s2-u1,s2-a1']
sensory buffer/big_buffer/token_count = [] / [] / 0
short-memory buffer/token_count = [] / 0
LTM after session2 = session1 two entries + session2 one entry
```

这证明清理的是已输出/已抽取的暂存态，不是累计在线 LTM；observer 记录的候选只来自当前
session 调用。

## 4. 强反例覆盖

1. 非空 boundary + force：segment bytes/order 不变，forced flush 后 sensory 三项归零；
2. 连续两个 session：第二次只含第二 session，不崩溃、不重复；
3. threshold crossing + force：`AUTO`、`TAIL` 按原顺序各一次进入 STM；
4. HaluMem production adapter：真实 vendored sensory/STM/LightMemory，两份 report 严格
   session-local，旧 LTM 保留；
5. no-boundary force：整段输出并清空行为不变；
6. non-force carryover：只删 emitted prefix，保留 tail，token_count 重算为 1；
7. identity：文件列表包含 sensory 文件，临时 fixture 只改该文件 bytes 时 hash 必变；
8. version/manifest：adapter 仍为 v7；既有 registered/registry 定向门继续验证 source identity
   和 strict manifest/resume，不新增 HaluMem 特判键。

修复后上述新增专项子集：

```text
7 passed, 1 warning in 7.47s
```

## 5. 前四格 reachability

变更触达所有使用官方 `LightMemory.add_memory()` 的 benchmark，但影响分两层：

- forced flush 的清理位置修复不改变本次输出 segment bytes/order，只改变调用后的 sensory
  residual；非 final `force_segment=False` 的 prefix/tail 语义由强反例锁定不变；
- automatic + forced tail 合并只在**同一次 final add** 同时产生 automatic prefix 与 remaining
  tail 时改变下游 extraction，正是旧实现会漏内容的路径。该路径对长输入可达，不能仅凭旧 cropped
  smoke 没撞到就宣布不可达。

因此 LoCoMo/LongMemEval/MemBench/BEAM 的旧真实 artifacts 只能作为旧 source identity 的历史
证据，不能 resume 到新 build；是否需要重跑前四格 current-v7 B11 由架构师根据真实 smoke shape
与本次定向门裁决。actor 不修改任何既有 `REAL_SMOKE_PASSED`/frozen 状态。

## 6. 自检、偏差与执行身份

任务卡指定的五文件定向门首次得到：

```text
2 failed, 215 passed, 1 warning in 7.92s
```

两条失败均为 `DatasetNotFoundError: halumem expected dataset path missing:
data/halumem/HaluMem-Medium.jsonl`，发生在 production code 执行前。建立卡允许的 `data/` 资产
软链后，原命令复跑尾行：

```text
217 passed, 1 warning in 7.62s
```

`git diff --check`：clean。

偏差披露：除任务卡最终门外，为满足“补丁前必须复现”先运行两条临时零 API stdout 探针与一组
预补丁失败测试；补丁后又运行新增 7-case 专项子集。五文件总门因缺 gitignored 数据资产先失败
一次，补资产软链后复跑一次。没有运行全量 pytest、compileall、真实 API、模型下载或写实验资产。

执行入口为 Codex multi-agent subagent；本 actor 没有再使用子 agent。harness 没有向本 actor
独立暴露可核验的细分模型标签，因此不从父会话或模板猜模型名。
