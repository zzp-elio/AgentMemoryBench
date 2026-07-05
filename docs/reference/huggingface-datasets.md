# Hugging Face Dataset 发布流程

本项目把代码放在 GitHub，把大型 benchmark runtime data 放在 Hugging Face Dataset repo。
这样可以避免 GitHub 仓库膨胀，同时保留数据版本、校验和和下载入口。

## 推荐仓库

推荐创建 public dataset repo，便于其他实验使用者直接下载：

```text
BuptZZP/agentmemorybench-data
```

当前公开地址：

```text
https://huggingface.co/datasets/BuptZZP/agentmemorybench-data
```

当前已上传 revision：

```text
0eb625cd4c7cecca7951c7c7feae4211861f979d
```

注意：不同 benchmark 的 redistribution license 仍需要持续核验。公开仓库便于协作和下载，
但后续必须补齐 license、citation 和来源说明。

## 本地目录约定

项目运行时数据入口仍然是根目录 `data/`：

```text
data/
  locomo/
  longmemeval/
  halumem/
  mem_gallery/
  membench/
  BEAM/
```

`data/` 不进入 Git。Hugging Face 上传包由脚本从 `data/` 生成，输出到
`tmp/hf_dataset_bundle/`。

## 生成上传包

```bash
uv run python scripts/prepare_hf_dataset_bundle.py \
  --source data \
  --output tmp/hf_dataset_bundle \
  --repo-id BuptZZP/agentmemorybench-data \
  --link-mode hardlink
```

说明：

- 默认使用 hardlink，避免本地重复占用 4GB+ 空间；如果文件系统不支持 hardlink，会回退复制。
- 脚本会跳过 `.DS_Store`、`__pycache__`、`.git` 等噪声文件。
- 输出目录不能等于 `data/`，也不能位于 `data/` 内部，脚本会强校验。

生成结果：

```text
tmp/hf_dataset_bundle/
  README.md
  manifest.json
  checksums.sha256
  locomo/README.md
  longmemeval/README.md
  halumem/README.md
  mem_gallery/README.md
  membench/README.md
  BEAM/README.md
  ...
```

`manifest.json` 和 `checksums.sha256` 只记录真实数据文件，不把自动生成的 README、manifest
和 checksum 文件算作 dataset 文件。

## 登录 Hugging Face

当前机器需要先登录：

```bash
hf auth login
hf auth whoami
```

也可以用环境变量：

```bash
export HF_TOKEN=<your_huggingface_token>
```

不要把 token 写入 `.env` 以外的文档、日志或命令输出。

## 创建 public dataset repo

```bash
hf repos create BuptZZP/agentmemorybench-data \
  --type dataset \
  --exist-ok
```

## 上传

`data/` 当前体量较大，使用可恢复的大目录上传：

```bash
hf upload-large-folder \
  BuptZZP/agentmemorybench-data \
  tmp/hf_dataset_bundle \
  --type dataset \
  --num-workers 8
```

如果只是上传少量文件或 README 修订，可以使用普通上传：

```bash
hf upload \
  BuptZZP/agentmemorybench-data \
  tmp/hf_dataset_bundle/README.md \
  README.md \
  --type dataset \
  --commit-message "docs: update dataset card"
```

## 验证上传

```bash
hf datasets info BuptZZP/agentmemorybench-data

hf download BuptZZP/agentmemorybench-data \
  --type dataset \
  --include "locomo/**" \
  --local-dir /tmp/agentmemorybench-data-test
```

如果需要检查 parquet viewer，不是所有原始 JSON/JSONL 文件都会自动生成可预览 parquet。
当前项目的核心目标是把原始 runtime data 固定到 HF repo，并由本项目 adapter 读取。

## 本项目下载方式

完整下载：

```bash
hf download BuptZZP/agentmemorybench-data \
  --type dataset \
  --local-dir data
```

只下载 LoCoMo：

```bash
hf download BuptZZP/agentmemorybench-data \
  --type dataset \
  --include "locomo/**" \
  --local-dir data
```

下载后保持目录结构不变，adapter 才能按默认路径读取。

## 更新数据

1. 修改本地 `data/`。
2. 重新生成 bundle。
3. 检查 `tmp/hf_dataset_bundle/manifest.json` 和 `checksums.sha256`。
4. 用 `hf upload-large-folder` 上传。
5. 在本项目文档中记录数据版本变化。

每次正式实验都应记录 Hugging Face dataset revision 或 commit hash，避免后续数据漂移影响
可复现性。
