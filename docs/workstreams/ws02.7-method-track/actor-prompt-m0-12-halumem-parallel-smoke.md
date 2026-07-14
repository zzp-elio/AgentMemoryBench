# Actor 卡 M0-12：HaluMem 标准并行 smoke 形状（固定第二形状，非自由裁剪）

> 派发日 2026-07-14。自包含代码卡。允许修改：
> `src/memory_benchmark/benchmark_adapters/halumem.py`、`src/memory_benchmark/
> cli/main.py`（仅 smoke 轴校验处）、tests、新建
> `docs/workstreams/ws02.7-method-track/notes/m0-12-halumem-par-smoke.md`。
> 禁改 runners/、禁改其他 benchmark、禁真实 API。
> **前置**：M0-11 合入 main 后再开工（否则并行 smoke 也会撞 probe-scope bug）。

## 0. Git 纪律
```
git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m12 -b actor/m0-12-halumem-par
cd /Users/wz/Desktop/mb-actor-m12 && uv sync
```
禁 push；只跑目标测试 + compileall（playbook #18）。

## 1. 背景与设计裁决

HaluMem smoke 是**固定形状**（用户 2026-07 设计，正确：halumem 灌入与测评
交错、session 级耦合，自由裁剪 round/QA 会破坏官方语义）：
`cli/main.py:635-647` 拒绝一切裁剪参数；`benchmark_adapters/halumem.py:262`
smoke = `adapter.load(limit=1)` 单 user。后果：B11 五件套⑤（并行冒烟需
workers>1 且 ≥2 conversations）对 halumem 无法执行——单 user 下第二 worker
空转 = 无效并行（beam par2 判例）。

**裁决**：不开放自由裁剪，而是**增加第二个同样固定的标准形状**：
- 维持现状：默认 smoke = 1 user（形状零变化，已有 run 可比性不受影响）。
- 新增：`--workers N`（N>1）时 smoke 数据集固定取 `load(limit=2)` 的**前 2 个
  user**（确定性顺序，与 limit=1 的那个 user 保持同源前缀），其余裁剪参数
  依旧全部拒绝。即"并行标准形状"也是唯一的、不可调的。
- manifest/metadata 记录实际形状（smoke_policy 或 metadata 补
  `smoke_parallel_shape` 字段），保证 resume 指纹区分两种形状、互不误续。

## 2. 施工内容
1. halumem 的 smoke 构建按 workers 分派两个固定形状（workers 从
   PreparedBenchmarkRun 请求链路已有的参数取；若该参数未传到 adapter 层，
   选最小改动的传递路径并在 note 里给锚——**不许**为此改 runner 签名）。
2. cli 校验信息更新：拒绝裁剪参数的报错文案补一句"parallel smoke uses a
   fixed 2-user shape"之类的提示。
3. 测试：workers=1 形状与现状逐字节一致（回归）；workers=2 数据集恰为前
   2 user 且确定性；裁剪参数在两种形状下都被拒；resume 指纹两形状不互认。

## 3. 完成门
目标测试 + compileall 全绿（报数字）；note = 形状定义 + 传参路径锚 + resume
指纹说明。真实验证 = 用户跑 `--workers 2` halumem smoke（付费，不在本卡）。

## 4. 停工条件
- workers 参数无法在不改 runner/公共签名的前提下到达 halumem smoke 构建点；
- 发现 operation-level runner 实际不支持 workers>1 协调（若如此=停工上报，
  ⑤ 对 halumem 记 N/A 的裁决权在架构师）。

## 施工报告（actor 填写）
（待填）
