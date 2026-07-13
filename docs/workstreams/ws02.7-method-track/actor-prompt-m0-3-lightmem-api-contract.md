# Actor 卡 M0-3：LightMem 官方接口契约详解（参数/返回值/自定义类逐字段展开）

> 派发日 2026-07-13。自包含卡。**纯取证卡：只允许修改
> `docs/reference/integration/lightmem.md` 一个文件**；禁改任何代码；禁真实 API。

## 0. Git 纪律
独立 worktree + 分支 `actor/m0-3-api-contract`（用户已建）。只 commit 本分支、
禁 push、禁碰其他分支。引用的每个行号现场打开文件核实。

## 1. 背景

用户（2026-07-13）：实例文档的接口调用面表只有"调了什么"，还要"**输入参数的
含义与详细结构、返回值的含义与详细结构——返回值若是自定义类，把类逐字段展开**"，
否则 method 仍是半个黑盒。本卡把 LightMem 补到位；产出格式将成为后续所有 method
的模板。

## 2. 施工内容

在 `docs/reference/integration/lightmem.md` 的 §0 表格之后**新增一节
`## 0.5 接口契约详解（官方 API）`**，覆盖 adapter 实际调用的每个官方入口
（源 = `third_party/methods/LightMem/src/lightmem/memory/lightmem.py` 及其引用）：

1. `LightMemory.add_memory(...)`：完整签名；每个参数一行（名/类型/默认/含义/
   **我们 adapter 实际传什么**，adapter 行号+官方行号双锚）；返回值结构逐键展开
   （已知它带 token/api_call_nums 类效率字段——确切结构一手核）。
   **特别回答**：返回值里有没有"本次产出的 memory entries"？（= HaluMem
   memory_point 能力判定的关键证据，B2/B5+ 用）。
2. `LightMemory.retrieve(...)`：签名+参数表；返回结构（字符串？对象列表？）；
   **特别回答**：返回里有没有条目 id / 可定位来源的字段？（= recall@k 无损改造
   可行性的关键证据）。
3. `LightMemory.offline_update(...)`：签名+参数表+返回；与 add_memory 的
   force_segment/force_extract 的关系一句话说清。
4. **自定义类逐字段展开**：`MemoryEntry`（及 add/retrieve 路径上出现的其他
   自定义类/TypedDict/dataclass），每个字段：名/类型/含义/谁写入/谁消费。
5. 一张小表收尾：**能力证据摘要**——memory_point 可得性 / source id 可得性 /
   效率字段清单，三行，只写事实不写裁决。

## 3. 硬规则
- 每个陈述带 `文件:行号`；查不到写"来源待溯"；**禁编造**（含"合理推断"——推断
  必须标注为推断并给依据行号）。
- 含义描述允许读 docstring/注释/调用点归纳，但**结构**（类型/键名/字段）必须
  以代码为准。
- 不改 §0-§B11 既有内容，只新增 §0.5（若发现既有内容与你的一手证据矛盾，写进
  施工报告，不要改）。

## 4. 停工条件
- add_memory/retrieve 的返回结构随配置分叉到无法用一张表描述 → 停工列出分叉。

## 施工报告（actor 填写）
（待填）
