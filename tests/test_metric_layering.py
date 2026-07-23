"""指标纯内核与 evaluator 编排层的依赖方向回归门。"""

from __future__ import annotations

import ast
from pathlib import Path

from memory_benchmark.evaluators import answer_text, retrieval_metrics
from memory_benchmark.metrics import retrieval, text


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_METRICS_ROOT = _PROJECT_ROOT / "src" / "memory_benchmark" / "metrics"
_FORBIDDEN_PREFIXES = (
    "memory_benchmark.benchmark_adapters",
    "memory_benchmark.evaluators",
    "memory_benchmark.methods",
    "memory_benchmark.storage",
)


def test_metric_layer_has_no_reverse_dependency_on_orchestration_layers() -> None:
    """纯指标层不得反向 import evaluator、adapter、method 或 artifact storage。"""

    violations: list[str] = []
    for path in sorted(_METRICS_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.startswith(_FORBIDDEN_PREFIXES):
                    violations.append(f"{path.name}:{node.lineno}: {name}")
    assert violations == []


def test_legacy_metric_import_paths_reexport_canonical_objects() -> None:
    """目录迁移保留对象级兼容，旧消费者不会加载第二份公式。"""

    assert answer_text.normalize_answer is text.normalize_answer
    assert answer_text.normalized_tokens is text.normalized_tokens
    assert retrieval_metrics.recall_at_k is retrieval.recall_at_k
    assert retrieval_metrics.top_k_source_ids is retrieval.top_k_source_ids
