# EverOS 接入实例（B1-B11 逐项）

> 判据模板：`../method-integration-checklist.md` §B；勾选总表：`../integration-status.md`。
> 状态：**未开始**。仅完成 vendoring；**排接入序列最后**（用户 2026-07 拍板，
> 替代原名单中的 cognee）。

- adapter：无
- 算法源：vendored `third_party/methods/EverOS/`（git 尚未跟踪，2026-07-13 时点
  untracked——首个 M 阶段动作应含来源锁 + git 纳管决定）
- native 格：**locomo**（ws02.7 README 一手矩阵；配置来源待 M 阶段一手）

## B1-B11：全部 ⬜（无预填事实——接口调用面待其 M 阶段架构师 M0.1 审查产出）

## 特殊情况
1. 接入顺序最后：LightMem → Mem0/MemoryOS/A-Mem/SimpleMem 补 B 系列 →
   MemOS/Letta/LangMem/Supermemory → EverOS。
2. vendored 目录未进 git 是当前唯一 method 源码不在版本控制内的例子，M 阶段先处理。
