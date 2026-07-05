---
id: ws02
doc: plan (Track A2)
status: approved
created: 2026-07-06
---
# ws02 Track A2 实施计划：全部 10 个 method 机制深读

（2026-07-06 扩编：从 6 个新 method 扩为全部 10 个。用户指出 4 个已接入
method 的调研知识从未以卡片形式沉淀，只散落在代码与旧 handoff 中；本轮统一
补齐，最终形成 10 张同格式、同深度的机制卡片。）

执行者：Codex。目的：为最终协议设计提供 method 侧输入——Track A 回答了
"装不装得上"，本轮回答"**它的记忆机制到底怎么运转**"。产出将与 5 benchmark
调研卡片一起构成架构师的"粒度需求双向矩阵"。

## 施工纪律

1. 沿用 Track A 全部纪律：零真实 API、零 key、不修改 third_party 与主环境。
2. **隔离试装一律改用 uv**（PyPI SSL 问题已由架构师实测解决）：
   `uv venv /tmp/mech-<method> && uv pip install --python /tmp/mech-<method>/bin/python <pkg>`。
   仍禁止 `uv add` / 改 `pyproject.toml`。
3. 结论必须给源码证据（文件:行号）；推断和事实分开写；不确定就进"未确认项"。
4. 每完成一个 method 立即勾选并 commit（`docs: add <method> mechanism card`）。

## 关键素材（先读）

- 各 method 官方仓库：`third_party/methods/<dir>/`。
- **MemoryData 框架的实际集成代码**（最高价值参考——它已把这 6 个 method
  全部跑起来过）：`第三方框架参考/MemoryData/methods/<name>/` 的 adapter 与
  `MemoryData/utils/agent.py` 中对应分支（如何喂 chunk、何时 finalize）。
- Supermemory 另参考其官方评测框架 `第三方框架参考/memorybench/`。
- Track A 卡片（`audits/<method>.md`）作为起点，不重复其内容。

**4 个已接入 method（Mem0、MemoryOS、A-Mem、LightMem）的额外素材与要求**：

- 素材：`third_party/methods/{mem0-main,MemoryOS-main,A-mem,LightMem}/` 官方源码
  与 eval 脚本；我们的 adapter `src/memory_benchmark/methods/*.py`；
  `docs/reference/method-interface-inventory.md`（2026-06-22 版，作为起点）。
- 卡片额外加第 7 节 **"现有 adapter 的形变记录"**：逐条列出我们 adapter 中
  哪些代码是被 `add(conversation)` 整段输入逼出来的拆分/拼接/循环（贴
  文件:行号），以及官方原生调用形态本来是什么。这是协议重设计最直接的证据，
  务必具体。

## 机制卡片格式

每 method 写 `audits/mechanism-<method>.md`，固定 6 节（已接入 method 为 7 节）：

1. **写入后内部发生什么**：从原生 ingest API 进入后的完整 pipeline
   （抽取？分层？图构建？向量化？何时调 LLM/embedding？同步还是后台？）。
   用一段流程描述 + 关键源码位置。
2. **原生 ingest 形态**：确切函数签名；输入单位（单 message / message pair /
   自由文本 chunk / 文档 / session 批）；必需与可选字段（时间戳、角色、
   speaker 名、会话 id、用户 id）；是否有显式 flush/finalize/commit 边界；
   MemoryData 是怎么喂它的（贴其 adapter 调用形态）。
3. **检索机制**：检索入口签名；内部检索流程（向量/图/分层/关键词/LLM 重排）；
   返回结构（能否拿到条目级 provenance：来源 id、时间、分数）；
   检索是否调 LLM（对照协议规则 R1：检索服务型 LLM 允许，作答型禁止）。
4. **状态与边界行为**：状态存哪（内存/本地文件/DB/服务端）；多用户/多会话
   隔离的原生机制；有无后台任务（对照 R3 完成判据：如何知道"写入已可检索"）；
   清空/重建状态的官方方式（clean retry 需要）。
5. **对协议设计的含义**：该 method 最舒服的消费粒度是什么（turn / session /
   conversation / 文档 / chunk）；哪种粒度会让 adapter 被迫做别扭的拼接或拆分；
   需要哪些边界信号。**只陈述事实含义，不替架构师做协议选型。**
6. **未确认项**。

## 任务清单

先做 4 个已接入 method（素材最全、上手最快，还能立即产出协议证据），
再按从轻到重做 6 个新 method：

