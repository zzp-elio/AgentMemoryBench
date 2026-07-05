# 2026-06-11 项目清理交接

## 清理边界

本次采用保守清理方案，不删除源码、benchmark、模型、第三方 method、论文材料或有效测试。

完整保留并设为受保护实验资产：

```text
outputs/memoryos-locomo-full-20260603/
```

清理前后均校验以下文件 SHA256：

```text
summary.json      6cca3fbf0dd3c77d215b5fbe704de50d674a989ecaef685b498bbbdb90a74818
predictions.jsonl 305841f49159995c874e8d1c5995c91923841e207fbac28af0473d104b8320c9
scores.jsonl      960bc172acb9cbe46c29b228bcfec08d1c4accbcfc90fa75593f43ce9020c749
```

## 已删除

- `outputs/` 下除正式全量实验外的 debug、import smoke、mem0 smoke、MemoryOS 手动
  smoke、unit-test 输出和论文临时文本。
- 项目范围内的 `.pytest_cache`、`__pycache__`、`.pyc`、`.pyo` 和 `.DS_Store`。
- `.venv` 未清理，避免无收益地破坏当前可复现环境。

## 已归档

过时的 `docs/refactor-plan.md` 已移动到：

```text
old/2026-06-11-project-cleanup/docs/refactor-plan.md
```

该文档仍记录 69 个测试和未来接入 mem0，已不符合当前项目状态，因此不能继续作为事实来源。

## 测试审计结论

当前 17 个 `tests/test_*.py` 均覆盖现存源码或关键契约，没有安全删除项。
`tests/test_memoryos_locomo_full_runner.py` 虽然较大，但保护断点续跑、实验产物一致性、
失败恢复和私有数据边界；后续可以拆分，不能直接删除。

## 清理后验证

- 受保护实验的 `summary.json`、`predictions.jsonl`、`scores.jsonl` 哈希全部匹配。
- `outputs/` 只剩 `outputs/memoryos-locomo-full-20260603/`，约 97MB。
- 使用 `PYTHONDONTWRITEBYTECODE=1` 和 pytest `no:cacheprovider` 运行安全全量测试：
  163 passed、1 API smoke deselected、4 subtests passed。
- 13 条 warning 均来自第三方 MemoryOS 官方 `eval/utils.py` 的无效转义字符串；未修改
  第三方源码。
- 验证完成后，`.venv` 外生成缓存数量仍为 0。

## 下一步

清理完成后，下一项产品工作是对齐 Phase E：MemoryOS 在 LongMemEval 上完成单样本
LLM judge 闭环。开始编码前必须先完成设计确认。
