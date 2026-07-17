# Method TOML profile 与完整 answer builder 迁移

## 目的

把 2026-07-17 已拍板的配置政策落到运行时：每个 method 一个 TOML；主 section 跨五个
benchmark 固定；有一手作者参数时才增加稀疏 `author_<benchmark>`；TOML 选择完整 answer
builder，不再让新运行依赖全局 `config_track=unified/native` 双分支。

现行政策事实源：
[`method-toml-and-answer-builder-policy.md`](../../../../reference/method-toml-and-answer-builder-policy.md)。

## 范围

后续实施批只允许围绕以下事项展开：

1. method registry/profile loader 接受经审核的 `author_<benchmark>` section；
2. 把 adapter/third_party 接缝中写死但确属配置的参数暴露给强类型 TOML；
3. 让 section 选择 benchmark 完整 builder 或 method 官方完整 builder；
4. 对作者 builder 锁变量来源、缺失 fail-fast、最终 `PromptMessage[]` parity 与私有 gold 隔离；
5. manifest/resume 记录 section、解析后配置、builder 与 answer decoding 参数；
6. 保留旧 `config_track`/TrackIdentity/outputs 的只读兼容，不改写历史产物。

不在本支线范围：替 method 做 benchmark-specific sweep、决定所有 method 的最终最优参数、
调用真实 API、把算法实现分叉伪装成 TOML section。

## 依赖与顺序

1. MemBench FirstAgent canonical pair split；
2. RetrievalEvidence M1；
3. 5×10 主 smoke 可继续使用当前 `[smoke]`，不等待本支线调参；
4. **首个 `author_<benchmark>` 校准 run 或真实效果 `official_full` run 前**，本支线实现门
   必须关闭。

## 当前状态

**scheduled（2026-07-17）；尚未写 actor 卡，暂勿派发。**当前只有政策与消费者落盘，零代码
变更、零参数改动、零真实 API。到触发点后，架构师先逐 method 盘点“已暴露字段/仍写死字段/
官方 builder 所需变量”，再按单 method 小卡串行施工，禁止一次性横扫十家。

现行兼容实现中，LightMem 的 LoCoMo/LongMemEval 已有 `config_track=native` 官方 answer builder
与 readout bundle，技术上可运行；但 `TrackIdentity v1` 明确把它标为 `native_scope=readout_only`、
`build_override_applied=false`，不会切换作者 build 超参数/embedding/lifecycle。因此它只能叫“旧
readout-native 校验”，不能叫 `author_<benchmark>` 复现。两条 benchmark 的该路径已有历史 smoke，
本轮不为重复覆盖生成即将迁移的付费过渡 run；首次正式作者校准时，先实现 TOML section、完整
builder/decoding/manifest 身份，再使用新 run_id 执行。

## 退出条件

- 至少一个 method 用主 section 跑通五格离线/极小 smoke 路由，且不依赖新双轨分支；
- 至少一个有官方证据的 author section 通过最终 messages parity 强反例；
- manifest/resume 对 section/builder/config 失配 fail-fast；
- 旧 run 可离线读取但不能无痕 resume 到新身份；
- checklist B9-B11、对应 integration 实例页和父 README 有真实验收输出。