- [x] mechanism-mem0.md（含第 7 节形变记录）
- [x] mechanism-lightmem.md（含第 7 节；重点：offline update 的边界信号从哪来）
- [x] mechanism-amem.md（含第 7 节；重点：session_time 传递与 keyword 生成）
- [x] mechanism-memoryos.md（含第 7 节；重点：短中长期分层的写入触发时机）
- [x] mechanism-simplemem.md
- [x] mechanism-langmem.md
- [ ] mechanism-supermemory.md（含 memorybench 中 provider 实现的调用证据）
- [ ] mechanism-memos.md
- [ ] mechanism-cognee.md
- [ ] mechanism-letta.md
- [ ] 更新 `audits/summary.md`：追加"原生粒度一览"，覆盖全部 10 个 method，
  供架构师直接做矩阵
- [ ] 更新 ws02 README 断点，通知架构师

## 验收

- 6 张机制卡片 6 节齐全，每个机制结论有 `文件:行号` 证据。
- summary 的"原生粒度一览"覆盖全部 10 个 method。
- `git status --short` 无主环境依赖文件变更；全程零 API 调用。

## 明确不做

- 不写任何 adapter 代码；不下协议选型结论（第 5 节只陈述事实含义）。
- 不重做 Track A 的安装/配置面内容；不调研 benchmark 侧（架构师负责萃取）。

## 执行验收记录

### mechanism-mem0.md

完成时间：2026-07-05 20:40 CST

隔离试装命令：

```bash
rm -rf /tmp/mech-mem0 && uv venv /tmp/mech-mem0 && uv pip install --python /tmp/mech-mem0/bin/python -e third_party/methods/mem0-main
```

实际输出：

```text
Using CPython 3.12.8 interpreter at: /Library/Frameworks/Python.framework/Versions/3.12/bin/python3
Creating virtual environment at: /tmp/mech-mem0
Activate with: source /tmp/mech-mem0/bin/activate
Using Python 3.12.8 environment at: /private/tmp/mech-mem0
Resolved 32 packages in 2.66s
   Building mem0ai @ file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/mem0-main
Downloading openai (1.3MiB)
Downloading numpy (5.1MiB)
Downloading sqlalchemy (2.1MiB)
Downloading grpcio (11.5MiB)
 Downloaded openai
 Downloaded sqlalchemy
      Built mem0ai @ file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/mem0-main
 Downloaded numpy
 Downloaded grpcio
Prepared 13 packages in 3.08s
Installed 32 packages in 110ms
 + annotated-types==0.7.0
 + anyio==4.14.1
 + backoff==2.2.1
 + certifi==2026.6.17
 + charset-normalizer==3.4.7
 + distro==1.9.0
 + grpcio==1.81.1
 + h11==0.16.0
 + h2==4.3.0
 + hpack==4.2.0
 + httpcore==1.0.9
 + httpx==0.28.1
 + hyperframe==6.1.0
 + idna==3.18
 + jiter==0.16.0
 + mem0ai==2.0.4 (from file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/mem0-main)
 + numpy==2.5.1
 + openai==2.44.0
 + portalocker==3.2.0
 + posthog==7.21.3
 + protobuf==6.33.6
 + pydantic==2.13.4
 + pydantic-core==2.46.4
 + pytz==2026.2
 + qdrant-client==1.18.0
 + requests==2.34.2
 + sniffio==1.3.1
 + sqlalchemy==2.0.51
 + tqdm==4.68.3
 + typing-extensions==4.16.0
 + typing-inspection==0.4.2
 + urllib3==2.7.0
```

结构验收命令：

```bash
rg -c '^## [1-7]\. ' docs/workstreams/ws02-phase1-matrix/audits/mechanism-mem0.md
```

实际输出：

```text
7
```

源码证据计数命令：

```bash
rg -c '证据：`' docs/workstreams/ws02-phase1-matrix/audits/mechanism-mem0.md
```

实际输出：

```text
29
```

格式与主环境依赖检查命令：

```bash
git diff --check -- docs/workstreams/ws02-phase1-matrix/audits/mechanism-mem0.md docs/workstreams/ws02-phase1-matrix/plan-track-a2-method-mechanism.md
git status --short -- pyproject.toml uv.lock .venv
```

实际输出：

```text
```

### mechanism-langmem.md

完成时间：2026-07-05 21:01 CST

隔离试装命令：

```bash
rm -rf /tmp/mech-langmem && uv venv /tmp/mech-langmem && uv pip install --python /tmp/mech-langmem/bin/python -e third_party/methods/langmem
```

实际输出：

```text
Using CPython 3.12.8 interpreter at: /Library/Frameworks/Python.framework/Versions/3.12/bin/python3
Creating virtual environment at: /tmp/mech-langmem
Activate with: source /tmp/mech-langmem/bin/activate
Using Python 3.12.8 environment at: /private/tmp/mech-langmem
Resolved 48 packages in 2.11s
   Building langmem @ file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/langmem
      Built langmem @ file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/langmem
