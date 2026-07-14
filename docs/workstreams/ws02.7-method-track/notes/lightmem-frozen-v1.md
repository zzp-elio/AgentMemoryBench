# LightMem method-frozen-v1（2026-07-14）

> 首个走完 B1-B11 全流程的 method。判据=`method-integration-checklist.md`,
> 逐项证据=`docs/reference/integration/lightmem.md`（本文不复制,只给结论
> 与缺口清单）。**冻结语义:自本日起 `lightmem_adapter.py`、LightMem 注册行
> 与已批准的 third_party diff 视为冻结面,任何改动需在 ws02.7 断点区给出
> 解冻理由并重跑受影响格的 smoke。**

## 1. B1-B11 终局

B1-B11 全 ✅（状态行=integration-status.md;B2/B4/B8/B11 于 2026-07-14
frozen 收口,其余各项 2026-07-12~13 期间逐项过,证据锚全在实例文档）。
五格 smoke:locomo（双轨+prov n=1）/membench（-0-10k）/beam（-100k/-10m）/
lme（-s-cleaned,par2）/halumem（-medium,四指标）。主树基线 1151 passed
（M2-mem0 合入同日）。

## 2. 声明缺口（冻结时如实带走,不算违约）

1. **真实 resume 验证缓期**：resume 机制有离线测试网,但"真实 API 大 run
   断点续跑"未实测——缓期至预算批复后的 full 前置件（用户拍板）。
2. **native build profile 未实现**：native 轨=口径面（prompt/参数）native,
   build 侧超参仍 repo 默认（bundle 显式声明 hyperparam_ref=repo_default;
   三岔口证据 `lightmem-native-config-threeway.md`）。做全 native build =
   记忆不可复用、构建成本 ×2,进成本表后再定。
3. **halumem 五件套⑤=N/A**：operation-level runner 设计上单 worker
   （M0-12 停工证据链）;并行化=full 前独立设计项。
4. **lme 时间戳无非零实测样本**（B4 例外声明,机制同源,大切片补测）。
5. **上游两件套待用户操作**：source_id 透传 PR（素材
   `m0-7-lightmem-provenance.md` §6）+ 多 batch sid 空间不一致 issue。
6. **transformers `>512` embedding 截断警告**：smoke 可见,full 前复查
   影响面。
7. **B9 已知分叉**：locomo judge=lightmem 衍生（7 处文本偏差,框架级已
   声明）;native 校准复现（全套跟论文含模型）属第三种一次性用途,未跑。

## 3. 对流水线的输出

LightMem 期产出的通用资产与判据已收编
`docs/reference/method-onboarding-assembly-line.md` §一/§二,不在此重复。
后续 method 的 frozen note 以本文为体例:终局一句话 + 声明缺口编号清单 +
冻结语义。
