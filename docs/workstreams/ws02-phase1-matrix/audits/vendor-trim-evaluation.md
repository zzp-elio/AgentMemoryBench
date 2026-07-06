# third_party vendor 裁剪评估决策卡片

日期：2026-07-07
执行者：Codex
范围：纯静态调研；零真实 API；未移动、删除或修改 `third_party/` 文件。

## 1. 实际 Import 面

已 git 跟踪的 vendored method 只有 4 个：A-mem、LightMem、MemoryOS-main、mem0-main。
registry 将四者的 `source_identity_factory` 分别接到 adapter 内的 source identity
函数（`src/memory_benchmark/methods/registry.py:37`,
`src/memory_benchmark/methods/registry.py:43`,
`src/memory_benchmark/methods/registry.py:46`,
`src/memory_benchmark/methods/registry.py:50`,
`src/memory_benchmark/methods/registry.py:611`,
`src/memory_benchmark/methods/registry.py:640`,
`src/memory_benchmark/methods/registry.py:669`,
`src/memory_benchmark/methods/registry.py:698`）。

| 仓库 | 运行时 import / 引用入口 | source fingerprint 覆盖 | 被引用文件数 / git 跟踪总文件数 |
| --- | --- | --- | --- |
| A-mem | adapter 将 `third_party/methods/A-mem` 加入 `sys.path` 后 import `memory_layer_robust`（`src/memory_benchmark/methods/amem_adapter.py:191`, `src/memory_benchmark/methods/amem_adapter.py:208`, `src/memory_benchmark/methods/amem_adapter.py:218`） | `README.md`, `memory_layer_robust.py`, `llm_text_parsers.py`, `test_advanced_robust.py`, `run_k_sweep.sh`, `requirements.txt`（`src/memory_benchmark/methods/amem_adapter.py:144`, `src/memory_benchmark/methods/amem_adapter.py:158`） | 6 / 16 |
| LightMem | adapter 将 `third_party/methods/LightMem/src` 加入 `sys.path` 后 import `lightmem.memory.lightmem`；LoCoMo prompt 另从 `experiments/locomo/prompts.py` 读取（`src/memory_benchmark/methods/lightmem_adapter.py:216`, `src/memory_benchmark/methods/lightmem_adapter.py:229`, `src/memory_benchmark/methods/lightmem_adapter.py:238`, `src/memory_benchmark/methods/lightmem_adapter.py:1447`） | `README.md`, `pyproject.toml`, `src/lightmem/memory/lightmem.py`, LoCoMo add/search/prompts, LongMemEval runner（`src/memory_benchmark/methods/lightmem_adapter.py:242`, `src/memory_benchmark/methods/lightmem_adapter.py:249`） | 7 / 505 |
| MemoryOS-main | adapter import `eval` 下官方模块 `utils`, `short_term_memory`, `mid_term_memory`, `long_term_memory`, `dynamic_update`, `retrieval_and_answer`, `main_loco_parse`（`src/memory_benchmark/methods/memoryos_adapter.py:92`, `src/memory_benchmark/methods/memoryos_adapter.py:1131`, `src/memory_benchmark/methods/memoryos_adapter.py:1173`） | `eval/*.py`, `README.md`, `LICENSE`, `memoryos-pypi/prompts.py`，并额外把本项目 wrapper 纳入组合身份（`src/memory_benchmark/methods/memoryos_adapter.py:243`, `src/memory_benchmark/methods/memoryos_adapter.py:255`, `src/memory_benchmark/methods/memoryos_adapter.py:262`, `src/memory_benchmark/methods/memoryos_adapter.py:286`） | 11 / 73 |
| mem0-main | adapter 从 vendored 根 import `mem0`，benchmark prompt 从 `memory-benchmarks/benchmarks/*/prompts.py` 加载（`src/memory_benchmark/methods/mem0_adapter.py:194`, `src/memory_benchmark/methods/mem0_adapter.py:211`, `src/memory_benchmark/methods/mem0_adapter.py:221`, `src/memory_benchmark/methods/mem0_adapter.py:234`, `src/memory_benchmark/methods/mem0_adapter.py:1000`, `src/memory_benchmark/methods/mem0_adapter.py:1008`, `src/memory_benchmark/methods/mem0_adapter.py:1676`） | `mem0/**/*.py` 140 个文件 + `pyproject.toml` + `LICENSE` + LoCoMo/LongMemEval 两个 prompt，共 144 个文件（`src/memory_benchmark/methods/mem0_adapter.py:205`, `src/memory_benchmark/methods/mem0_adapter.py:221`, `src/memory_benchmark/methods/mem0_adapter.py:234`） | 144 / 1599 |