Prepared 24 packages in 1.41s
Installed 48 packages in 127ms
 + annotated-types==0.7.0
 + anthropic==0.116.0
 + anyio==4.14.1
 + certifi==2026.6.17
 + charset-normalizer==3.4.7
 + distro==1.9.0
 + docstring-parser==0.18.0
 + dydantic==0.0.8
 + h11==0.16.0
 + httpcore==1.0.9
 + httpx==0.28.1
 + idna==3.18
 + jiter==0.16.0
 + jsonpatch==1.33
 + jsonpointer==3.1.1
 + langchain==1.3.11
 + langchain-anthropic==1.4.8
 + langchain-core==1.4.8
 + langchain-openai==1.3.3
 + langchain-protocol==0.0.18
 + langgraph==1.2.7
 + langgraph-checkpoint==4.1.1
 + langgraph-prebuilt==1.1.0
 + langgraph-sdk==0.4.2
 + langmem==0.0.30 (from file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/langmem)
 + langsmith==0.9.7
 + openai==2.44.0
 + orjson==3.11.9
 + ormsgpack==1.12.2
 + packaging==26.2
 + pydantic==2.13.4
 + pydantic-core==2.46.4
 + pyyaml==6.0.3
 + regex==2026.6.28
 + requests==2.34.2
 + requests-toolbelt==1.0.0
 + sniffio==1.3.1
 + tenacity==9.1.4
 + tiktoken==0.13.0
 + tqdm==4.68.3
 + trustcall==0.0.39
 + typing-extensions==4.16.0
 + typing-inspection==0.4.2
 + urllib3==2.7.0
 + uuid-utils==0.16.2
 + websockets==15.0.1
 + xxhash==3.8.0
 + zstandard==0.25.0
```

结构验收命令：

```bash
rg -c '^## [1-6]\. ' docs/workstreams/ws02-phase1-matrix/audits/mechanism-langmem.md
```

实际输出：

```text
6
```

源码证据计数命令：

```bash
rg -c '证据：`' docs/workstreams/ws02-phase1-matrix/audits/mechanism-langmem.md
```

实际输出：

```text
29
```

格式与主环境依赖检查命令：

```bash
git diff --check -- docs/workstreams/ws02-phase1-matrix/audits/mechanism-langmem.md docs/workstreams/ws02-phase1-matrix/plan-track-a2-method-mechanism.md
git status --short -- pyproject.toml uv.lock .venv
```

实际输出：

```text
```

### mechanism-simplemem.md

完成时间：2026-07-05 20:59 CST

官方 editable 隔离试装命令：

```bash
rm -rf /tmp/mech-simplemem && uv venv /tmp/mech-simplemem && uv pip install --python /tmp/mech-simplemem/bin/python -e third_party/methods/SimpleMem
```

实际输出：

```text
Using CPython 3.12.8 interpreter at: /Library/Frameworks/Python.framework/Versions/3.12/bin/python3
Creating virtual environment at: /tmp/mech-simplemem
Activate with: source /tmp/mech-simplemem/bin/activate
Using Python 3.12.8 environment at: /private/tmp/mech-simplemem
Resolved 83 packages in 3.89s
   Building simplemem @ file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/SimpleMem
      Built simplemem @ file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/SimpleMem
