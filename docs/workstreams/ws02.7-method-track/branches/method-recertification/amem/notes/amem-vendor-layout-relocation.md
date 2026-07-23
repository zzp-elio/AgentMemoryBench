# A-Mem 双仓库目录整理

> 日期：2026-07-23
>
> 性质：vendored source 布局整理；不改变算法、输入映射、配置、adapter version 或
> method source identity。

## 1. 裁决

A-Mem 在本项目中有两个独立上游：

| 本地目录 | 上游 | 身份 |
|---|---|---|
| `third_party/methods/A-mem-product/` | `agiresearch/A-mem` | Phase 1 通用产品，adapter 实际调用 |
| `third_party/methods/A-mem/` | `WujiangXu/AgenticMemory` | 论文实验/复现参照，不进入主产品 build |

旧布局把通用产品单独放在顶层 `third_party/A-mem/`，破坏了 method 源码统一归档规则。
本批将它原样移动到 `third_party/methods/A-mem-product/`。

不采用“把实验仓库放进通用仓库子目录”的方案。两个目录分别来自独立 upstream；嵌套会
制造虚假的仓库所有权，混淆 upstream 升级边界、license/source identity 与 Git 管理，
也让外部读者误以为 paper reproduction 是产品仓库的一部分。并列且显式命名能同时表达
“同一 method 家族”和“不同 implementation surface”。

## 2. 行为不变量

- `AMem.consume_granularity` 仍为 `turn`。
- runtime 仍为产品 `AgenticMemorySystem.add_note/search_agentic`。
- content、speaker/role、caption、typed source time、lineage、HaluMem session delta 均不变。
- `AMEM_ADAPTER_VERSION` 保持 `conversation-qa-v2-product`。
- state manifest 只保存 adapter/profile/source hash，不保存 vendored root 的本地绝对路径。
- source identity 只哈希产品根内六个文件的相对路径与字节，根目录改名不进入 digest。

迁移前冻结 hash：

```text
6ca55fc8780e4d2dff0c2a8cb11643e48c804831a010e9d8e3cc1805f855c024
```

迁移后实测 hash：

```text
6ca55fc8780e4d2dff0c2a8cb11643e48c804831a010e9d8e3cc1805f855c024
```

## 3. 实现

- tracked 产品目录用 Git rename 原样移动，不复制、不删减上游文件。
- adapter 通过统一的
  `PathSettings.resolve_third_party_method_path("A-mem-product")` 找产品根；由公共 helper
  继续强校验目录存在与路径不得逃逸。
- `third_party/methods/MANIFEST.md` 分别声明 product 与 paper-reproduction 两个 upstream，
  不再让一行 `A-mem` 同时冒充两种身份。
- 当前稳定 integration/frozen 文档更新为新路径；历史审计不倒写当年的源码位置和裁决。

## 4. 验收

- A-Mem adapter、registered prediction、共享 registry 与文档门：
  `66 passed in 9.98s`。
- 独立 import 探针解析到
  `third_party/methods/A-mem-product/agentic_memory/memory_system.py`。
- 迁移后 source hash 为
  `6ca55fc8780e4d2dff0c2a8cb11643e48c804831a010e9d8e3cc1805f855c024`，与冻结前逐字
  相同。
- `src/memory_benchmark`、`tests` 与产品 `agentic_memory` compileall exit 0。
- 最终无 API 全量门：
  `1680 passed, 3 deselected, 1 warning, 29 subtests passed in 132.13s`。唯一 warning
  是既有 LightMem Pydantic v2 deprecation，与本批无关。
- `git diff --check` clean；真实 API 未调用。