实测命令输出：

```text
$ git ls-files third_party/methods | sed 's#^third_party/methods/##' | cut -d/ -f1 | sort | uniq -c
  16 A-mem
 505 LightMem
   1 MANIFEST.md
  73 MemoryOS-main
1599 mem0-main
```

```text
$ for d in A-mem LightMem MemoryOS-main mem0-main; do printf '%s ' "$d"; git ls-files "third_party/methods/$d" | wc -l; done
A-mem       16
LightMem      505
MemoryOS-main       73
mem0-main     1599
```

```text
$ printf 'A-mem fingerprint files\n'; for f in README.md memory_layer_robust.py llm_text_parsers.py test_advanced_robust.py run_k_sweep.sh requirements.txt; do test -f "third_party/methods/A-mem/$f" && printf '%s\n' "$f"; done
A-mem fingerprint files
README.md
memory_layer_robust.py
llm_text_parsers.py
test_advanced_robust.py
run_k_sweep.sh
requirements.txt
```

```text
$ printf 'LightMem fingerprint files\n'; for f in README.md pyproject.toml src/lightmem/memory/lightmem.py experiments/locomo/add_locomo.py experiments/locomo/search_locomo.py experiments/locomo/prompts.py experiments/longmemeval/run_lightmem_gpt.py; do test -f "third_party/methods/LightMem/$f" && printf '%s\n' "$f"; done
LightMem fingerprint files
README.md
pyproject.toml
src/lightmem/memory/lightmem.py
experiments/locomo/add_locomo.py
experiments/locomo/search_locomo.py
experiments/locomo/prompts.py
experiments/longmemeval/run_lightmem_gpt.py
```

```text
$ printf 'MemoryOS fingerprint files\n'; find third_party/methods/MemoryOS-main/eval -maxdepth 1 -type f -name '*.py' | sed 's#third_party/methods/MemoryOS-main/##' | sort; for f in README.md LICENSE memoryos-pypi/prompts.py; do test -f "third_party/methods/MemoryOS-main/$f" && printf '%s\n' "$f"; done
MemoryOS fingerprint files
eval/dynamic_update.py
eval/evalution_loco.py
eval/long_term_memory.py
eval/main_loco_parse.py
eval/mid_term_memory.py
eval/retrieval_and_answer.py
eval/short_term_memory.py
eval/utils.py
README.md
LICENSE
memoryos-pypi/prompts.py
```

```text
$ git ls-files 'third_party/methods/mem0-main/mem0/**/*.py' | wc -l
     140
```

```text
$ git ls-files 'third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/prompts.py' 'third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/prompts.py' 'third_party/methods/mem0-main/pyproject.toml' 'third_party/methods/mem0-main/LICENSE'
third_party/methods/mem0-main/LICENSE
third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/prompts.py
third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/prompts.py
third_party/methods/mem0-main/pyproject.toml
```

## 2. 体积画像

四个已跟踪仓库在当前 git tracked 文件中的合计工作区字节约 60.5 MB。mem0-main
占 tracked vendor 字节 51.4%，LightMem 占 37.1%；二者是主要空间来源。

| 仓库 | git 跟踪文件数 | tracked 文件字节 | tracked 字节占比 | 目录 `du -sh` |
| --- | ---: | ---: | ---: | ---: |
| A-mem | 16 | 2,083,121 | 3.4% | 4.8M |
| LightMem | 505 | 22,465,593 | 37.1% | 23M |
| MemoryOS-main | 73 | 4,833,488 | 8.0% | 4.9M |
| mem0-main | 1599 | 31,112,147 | 51.4% | 48M |
| 合计 | 2193 | 60,494,349 | 100.0% | - |

