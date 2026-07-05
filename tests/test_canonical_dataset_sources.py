"""校验 canonical 数据集副本与官方 benchmark 源文件完全一致。

本模块只做离线真实性核验，不访问网络，也不修改第三方仓库内容。
覆盖范围包括：
- LoCoMo 单文件副本；
- LongMemEval S/M 单文件副本；
- HaluMem Medium/Long 单文件副本；
- Mem-Gallery 的 dialog/image/prompts 三棵目录树。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


ROOT = Path(__file__).resolve().parents[1]
CHUNK_SIZE = 1024 * 1024

DATASET_FILE_PAIRS = (
    (
        "data/locomo/locomo10.json",
        "third_party/benchmarks/locomo-main/data/locomo10.json",
    ),
    (
        "data/longmemeval/longmemeval_s_cleaned.json",
        "third_party/benchmarks/LongMemEval-main/data/longmemeval_s_cleaned.json",
    ),
    (
        "data/longmemeval/longmemeval_m_cleaned.json",
        "third_party/benchmarks/LongMemEval-main/data/longmemeval_m_cleaned.json",
    ),
    (
        "data/halumem/HaluMem-Medium.jsonl",
        "third_party/benchmarks/HaluMem-main/data/HaluMem-Medium.jsonl",
    ),
    (
        "data/halumem/HaluMem-Long.jsonl",
        "third_party/benchmarks/HaluMem-main/data/HaluMem-Long.jsonl",
    ),
)

TREE_PAIRS = (
    (
        "data/mem_gallery/dialog",
        "third_party/benchmarks/Mem-Gallery-main/benchmark/data/dialog",
    ),
    (
        "data/mem_gallery/image",
        "third_party/benchmarks/Mem-Gallery-main/benchmark/data/image",
    ),
    (
        "data/mem_gallery/prompts",
        "third_party/benchmarks/Mem-Gallery-main/benchmark/prompt",
    ),
)


def _sha256_file(path: Path) -> str:
    """流式读取文件并返回其 SHA-256 摘要。

    输入:
        path: 需要校验的文件路径。

    输出:
        str: 64 位十六进制 SHA-256 字符串。
    """

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_tree_fingerprints(root: Path) -> dict[str, str]:
    """收集目录树下所有文件的相对路径与 SHA-256。

    输入:
        root: 需要遍历的目录根。

    输出:
        dict[str, str]: 以相对路径为 key、文件 SHA-256 为 value 的映射。
    """

    fingerprints: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative_path = path.relative_to(root).as_posix()
        fingerprints[relative_path] = _sha256_file(path)
    return fingerprints


@pytest.mark.parametrize("canonical_rel, official_rel", DATASET_FILE_PAIRS)
def test_canonical_dataset_file_sha256_matches_official_copy(
    canonical_rel: str,
    official_rel: str,
) -> None:
    """逐对校验核心文本数据文件的字节内容是否与官方副本一致。"""

    canonical_path = ROOT / canonical_rel
    official_path = ROOT / official_rel

    assert canonical_path.is_file(), f"canonical 文件不存在: {canonical_path}"
    assert official_path.is_file(), f"official 文件不存在: {official_path}"
    assert (
        _sha256_file(canonical_path) == _sha256_file(official_path)
    ), f"SHA-256 不一致: {canonical_path} vs {official_path}"


@pytest.mark.parametrize("canonical_rel, official_rel", TREE_PAIRS)
def test_mem_gallery_tree_paths_counts_and_sha256_match_official_copy(
    canonical_rel: str,
    official_rel: str,
) -> None:
    """逐树校验 Mem-Gallery 的相对路径集合、文件数与逐文件 SHA-256。"""

    canonical_root = ROOT / canonical_rel
    official_root = ROOT / official_rel

    assert canonical_root.is_dir(), f"canonical 目录不存在: {canonical_root}"
    assert official_root.is_dir(), f"official 目录不存在: {official_root}"

    canonical_files = _collect_tree_fingerprints(canonical_root)
    official_files = _collect_tree_fingerprints(official_root)

    canonical_paths = set(canonical_files)
    official_paths = set(official_files)

    assert len(canonical_files) == len(
        official_files
    ), f"文件数不一致: {canonical_root}={len(canonical_files)} vs {official_root}={len(official_files)}"
    assert (
        canonical_paths == official_paths
    ), f"相对路径集合不一致: only_in_canonical={sorted(canonical_paths - official_paths)}; only_in_official={sorted(official_paths - canonical_paths)}"

    for relative_path in sorted(canonical_paths):
        assert (
            canonical_files[relative_path] == official_files[relative_path]
        ), f"文件 SHA-256 不一致: {canonical_root / relative_path} vs {official_root / relative_path}"


def test_membench_semantic_directory_exists() -> None:
    """MemBench 语义目录必须存在；原始数据已于 2026-07 落位，允许非空。

    2026-07-05 起 `data/membench` 已存放用户收集的 MemBench 原始数据
    （`Membenchdata/data2test/...`），旧的"空目录占位"断言随之作废。
    canonical 结构核验与官方副本比对属于 MemBench adapter 接入任务，
    届时应仿照 LoCoMo/LongMemEval 的 SHA-256 比对测试补齐。
    """

    membench_root = ROOT / "data" / "membench"

    assert membench_root.is_dir(), f"MemBench 语义目录不存在: {membench_root}"
