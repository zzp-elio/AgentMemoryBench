# LightMem 前四格 forced-flush exact-smoke 零 API reachability

日期：2026-07-19

执行者：GPT-5.6 sol 架构师（主树直接核验）

网络/API：0；只读正式数据、既有 run manifest/checkpoint、本地 LLMLingua 与 MiniLM。

## 1. 为什么要查

`8879af9` 修正了 vendored LightMem 两处 forced-flush bookkeeping，并把
`sensory_memory.py` 纳入 source identity。前四格既有 artifact 的 source hash 是
`74be165f…`，current build 是 `a44d7d99…`，严格 resume 必然拒绝；但“hash 变化”本身不能代裁
是否要重烧 API。

真正会改变本次 extraction 输入的条件只有一个：**最后一次 `add_memory()` 在
`add_messages()` 中自动切出 prefix，随后 `force_segment=True` 又切出 tail**。旧实现会用 tail
覆盖 automatic prefix；新实现按顺序 `extend` 两者。单纯修正 forced flush 后的清理游标不会
改变该次输出，只影响调用后的暂存态，而该调用已经是 conversation final。

## 2. exact-smoke 取样身份

探针用 production benchmark registration 重建既有 B11 的精确裁剪，不从 gold 选样：

| benchmark/variant | 旧 run 的精确 history/conv 规模 | conversation id |
| --- | --- | --- |
| LoCoMo/locomo10 | 3 rounds，2 conversations | `conv-26`, `conv-30` |
| LongMemEval/s_cleaned | 1 round，2 conversations | `e47becba`, `118b2229` |
| MemBench/0_10k | 每源 1 round、每源 1 conversation | 四个 `*-0` |
| MemBench/100k 补充哨兵 | FirstHigh+ThirdHigh，每源 1 round、每源 1 conversation | 两个 `*-0` |
| BEAM/100k | 1 round，2 conversations | `1`, `2` |
| BEAM/10m | 1 round，1 conversation | `1` |

单/双 worker 对同一 conversation 内容不作不同裁剪；因此只需按唯一 conversation 核一次，不能
把相同 payload 因 worker 数不同重复算作两份 reachability 证据。

## 3. 第一层：真实 compressor/tokenizer 全量探针

使用 current TOML 等价配置 `pre_compress=true / compression_rate=0.7 /
sensory_buffer_len=512 / hybrid`。只构造本地 `LlmLingua2Compressor`，dummy endpoint 固定为
`127.0.0.1:9` 且没有构造 memory manager、retrieve 或 answer 调用。每个 production batch 经过
真实 compressor 后，按 sensory manager 相同 tokenizer 计算 user token 数并逐调用模拟溢出。

| benchmark | conversation | batch 数 | 压缩后每批 user tokens | final 自动溢出 |
| --- | --- | ---: | --- | --- |
| LoCoMo | conv-26 | 3 | 11, 23, 13 | 否 |
| LoCoMo | conv-30 | 3 | 13, 26, 27 | 否 |
| LongMemEval | e47becba | 1 | 117 | 否 |
| LongMemEval | 118b2229 | 1 | 40 | 否 |
| MemBench 0_10k | first-high | 1 | 34 | 否 |
| MemBench 0_10k | first-low | 1 | 30 | 否 |
| MemBench 0_10k | third-high | 2 | 29, 67 | 否 |
| MemBench 0_10k | third-low | 2 | 22, 34 | 否 |
| MemBench 100k | first-high | 1 | 120 | 否 |
| **MemBench 100k** | **third-high** | **2** | **438, 361** | **是：438+361>512** |
| BEAM 100k | 1 | 1 | 34 | 否 |
| BEAM 100k | 2 | 1 | 40 | 否 |
| BEAM 10m | 1 | 1 | 41 | 否 |

汇总原文：

```text
SUMMARY {"affected": ["membench/100k/third-high-highlevel-movie-0"],
"affected_count": 1, "conversation_count": 13, "network_calls": 0}
```

## 4. 第二层：受影响样本的真实 vendored 链

对唯一候选运行真实
`LightMemory.add_memory → LLMLingua compressor → SenMemBufferManager → topic segmenter → MiniLM`
链；只把 `ShortMemBufferManager.add_segments()` 的下游 extraction 换成 recording sink 并立即
返回 `(0, [])`，所以不会进入 memory LLM、向量写入、retrieve 或 answer。第一批按 production
`force=false`，第二/最终批按 `force_segment=true, force_extract=true`。

```text
cut_trace = [
  {force_segment: false, segment_count: 1, source_external_ids: [["1", "1"]]},
  {force_segment: true,  segment_count: 1, source_external_ids: [["2", "2"]]}
]
shortmem_received[-1] = {
  force_extract: true,
  segment_count: 2,
  source_external_ids: [["1", "1"], ["2", "2"]]
}
final sensory buffer / big_buffer / token_count = 0 / 0 / 0
REAL_CHAIN_REACHABILITY_PASSED
```

重复 id 是 ThirdAgent singleton 的真实 child 与 structural assistant placeholder 镜像同一个
source id，不是重复 source turn。承重点是旧实现会把第一个 automatic segment 覆盖掉；新实现
把 step 1 与 step 2 各一次、按原序交给 STM。

## 5. 架构裁决

1. LoCoMo、LongMemEval、MemBench `0_10k` 与 BEAM 的已验 B11 精确 crop **不触达**输出改变路径；
   不需要为了 source hash 变化而重烧这四格主 smoke。旧 artifacts 仍不可 resume 到新 build，
   但可以作为这些 exact shapes 的行为证据与本 note 的 reachability 证据组合使用。
2. MemBench `100k` missing-time 补充哨兵的 `third-high-highlevel-movie-0` **确定触达**；旧 run 没有
   完整送入 step 1，故旧 `100K_MISSING_TIME_SENTINEL_PASSED_ZERO_EXTRACTION` 不能继续给 current
   source identity 盖章。
3. 最小付费复验只需重跑既有 100k FirstHigh+ThirdHigh W1 哨兵，不重跑 0_10k W1/W2、LoCoMo、
   LongMemEval 或 BEAM。完成前 LightMem current build 保持 `FROZEN_PENDING_100K_SENTINEL_REFILL`。
4. 本探针只裁 exact smoke reachability，不外推 full：更长 history 当然可能命中 automatic+tail，
   但 current code 已有真实链强反例锁定正确合并行为。