实测命令输出：

```text
$ for d in A-mem LightMem MemoryOS-main mem0-main; do printf '%s ' "$d"; git ls-files -z "third_party/methods/$d" | xargs -0 wc -c | tail -n 1; done
A-mem  2083121 total
LightMem  22465593 total
MemoryOS-main  4833488 total
mem0-main  31112147 total
```

```text
$ for d in A-mem LightMem MemoryOS-main mem0-main; do du -sh "third_party/methods/$d"; done
4.8M	third_party/methods/A-mem
 23M	third_party/methods/LightMem
4.9M	third_party/methods/MemoryOS-main
 48M	third_party/methods/mem0-main
```

```text
$ git count-objects -vH
count: 5333
size: 29.29 MiB
in-pack: 3411
packs: 2
size-pack: 32.39 MiB
prune-packable: 0
garbage: 0
size-garbage: 0 bytes
```

6 个 local-only 仓库当前不进入 git，仍由 `third_party/methods/MANIFEST.md`
记录 upstream 和版本锚点；`git ls-files` 对这些目录均为 0。MANIFEST 记录
MemOS、SimpleMem、cognee、langmem、letta、supermemory 的 URL、commit 和
`local-only；按 fetch 脚本恢复` 管理方式（`third_party/methods/MANIFEST.md:8`,
`third_party/methods/MANIFEST.md:9`, `third_party/methods/MANIFEST.md:10`,
`third_party/methods/MANIFEST.md:11`, `third_party/methods/MANIFEST.md:12`,
`third_party/methods/MANIFEST.md:13`）。

```text
$ for d in MemOS SimpleMem cognee langmem letta supermemory; do printf '%s ' "$d"; git ls-files "third_party/methods/$d" | wc -l; done
MemOS        0
SimpleMem        0
cognee        0
langmem        0
letta        0
supermemory        0
```

```text
$ for d in MemOS SimpleMem cognee langmem letta supermemory; do du -sh "third_party/methods/$d"; done
 86M	third_party/methods/MemOS
113M	third_party/methods/SimpleMem
280M	third_party/methods/cognee
6.6M	third_party/methods/langmem
309M	third_party/methods/letta
274M	third_party/methods/supermemory
```

## 3. 参考框架做法

MemoryData 采用混合做法：对 A-Mem、LightMem、MemoryOS、MemOS、cognee、Letta、
SimpleMem 等放 `methods/*/source/` 的 vendored source 目录，同时 adapter 通过
`sys.path` 引用 source。例如 A-Mem adapter 把 `methods/a_mem/source/a_mem`
加入 `sys.path` 并 import `memory_layer`（`第三方框架参考/MemoryData/methods/a_mem/a_mem_adapter.py:17`,
`第三方框架参考/MemoryData/methods/a_mem/a_mem_adapter.py:18`,
`第三方框架参考/MemoryData/methods/a_mem/a_mem_adapter.py:22`），LightMem adapter
把 `methods/lightmem/source` 加入 `sys.path` 后 import `LightMemory`
（`第三方框架参考/MemoryData/methods/lightmem/lightmem_adapter.py:22`,
`第三方框架参考/MemoryData/methods/lightmem/lightmem_adapter.py:23`,
`第三方框架参考/MemoryData/methods/lightmem/lightmem_adapter.py:27`），MemoryOS
同样从 `methods/memoryos/source` import `MemoryOS`
（`第三方框架参考/MemoryData/methods/memoryos/memoryos_adapter.py:10`,
`第三方框架参考/MemoryData/methods/memoryos/memoryos_adapter.py:11`,
`第三方框架参考/MemoryData/methods/memoryos/memoryos_adapter.py:15`）。
代价是仓库较重，但复现时不依赖第三方包发布状态。

