# 2026-06-17 Hugging Face Dataset Bundle 交接

## 本次任务

用户确认将根目录 `data/` 下的大型 runtime dataset 放到 Hugging Face Dataset repo。当前
repo 目标已从 `zzp/agentmemorybench-data` 改为 `BuptZZP/agentmemorybench-data`，并按
public dataset repo 上传，便于其他人下载。

## 已完成

- 新增 `scripts/prepare_hf_dataset_bundle.py`：
  - 从 `data/` 生成 `tmp/hf_dataset_bundle/`。
  - 默认使用 hardlink，减少本地重复磁盘占用。
  - 跳过 `.DS_Store`、`__pycache__`、`.git` 等噪声。
  - 自动生成根 `README.md`、每个顶层 dataset 的 `README.md`、`manifest.json` 和
    `checksums.sha256`。
  - `manifest.json` 不写入本机绝对路径。
  - 强校验输出目录不能等于 `data/`、不能位于 `data/` 内部、不能是 `data/` 的上级目录。
- 新增 `tests/test_hf_dataset_bundle.py`，覆盖 bundle 生成和危险路径拒绝。
- 新增 `docs/huggingface-datasets.md`，固定 HF 登录、创建 public dataset repo、上传、
  验证和下载命令。
- README 和 AGENTS 已加入 HF dataset workflow 导航。

## 本地生成结果

已在真实 `data/` 上运行：

```bash
uv run python scripts/prepare_hf_dataset_bundle.py \
  --source data \
  --output tmp/hf_dataset_bundle \
  --repo-id BuptZZP/agentmemorybench-data \
  --link-mode hardlink
```

结果：

- 输出目录：`tmp/hf_dataset_bundle/`
- 数据文件数：1537
- 数据总字节数：4950548322
- 顶层 dataset：`BEAM`、`halumem`、`locomo`、`longmemeval`、`mem_gallery`、`membench`

`tmp/` 已在 `.gitignore` 中，不会进入 Git。

## Hugging Face 上传结果

已创建并上传 public dataset repo：

```text
https://huggingface.co/datasets/BuptZZP/agentmemorybench-data
```

Hub API 验证结果：

```text
id: BuptZZP/agentmemorybench-data
private: false
sha: 0eb625cd4c7cecca7951c7c7feae4211861f979d
lastModified: 2026-06-17T08:24:29.000Z
```

无认证下载验证：

```bash
curl -L -s -o /tmp/agentmemorybench-hf-readme.md \
  -w "%{http_code} %{size_download}\n" \
  https://huggingface.co/datasets/BuptZZP/agentmemorybench-data/resolve/main/README.md

curl -L -s -o /tmp/agentmemorybench-hf-manifest.json \
  -w "%{http_code} %{size_download}\n" \
  https://huggingface.co/datasets/BuptZZP/agentmemorybench-data/resolve/main/manifest.json
```

两者均返回 HTTP 200；远端 `manifest.json` 显示 `repo_id` 为
`BuptZZP/agentmemorybench-data`，`total_files=1537`，`total_bytes=4950548322`。

## 验证

已运行：

```bash
uv run pytest tests/test_hf_dataset_bundle.py tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests scripts
du -sh tmp/hf_dataset_bundle
rg -n "/Users/wz" tmp/hf_dataset_bundle/README.md tmp/hf_dataset_bundle/manifest.json tmp/hf_dataset_bundle/*/README.md || true
```

结果：

- focused 测试：`7 passed`
- `compileall`：exit 0
- bundle 大小：`4.6G`
- 生成的 HF README/manifest/子 README 未发现 `/Users/wz` 本地路径

## 后续重新上传命令

用户登录 HF 后执行：

```bash
hf auth login
hf repos create BuptZZP/agentmemorybench-data --type dataset --exist-ok
hf upload-large-folder BuptZZP/agentmemorybench-data tmp/hf_dataset_bundle --type dataset --num-workers 8
```

公开仓库便于其他人下载，但后续仍需逐个核验上游 benchmark license 和 redistribution 权限。
