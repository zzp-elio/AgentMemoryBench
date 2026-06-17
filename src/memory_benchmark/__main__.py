"""支持通过 `python -m memory_benchmark` 启动统一 CLI。"""

from memory_benchmark.cli.main import main


if __name__ == "__main__":
    raise SystemExit(main())
