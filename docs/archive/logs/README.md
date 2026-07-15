# 日志规范

本目录记录开发期主题日志，不存放运行期 JSONL 或模型输出。

## 命名

日志文件使用：

```text
YYYY-MM-DD-<phase-or-topic>.md
```

示例：

```text
2026-06-03-phase1-runner-review.md
2026-06-03-locomo-adapter-debug.md
```

文件名里建议包含 `phase` 或明确主题，便于后续查找。

## 内容

每篇日志至少包含：

- 日期。
- 执行内容。
- 结论来源。
- 关键发现。
- 未解决问题。
- 下一步。

## 与 project-log 的关系

`project-log` 用作总索引和里程碑摘要；本目录保存更细的主题记录。当前压缩恢复以活跃
workstream README 顶部“恢复胶囊”为热层、`docs/archive/handoffs/` 为历史冷层；本文
不保存动态断点。