EverOS / EverCore 评测是另一种形态：既有 in-process adapter，也有 HTTP API
adapter。架构记录列出 `evermemos_local_api` / `evermemos_cloud_api` 对应
`EverCoreAPIAdapter`（`第三方框架参考/EVALUATION_ARCHITECTURE.md:60`,
`第三方框架参考/EVALUATION_ARCHITECTURE.md:63`），并说明 HTTP API 使用
`group_id = conversation_id` 隔离（`第三方框架参考/EVALUATION_ARCHITECTURE.md:1349`,
`第三方框架参考/EVALUATION_ARCHITECTURE.md:1352`）。MemoryData 的 EverOS
adapter 也是 thin HTTP wrapper：构造 `base_url/search/conversation-meta`，
用 `httpx.Client` 发请求（`第三方框架参考/MemoryData/methods/everos/everos_adapter.py:1`,
`第三方框架参考/MemoryData/methods/everos/everos_adapter.py:14`,
`第三方框架参考/MemoryData/methods/everos/everos_adapter.py:40`,
`第三方框架参考/MemoryData/methods/everos/everos_adapter.py:62`）。代价是可复现性
依赖外部服务状态，但本仓库无需复制完整实现。

supermemoryai memorybench 更偏 provider SDK/API 接入。复刻文档列出 Mem0 使用
`mem0ai`、Zep 使用 `@getzep/zep-cloud`、Supermemory 使用 `supermemory`
依赖（`第三方框架参考/supermemoryai-memorybench.md:87`,
`第三方框架参考/supermemoryai-memorybench.md:88`,
`第三方框架参考/supermemoryai-memorybench.md:89`）；provider 注册为
`supermemory`, `mem0`, `zep`, `filesystem`, `rag`
（`第三方框架参考/supermemoryai-memorybench.md:1456`,
`第三方框架参考/supermemoryai-memorybench.md:1459`,
`第三方框架参考/supermemoryai-memorybench.md:1460`,
`第三方框架参考/supermemoryai-memorybench.md:1461`,
`第三方框架参考/supermemoryai-memorybench.md:1462`,
`第三方框架参考/supermemoryai-memorybench.md:1463`）。Supermemory、Mem0、
Zep 分别通过 SDK/client 或 HTTP polling 写入与检索
（`第三方框架参考/supermemoryai-memorybench.md:1474`,
`第三方框架参考/supermemoryai-memorybench.md:1505`,
`第三方框架参考/supermemoryai-memorybench.md:1551`,
`第三方框架参考/supermemoryai-memorybench.md:1573`,
`第三方框架参考/supermemoryai-memorybench.md:1612`,
`第三方框架参考/supermemoryai-memorybench.md:1628`,
`第三方框架参考/supermemoryai-memorybench.md:1645`），并强调 provider
只负责 search，最终 answer 由统一 answering model 生成
（`第三方框架参考/supermemoryai-memorybench.md:2797`,
`第三方框架参考/supermemoryai-memorybench.md:2799`）。代价是 benchmark
主体很轻，但强依赖云 API / SDK 版本。

## 4. 裁剪风险清单

只保留当前被 import 或 source fingerprint 覆盖的子树，会立刻丢失一批审计资产：

- 官方 eval 脚本和 prompt / 参数事实源会变薄。当前接口清单仍引用 mem0
  `memory-benchmarks/README.md`、LoCoMo / LongMemEval `run.py` 和 prompts
  （`docs/reference/method-interface-inventory.md:62`,
  `docs/reference/method-interface-inventory.md:63`,
  `docs/reference/method-interface-inventory.md:64`,
  `docs/reference/method-interface-inventory.md:65`,
  `docs/reference/method-interface-inventory.md:66`,
  `docs/reference/method-interface-inventory.md:67`），LightMem 也引用 README、
  LoCoMo add/search、LongMemEval runner/offline_update 和论文 PDF
  （`docs/reference/method-interface-inventory.md:131`,
  `docs/reference/method-interface-inventory.md:132`,
  `docs/reference/method-interface-inventory.md:133`,
  `docs/reference/method-interface-inventory.md:134`,
  `docs/reference/method-interface-inventory.md:135`,
  `docs/reference/method-interface-inventory.md:136`,
  `docs/reference/method-interface-inventory.md:137`）。