Downloading open-clip-torch (1.5MiB)
Downloading soundfile (1.1MiB)
Downloading timm (2.5MiB)
Downloading tantivy (7.9MiB)
Downloading lancedb (50.2MiB)
Downloading torchvision (1.8MiB)
   Building llvmlite==0.36.0
  × Failed to build `llvmlite==0.36.0`
  ├─▶ The build backend returned an error
  ╰─▶ Call to `setuptools.build_meta:__legacy__.build_wheel` failed (exit
      status: 1)

      [stderr]
      /Users/wz/.cache/uv/builds-v0/.tmpMobMVV/lib/python3.12/site-packages/setuptools/_vendor/wheel/bdist_wheel.py:4:
      FutureWarning: The 'wheel' package is no longer the canonical location
      of the 'bdist_wheel' command, and will be removed in a future release.
      Please update to setuptools v70.1 or later which contains an integrated
      version of this command.
        warn(
      Traceback (most recent call last):
        File "<string>", line 14, in <module>
        File
      "/Users/wz/.cache/uv/builds-v0/.tmpMobMVV/lib/python3.12/site-packages/setuptools/build_meta.py",
      line 333, in get_requires_for_build_wheel
          return self._get_build_requires(config_settings, requirements=[])
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        File
      "/Users/wz/.cache/uv/builds-v0/.tmpMobMVV/lib/python3.12/site-packages/setuptools/build_meta.py",
      line 301, in _get_build_requires
          self.run_setup()
        File
      "/Users/wz/.cache/uv/builds-v0/.tmpMobMVV/lib/python3.12/site-packages/setuptools/build_meta.py",
      line 520, in run_setup
          super().run_setup(setup_script=setup_script)
        File
      "/Users/wz/.cache/uv/builds-v0/.tmpMobMVV/lib/python3.12/site-packages/setuptools/build_meta.py",
      line 317, in run_setup
          exec(code, locals())
        File "<string>", line 55, in <module>
        File "<string>", line 52, in _guard_py_ver
      RuntimeError: Cannot install on Python version 3.12.8; only versions
      >=3.6,<3.10 are supported.

      hint: This usually indicates a problem with the package or the build
      environment.
  help: `llvmlite` (v0.36.0) was included because `simplemem` (v0.3.0) depends
        on `librosa` (v0.11.0) which depends on `numba` (v0.53.1) which
        depends on `llvmlite`
```

text path 核心依赖隔离复核命令：

```bash
uv pip install --python /tmp/mech-simplemem/bin/python 'openai>=1.0.0' 'pydantic>=2.0.0' 'lancedb>=0.4.0' 'sentence-transformers>=2.2.0' 'numpy>=1.24.0' 'dateparser>=1.1.0' 'pyarrow>=12.0.0' 'tantivy>=0.20.0'
uv pip install --python /tmp/mech-simplemem/bin/python --no-deps -e third_party/methods/SimpleMem
```

实际输出：

```text
Using Python 3.12.8 environment at: /private/tmp/mech-simplemem
Resolved 60 packages in 13ms
Downloading tantivy (7.9MiB)
Downloading lancedb (50.2MiB)
 Downloaded tantivy
 Downloaded lancedb
Prepared 2 packages in 9.32s
Installed 60 packages in 739ms
 + annotated-doc==0.0.4
 + annotated-types==0.7.0
 + anyio==4.14.1
 + certifi==2026.6.17
 + click==8.4.2
 + dateparser==1.4.1
 + deprecation==2.1.0
 + distro==1.9.0
 + filelock==3.29.5
 + fsspec==2026.6.0
 + h11==0.16.0
 + hf-xet==1.5.1
 + httpcore==1.0.9
 + httpx==0.28.1
 + huggingface-hub==1.22.0
 + idna==3.18
 + jinja2==3.1.6
 + jiter==0.16.0
 + joblib==1.5.3
 + lance-namespace==0.9.0
 + lance-namespace-urllib3-client==0.9.0
 + lancedb==0.34.0
 + markdown-it-py==4.2.0
 + markupsafe==3.0.3
 + mdurl==0.1.2
 + mpmath==1.3.0
 + narwhals==2.23.0
 + networkx==3.6.1
 + numpy==2.5.1
 + openai==2.44.0
 + packaging==26.2
 + pyarrow==24.0.0
 + pydantic==2.13.4
 + pydantic-core==2.46.4
 + pygments==2.20.0
 + python-dateutil==2.9.0.post0
 + pytz==2026.2
 + pyyaml==6.0.3
 + regex==2026.6.28
 + rich==15.0.0
 + safetensors==0.8.0
 + scikit-learn==1.9.0
 + scipy==1.18.0
 + sentence-transformers==5.6.0
 + setuptools==81.0.0
 + shellingham==1.5.4
 + six==1.17.0
 + sniffio==1.3.1
 + sympy==1.14.0
 + tantivy==0.26.0
 + threadpoolctl==3.6.0
 + tokenizers==0.22.2
 + torch==2.12.1
 + tqdm==4.68.3
 + transformers==5.13.0
 + typer==0.26.8
 + typing-extensions==4.16.0
 + typing-inspection==0.4.2
 + tzlocal==5.4.4
 + urllib3==2.7.0
Using Python 3.12.8 environment at: /private/tmp/mech-simplemem
Resolved 1 package in 521ms
   Building simplemem @ file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/SimpleMem
      Built simplemem @ file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/SimpleMem
Prepared 1 package in 194ms
Installed 1 package in 2ms
 + simplemem==0.3.0 (from file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/SimpleMem)
```

结构验收命令：

```bash
rg -c '^## [1-6]\. ' docs/workstreams/ws02-phase1-matrix/audits/mechanism-simplemem.md
```

实际输出：

```text
6
```

源码证据计数命令：

```bash
rg -c '证据：`' docs/workstreams/ws02-phase1-matrix/audits/mechanism-simplemem.md
```

实际输出：

```text
33
```

格式与主环境依赖检查命令：

```bash
git diff --check -- docs/workstreams/ws02-phase1-matrix/audits/mechanism-simplemem.md docs/workstreams/ws02-phase1-matrix/plan-track-a2-method-mechanism.md
git status --short -- pyproject.toml uv.lock .venv
```

实际输出：

```text
```

### mechanism-memoryos.md

完成时间：2026-07-05 20:52 CST

官方 requirements 隔离试装命令：

```bash
rm -rf /tmp/mech-memoryos && uv venv /tmp/mech-memoryos && uv pip install --python /tmp/mech-memoryos/bin/python -r third_party/methods/MemoryOS-main/memoryos-pypi/requirements.txt
```

实际输出：

```text
Using CPython 3.12.8 interpreter at: /Library/Frameworks/Python.framework/Versions/3.12/bin/python3
Creating virtual environment at: /tmp/mech-memoryos
Activate with: source /tmp/mech-memoryos/bin/activate
Using Python 3.12.8 environment at: /private/tmp/mech-memoryos
  × No solution found when resolving dependencies:
  ╰─▶ Because only the following versions of faiss-gpu are available:
          faiss-gpu<=1.7.0
          faiss-gpu==1.7.1
          faiss-gpu==1.7.1.post1
          faiss-gpu==1.7.1.post2
          faiss-gpu==1.7.1.post3
          faiss-gpu==1.7.2
          faiss-gpu==1.14.3
      and faiss-gpu>=1.7.0,<=1.7.2 has no wheels with a matching Python ABI
      tag (e.g., `cp312`), we can conclude that faiss-gpu>=1.7.0,<=1.7.2
      cannot be used.
      And because faiss-gpu==1.14.3 has no wheels with a matching platform
      tag (e.g., `macosx_15_0_arm64`) and you require faiss-gpu>=1.7.0, we can
      conclude that your requirements are unsatisfiable.

      hint: Wheels are available for `faiss-gpu` (v1.14.3) on the following
      platforms: `manylinux_2_27_x86_64`, `manylinux_2_28_x86_64`

      hint: You require CPython 3.12 (`cp312`), but we only found wheels
      for `faiss-gpu` (v1.7.2) with the following Python ABI tags: `cp36m`,
      `cp37m`, `cp38`, `cp39`, `cp310`
```

CPU FAISS 替代复核命令：

```bash
uv pip install --python /tmp/mech-memoryos/bin/python 'numpy==1.24.*' 'sentence-transformers==5.0.0' 'transformers>=4.51.0' 'FlagEmbedding>=1.2.9' 'faiss-cpu>=1.7.0,<2.0.0' 'httpx[socks]' openai 'flask>=2.0.0,<3.0.0' 'python-dotenv>=0.19.0,<2.0.0' 'typing-extensions>=4.0.0,<5.0.0' 'regex>=2022.1.18'
```

实际输出：

```text
Using Python 3.12.8 environment at: /private/tmp/mech-memoryos
Resolved 79 packages in 5.96s
Downloading sentencepiece (1.2MiB)
Downloading transformers (11.4MiB)
Downloading faiss-cpu (5.7MiB)
Downloading lxml (8.2MiB)
 Downloaded sentencepiece
   Building pandas==2.1.0
 Downloaded faiss-cpu
 Downloaded lxml
   Building numpy==1.24.4
 Downloaded transformers
  × Failed to build `numpy==1.24.4`
  ├─▶ The build backend returned an error
  ╰─▶ Call to `setuptools.build_meta:__legacy__.build_wheel` failed (exit
      status: 1)

      [stderr]
      Traceback (most recent call last):
        File "<string>", line 8, in <module>
        File
      "/Users/wz/.cache/uv/builds-v0/.tmpVvtuIO/lib/python3.12/site-packages/setuptools/__init__.py",
      line 10, in <module>
          import distutils.core
      ModuleNotFoundError: No module named 'distutils'

      hint: `distutils` was removed from the standard library in Python 3.12.
      Consider adding a constraint (like `numpy >1.24.4`) to avoid building a
      version of `numpy` that depends on `distutils`.
```

Python 3.9 官方 requirements 复核命令：

```bash
rm -rf /tmp/mech-memoryos-py39 && uv venv --python /usr/bin/python3 /tmp/mech-memoryos-py39 && uv pip install --python /tmp/mech-memoryos-py39/bin/python -r third_party/methods/MemoryOS-main/memoryos-pypi/requirements.txt
```

实际输出：

```text
Using CPython 3.9.6 interpreter at: /Library/Developer/CommandLineTools/usr/bin/python3
warning: The requested interpreter resolved to Python 3.9.6, which is incompatible with the project's Python requirement: `>=3.11` (from `project.requires-python`)
Creating virtual environment at: /tmp/mech-memoryos-py39
Activate with: source /tmp/mech-memoryos-py39/bin/activate
Using Python 3.9.6 environment at: /private/tmp/mech-memoryos-py39
  × No solution found when resolving dependencies:
  ╰─▶ Because only the following versions of faiss-gpu are available:
          faiss-gpu<=1.7.0
          faiss-gpu==1.7.1
          faiss-gpu==1.7.1.post1
          faiss-gpu==1.7.1.post2
          faiss-gpu==1.7.1.post3
          faiss-gpu==1.7.2
          faiss-gpu==1.14.3
      and faiss-gpu>=1.7.0,<=1.7.2 has no wheels with a matching
      platform tag (e.g., `macosx_15_0_arm64`), we can conclude that
      faiss-gpu>=1.7.0,<=1.7.2 cannot be used.
      And because faiss-gpu==1.14.3 has no wheels with a matching Python
      implementation tag (e.g., `cp39`) and you require faiss-gpu>=1.7.0, we
      can conclude that your requirements are unsatisfiable.

      hint: You require CPython 3.9 (`cp39`), but we only found wheels for
      `faiss-gpu` (v1.14.3) with the following Python implementation tag:
      `cp310`

      hint: Wheels are available for `faiss-gpu` (v1.7.2) on the following
      platforms: `manylinux_2_17_x86_64`, `manylinux2014_x86_64`
```

结构验收命令：

```bash
rg -c '^## [1-7]\. ' docs/workstreams/ws02-phase1-matrix/audits/mechanism-memoryos.md
```

实际输出：

```text
7
```

源码证据计数命令：

```bash
rg -c '证据：`' docs/workstreams/ws02-phase1-matrix/audits/mechanism-memoryos.md
```

实际输出：

```text
34
```

格式与主环境依赖检查命令：

```bash
git diff --check -- docs/workstreams/ws02-phase1-matrix/audits/mechanism-memoryos.md docs/workstreams/ws02-phase1-matrix/plan-track-a2-method-mechanism.md
git status --short -- pyproject.toml uv.lock .venv
```

实际输出：

```text
```

### mechanism-amem.md

完成时间：2026-07-05 21:24 CST

隔离试装命令：

```bash
rm -rf /tmp/mech-amem && uv venv /tmp/mech-amem && uv pip install --python /tmp/mech-amem/bin/python -r third_party/methods/A-mem/requirements.txt
```

实际输出：

```text
Using CPython 3.12.8 interpreter at: /Library/Frameworks/Python.framework/Versions/3.12/bin/python3
Creating virtual environment at: /tmp/mech-amem
Activate with: source /tmp/mech-amem/bin/activate
Using Python 3.12.8 environment at: /private/tmp/mech-amem
WARN Fixing invalid version specifier by removing stray quotes (before: `>= '2.7'`; after: `>= 2.7`)
WARN Fixing invalid version specifier by removing stray quotes (before: `>= '2.7'`; after: `>= 2.7`)
Resolved 89 packages in 2.25s
   Building rouge-score==0.1.2
      Built rouge-score==0.1.2
Downloading litellm (15.9MiB)
Downloading pillow (4.6MiB)
Downloading matplotlib (8.8MiB)
Downloading torch (83.9MiB)
Downloading transformers (11.0MiB)
Downloading scipy (19.5MiB)
Downloading hf-xet (3.7MiB)
 Downloaded hf-xet
 Downloaded pillow
 Downloaded matplotlib
 Downloaded transformers
 Downloaded litellm
 Downloaded scipy
 Downloaded torch
Prepared 24 packages in 20.08s
Installed 89 packages in 665ms
 + absl-py==2.5.0
 + aiohappyeyeballs==2.7.1
 + aiohttp==3.14.1
 + aiosignal==1.4.0
 + annotated-doc==0.0.4
 + annotated-types==0.7.0
 + anyio==4.14.1
 + attrs==26.1.0
 + bert-score==0.3.13
 + certifi==2026.6.17
 + charset-normalizer==3.4.7
 + click==8.4.2
 + contourpy==1.3.3
 + cycler==0.12.1
 + distro==1.9.0
 + fastuuid==0.14.0
 + filelock==3.29.5
 + fonttools==4.63.0
 + frozenlist==1.8.0
 + fsspec==2026.6.0
 + h11==0.16.0
 + hf-xet==1.5.1
 + httpcore==1.0.9
 + httpx==0.28.1
 + huggingface-hub==1.22.0
 + idna==3.18
 + importlib-metadata==8.9.0
 + iniconfig==2.3.0
 + jinja2==3.1.6
 + jiter==0.16.0
 + joblib==1.5.3
 + jsonschema==4.26.0
 + jsonschema-specifications==2025.9.1
 + kiwisolver==1.5.0
 + litellm==1.91.0
 + markdown-it-py==4.2.0
 + markupsafe==3.0.3
 + matplotlib==3.11.0
 + mdurl==0.1.2
 + mpmath==1.3.0
 + multidict==6.7.1
 + narwhals==2.23.0
 + networkx==3.6.1
 + nltk==3.9.4
 + numpy==2.5.1
 + ollama==0.6.2
 + openai==2.44.0
 + packaging==26.2
 + pandas==3.0.3
 + pathlib==1.0.1
 + pillow==12.3.0
 + pluggy==1.6.0
 + propcache==0.5.2
 + pydantic==2.13.4
 + pydantic-core==2.46.4
 + pygments==2.20.0
 + pyparsing==3.3.2
 + pytest==9.1.1
 + python-dateutil==2.9.0.post0
 + python-dotenv==1.2.2
 + pyyaml==6.0.3
 + rank-bm25==0.2.2
 + referencing==0.37.0
 + regex==2026.6.28
 + requests==2.34.2
 + rich==15.0.0
 + rouge-score==0.1.2
 + rpds-py==2026.6.3
 + safetensors==0.8.0
 + scikit-learn==1.9.0
 + scipy==1.18.0
 + sentence-transformers==5.6.0
 + setuptools==81.0.0
 + shellingham==1.5.4
 + six==1.17.0
 + sniffio==1.3.1
 + sympy==1.14.0
 + threadpoolctl==3.6.0
 + tiktoken==0.13.0
 + tokenizers==0.22.2
 + torch==2.12.1
 + tqdm==4.68.3
 + transformers==5.13.0
 + typer==0.26.8
 + typing-extensions==4.16.0
 + typing-inspection==0.4.2
 + urllib3==2.7.0
 + yarl==1.24.2
 + zipp==4.1.0
```

结构验收命令：

```bash
rg -c '^## [1-7]\. ' docs/workstreams/ws02-phase1-matrix/audits/mechanism-amem.md
```

实际输出：

```text
7
```

源码证据计数命令：

```bash
rg -c '证据：`' docs/workstreams/ws02-phase1-matrix/audits/mechanism-amem.md
```

实际输出：

```text
31
```

格式与主环境依赖检查命令：

```bash
git diff --check -- docs/workstreams/ws02-phase1-matrix/audits/mechanism-amem.md docs/workstreams/ws02-phase1-matrix/plan-track-a2-method-mechanism.md
git status --short -- pyproject.toml uv.lock .venv
```

实际输出：

```text
```

### mechanism-lightmem.md

完成时间：2026-07-05 21:03 CST

隔离试装命令：

```bash
rm -rf /tmp/mech-lightmem && uv venv /tmp/mech-lightmem && uv pip install --python /tmp/mech-lightmem/bin/python -e third_party/methods/LightMem
```

实际输出：

```text
Using CPython 3.12.8 interpreter at: /Library/Frameworks/Python.framework/Versions/3.12/bin/python3
Creating virtual environment at: /tmp/mech-lightmem
Activate with: source /tmp/mech-lightmem/bin/activate
Using Python 3.12.8 environment at: /private/tmp/mech-lightmem
WARN Fixing invalid version specifier by removing star after comparison operator other than equal and not equal (before: `>=3.5.*`; after: `>=3.5`)
WARN Fixing invalid version specifier by removing star after comparison operator other than equal and not equal (before: `>=3.5.*`; after: `>=3.5`)
WARN Fixing invalid version specifier by removing star after comparison operator other than equal and not equal (before: `>=3.5.*`; after: `>=3.5`)
WARN Fixing invalid version specifier by removing star after comparison operator other than equal and not equal (before: `>=3.5.*`; after: `>=3.5`)
WARN Fixing invalid version specifier by removing star after comparison operator other than equal and not equal (before: `>=3.5.*`; after: `>=3.5`)
WARN Fixing invalid version specifier by removing star after comparison operator other than equal and not equal (before: `>=3.5.*`; after: `>=3.5`)
Resolved 59 packages in 1.48s
   Building lightmem @ file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/LightMem
Downloading networkx (1.6MiB)
Downloading tokenizers (2.8MiB)
Downloading nltk (1.4MiB)
Downloading numpy (4.8MiB)
Downloading scikit-learn (8.2MiB)
Downloading pillow (4.5MiB)
Downloading pydantic-core (1.8MiB)
Downloading scipy (21.4MiB)
Downloading torch (70.2MiB)
Downloading transformers (11.4MiB)
Downloading grpcio (10.9MiB)
Downloading hf-xet (2.5MiB)
      Built lightmem @ file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/LightMem
 Downloaded nltk
 Downloaded networkx
 Downloaded pydantic-core
 Downloaded hf-xet
 Downloaded tokenizers
 Downloaded pillow
 Downloaded numpy
 Downloaded scikit-learn
 Downloaded grpcio
 Downloaded transformers
 Downloaded scipy
 Downloaded torch
Prepared 36 packages in 14.77s
Installed 59 packages in 450ms
 + accelerate==1.10.1
 + annotated-types==0.7.0
 + anyio==4.11.0
 + certifi==2025.10.5
 + charset-normalizer==3.4.3
 + click==8.3.0
 + distro==1.9.0
 + filelock==3.20.0
 + fsspec==2025.9.0
 + grpcio==1.75.1
 + h11==0.16.0
 + h2==4.3.0
 + hf-xet==1.1.10
 + hpack==4.1.0
 + httpcore==1.0.9
 + httpx==0.28.1
 + huggingface-hub==0.35.3
 + hyperframe==6.1.0
 + idna==3.10
 + jinja2==3.1.6
 + jiter==0.11.0
 + joblib==1.5.2
 + lightmem==0.1.0 (from file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/LightMem)
 + llmlingua==0.2.2
 + markupsafe==3.0.3
 + mpmath==1.3.0
 + networkx==3.4.2
 + nltk==3.9.2
 + numpy==2.2.6
 + openai==2.3.0
 + packaging==25.0
 + pillow==11.3.0
 + portalocker==3.2.0
 + protobuf==6.32.1
 + psutil==7.1.0
 + pydantic==2.12.0
 + pydantic-core==2.41.1
 + pysocks==1.7.1
 + pyyaml==6.0.3
 + qdrant-client==1.15.1
 + rank-bm25==0.2.2
 + regex==2025.9.18
 + requests==2.32.5
 + safetensors==0.6.2
 + scikit-learn==1.7.2
 + scipy==1.15.3
 + sentence-transformers==5.1.1
 + setuptools==83.0.0
 + sniffio==1.3.1
 + sympy==1.14.0
 + threadpoolctl==3.6.0
 + tiktoken==0.12.0
 + tokenizers==0.22.1
 + torch==2.8.0
 + tqdm==4.67.1
 + transformers==4.57.0
 + typing-extensions==4.15.0
 + typing-inspection==0.4.2
 + urllib3==2.5.0
warning: `transformers==4.57.0` is yanked (reason: "Error in the setup causing installation issues")
```

结构验收命令：

```bash
rg -c '^## [1-7]\. ' docs/workstreams/ws02-phase1-matrix/audits/mechanism-lightmem.md
```

实际输出：

```text
7
```

源码证据计数命令：

```bash
rg -c '证据：`' docs/workstreams/ws02-phase1-matrix/audits/mechanism-lightmem.md
```

实际输出：

```text
34
```

格式与主环境依赖检查命令：

```bash
git diff --check -- docs/workstreams/ws02-phase1-matrix/audits/mechanism-lightmem.md docs/workstreams/ws02-phase1-matrix/plan-track-a2-method-mechanism.md
git status --short -- pyproject.toml uv.lock .venv
```

实际输出：

```text
```
