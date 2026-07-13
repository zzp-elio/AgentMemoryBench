# Actor 卡 M0-6：BEAM × LightMem 时间适配层施工 + smoke 切片风险核查

> 派发日 2026-07-13。自包含卡。**代码卡**：允许修改
> `src/memory_benchmark/methods/lightmem_adapter.py` + 新增/修改其测试 +
> 新建 `docs/workstreams/ws02.7-method-track/notes/m0-6-beam-time-adapter.md`。
> **禁改** `third_party/`、`src/memory_benchmark/benchmark_adapters/beam.py`
> （frozen）、其他 method/runner 文件。禁真实 API。

## 0. Git 纪律（actor 自建 worktree）
```
git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m06 -b actor/m0-6-beam-time
cd /Users/wz/Desktop/mb-actor-m06 && uv sync
```
只 commit 本分支、禁 push、禁碰其他分支。data/ 为 gitignored 资产，从主树
`/Users/wz/Desktop/memoryBenchmark/data/` 只读，不拷贝。引用行号现场核实。

## 1. 背景（M0-4 取证结论，先读
`notes/m0-4-membench-beam-lightmem-compat.md` §2-§3、§6）

BEAM 非空 time_anchor 是 `April-02-2024` 式 `%B-%d-%Y`（架构师已独立复扫实锤：
100k 90/5,732 非空）。LightMem adapter 对非 LoCoMo 时间原样透传
（lightmem_adapter.py:1410-1426），官方 `MessageNormalizer` 只收
`YYYY[/-]M[/-]D (weekday) H:MM` 或 ISO（lightmem.py:28-57）→ 100k/10m smoke
必然 `ValueError`。架构师裁决的修复方向：**adapter 时间适配层显式转换,
不动 frozen benchmark adapter、不动 third_party**。

## 2. 施工内容

1. **时间适配**：在 lightmem_adapter 的时间标准化层加 `%B-%d-%Y` → ISO 的
   显式、可测转换（如 `April-02-2024` → `2024-04-02T00:00:00`）。约束：
   - 转换规则**通用声明**（月名-日-年格式），不写死 "BEAM" 分支名；放在现有
     LoCoMo 特化之后、透传之前的位置。
   - 原始字符串保留进可审计位置（现有 metadata/日志通道，有则用无则不加）。
   - 完全无时间的 fail-fast 行为**保持不变**（架构师裁决：这是正确行为；
     10m conv7/p1:s1 的缺时政策在 formal 前另行裁决，本卡不处理）。
2. **测试**：pytest 覆盖 ①`%B-%d-%Y` 正例（含单数日 `July-1-2024` 若真实数据
   存在该形态——先扫描确认，不存在则不造）②非法月名仍走原路径 ③既有 LoCoMo/
   ISO 路径回归不破。fixture 用真实 BEAM anchor 值。
3. **smoke 切片风险核查**（写进 note，零成本）：
   - 按 BEAM 声明式 smoke policy（frozen 档案 + `benchmark_adapters/beam.py`
     裁剪轴）算出 100k 与 10m smoke 实际会注入哪些 conversation/session/turn；
   - **硬答案 A**：10m smoke 切片是否触达 conv 7/`p1:s1`（244 turns 全无时间）？
   - **硬答案 B**：两 variant smoke 切片内最长 turn 多少 chars/tokens？是否
     含 30 万字符级 turn（M0-4 §2.4 的 sensory buffer 无进展风险）？
   - 若 smoke 切片含超长 turn：本地跑一次 LLMLingua-2 压缩该 turn（本地模型，
     零 API 成本），报告压缩后 token 数是否 <512、耗时；若不含，写明即可，
     压缩实测推迟。
4. **完成门**：`uv run pytest -q` 全绿（报数字）+ `uv run python -m compileall
   -q src/memory_benchmark tests`；note 里给出"BEAM 100k/10m 可否进入真实
   smoke"的更新结论。

## 3. 硬规则
- 只动允许清单内文件；不改 LightMem 抽取/存储逻辑（转换发生在进入官方
  normalizer 之前的 adapter 侧）。
- 转换必须无损可逆记录（原值可审计），禁静默丢弃原始格式信息。
- 每个陈述带 `文件:行号`；禁编造。

## 4. 停工条件
- 发现 `%B-%d-%Y` 之外还有第三种真实 anchor 形态 → 停工列清单等裁决。
- 时间适配需要动 beam.py 或 third_party 才能实现 → 停工说明原因。

## 施工报告（actor 填写）
（待填）