- requirements / pyproject / README / LICENSE 是复现与合规上下文。A-Mem source
  identity 已把 `requirements.txt` 纳入哈希（`src/memory_benchmark/methods/amem_adapter.py:158`,
  `src/memory_benchmark/methods/amem_adapter.py:164`），LightMem 纳入
  `pyproject.toml`（`src/memory_benchmark/methods/lightmem_adapter.py:249`,
  `src/memory_benchmark/methods/lightmem_adapter.py:251`），mem0 读取
  `pyproject.toml` 的 package version（`src/memory_benchmark/methods/mem0_adapter.py:212`,
  `src/memory_benchmark/methods/mem0_adapter.py:216`）。
- 未来扩展 HaluMem / BEAM / MemBench 时，可能需要目前未 import 的官方
  `evaluation/`, `experiments/`, examples 或 benchmark 子目录作为参数、prompt、
  reader 和 gap 核验来源。裁剪会把“可读原始上下文”变成需要重新拉 upstream。
- source fingerprint 有两类风险。第一类是直接变化：如果裁剪时移动路径、改相对路径、
  改文件内容或漏掉当前哈希文件，`source_sha256` 会变化；MemoryOS 甚至把 wrapper
  与 vendored 文件组合成 `source_sha256`（`src/memory_benchmark/methods/memoryos_adapter.py:282`,
  `src/memory_benchmark/methods/memoryos_adapter.py:287`,
  `src/memory_benchmark/methods/memoryos_adapter.py:316`）。这会影响已完成
  conversation state 的 source 校验和 resume 兼容。第二类是间接风险：即便哈希
  文件保持不变，裁掉同仓其他事实源后，后续人工审查难以解释旧 hash 对应的完整
  upstream 语境。
- 已有测试和文档把 source identity 当作稳定契约。例如 A-Mem resume 会比较
  `source_sha256`（`src/memory_benchmark/methods/amem_adapter.py:639`,
  `src/memory_benchmark/methods/amem_adapter.py:675`），MemoryOS 也有 wrapper /
  vendored source identity 兼容测试（`tests/test_memoryos_registered_prediction.py:739`,
  `tests/test_memoryos_registered_prediction.py:804`,
  `tests/test_memoryos_registered_prediction.py:811`）。裁剪不是单纯文件瘦身，
  会进入 resume / manifest 兼容边界。

## 5. 方案建议

| 方案 | 内容 | 收益 | 风险 | 建议 |
| --- | --- | --- | --- | --- |
| A 维持现状 | 4 个已接入 method 继续 git-tracked 全仓 vendor；6 个未接入 method 维持 MANIFEST + local-only | 保留已验收 source hash、官方脚本、论文/README/requirements 证据链；不影响 resume | 仓库继续承担约 60.5 MB tracked vendor 字节，mem0-main 和 LightMem 较重 | 推荐 |
| B 裁剪已跟踪 4 仓 | 只保留当前 import / fingerprint 覆盖文件或子树 | 可减少 mem0-main、LightMem 的 tracked 文件数和工作区体积 | 易丢官方 eval 事实源；改动会穿透 source identity / resume；未来 benchmark 扩展要重新找 upstream | 不推荐本轮执行 |
| C 全部转 MANIFEST + 脚本 | 4 个已跟踪仓库也改成 local-only，靠脚本按 commit 恢复 | 主仓最轻，接近 6 个新 method 的管理方式 | 当前已验收代码与历史输出依赖已跟踪 source hash；会要求重写恢复脚本、CI/本地 bootstrap、source identity 策略 | 仅可作为 ws03 独立迁移议题 |

推荐：选择 A，维持现状，不执行裁剪。理由是本阶段目标是可复现、可审计、可恢复；
当前 60.5 MB tracked vendor 体积相对可接受，而裁剪会把风险集中到 source
fingerprint、resume 兼容和官方事实源缺失上。若未来必须瘦身，应先由架构师另开
ws03 级迁移 spec，定义新的 source identity 版本、恢复脚本、历史 run 兼容策略和
审计证据保留规则，再考虑 B 或 C。
