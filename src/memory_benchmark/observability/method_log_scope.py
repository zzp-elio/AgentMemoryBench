"""run 级 method logger 落盘作用域。

本模块给一次 benchmark run 在 root logger 上挂一个 run-scoped 的
``FileHandler``，把 method 自己 logger 打的 INFO/WARNING（如 LightMem
``LightMemory`` 的 "Created N MemoryEntry objects"、segment/token 统计、
"No entries found" 警告等）落盘到 ``logs/method.log``，让成本/异常可事后追溯。

设计要点（与 ws04 卡 Y 一致）：

- **run 起挂、run 止摘**：用 ``with method_log_scope(logs_dir)`` 包住 run 主体，
  ``_MethodLogScope.__exit__`` 在正常退出与异常下都 ``removeHandler`` 并 ``close``，
  避免 ① handler 泄漏（重复 run / 并行 run 累积）、② 跨 run 串写。
- **不改终端行为**：只额外落一份文件，不动 method / 第三方现有 ConsoleHandler。
- **降噪**：``_NoisyThirdPartyFilter`` 过滤掉已知刷屏且无诊断价值的第三方
  namespace（transformers、urllib3、httpx、sentence_transformers）的 INFO；
  method 自身 logger 与框架 INFO 保留。
- **run 级而非 conversation 级**：handler 只挂一次到 root logger，并行
  conversation（同进程线程）下 Python logging 本身线程安全，无需额外锁。
- **INFO level + 时间戳格式**：``%(asctime)s %(name)s %(levelname)s %(message)s``。

线程安全说明：Python logging 的 handler 调用链是线程安全的（每次 emit 持
``Handler.lock``），FileHandler 追加写同一线程并发安全。
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

#: method.log 文件名。
METHOD_LOG_FILENAME = "method.log"

#: 已知刷屏、INFO 无诊断价值的第三方 logger namespace；命中即被本作用域过滤。
#:
#: 名字按 logger 层级前缀匹配（``startswith``），因此 ``httpx`` 覆盖
#: ``httpx.core`` / ``httpx._client`` 等子 logger。
NOISY_THIRD_PARTY_NAMESPACES: tuple[str, ...] = (
    "transformers",
    "urllib3",
    "httpx",
    "sentence_transformers",
)

#: method.log FileHandler 的日志格式。
_METHOD_LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
#: method.log FileHandler 的时间戳格式（ISO-8601 风格、到秒）。
_METHOD_LOG_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"


class _NoisyThirdPartyFilter(logging.Filter):
    """过滤掉刷屏第三方 namespace 的 INFO 级日志。

    只压这些 namespace 的低价值 INFO；WARNING 及以上保留（异常信号不能丢）。
    匹配方式为 logger 名前缀匹配，确保子 logger 也被覆盖。

    输入:
        record: 一条 ``logging.LogRecord``。

    输出:
        bool: 返回 ``True`` 表示保留该记录，``False`` 表示丢弃。
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        """按 logger 名前缀过滤；仅 INFO 级第三方 noise 被压掉。"""

        name = record.name or ""
        if record.levelno < logging.WARNING and any(
            name == ns or name.startswith(ns + ".")
            for ns in NOISY_THIRD_PARTY_NAMESPACES
        ):
            return False
        return True


@contextmanager
def method_log_scope(log_dir: str | Path) -> Iterator[Path]:
    """在 root logger 上挂一个 run-scoped ``method.log`` FileHandler。

    本函数只**额外**落一份文件：它不改变现有任何 handler、不收窄 root 的
    effective level、也不抑制 method 自身 logger 的传播。作用域结束（含异常）
    一定 ``removeHandler`` + ``close``，保证 root logger 上不残留本 handler，
    避免重复 run / 并行 run 累积与跨 run 串写。

    注意（已知折中）：某些第三方 method 在自身 system 构造时会调用类似
    ``logging.basicConfig``/``apply_logging_config`` 重置 root logger，从而
    移除已挂的 handler。因此本作用域应当在 method system 实例构造**之后**挂载
    （主线 ``run_predictions`` 在调用前已构建好 system 实例）。isolated worker
    路径下 worker 在线程内自行构造 system 会再次重置 root handler —— 这会
    暂时摘掉本 handler；属已知遗留，由架构师后续在 ws04 本体治理，本卡不扩。

    输入:
        log_dir: 本次 run 的日志目录（``<run_dir>/logs``），文件写到
            ``log_dir/method.log``。

    输出:
        Iterator[Path]: yield 实际写入的 ``method.log`` 路径。

    """

    log_path = Path(log_dir) / METHOD_LOG_FILENAME
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    formatter = logging.Formatter(
        fmt=_METHOD_LOG_FORMAT,
        datefmt=_METHOD_LOG_DATEFMT,
    )
    file_handler = logging.FileHandler(
        log_path,
        mode="a",
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(_NoisyThirdPartyFilter())

    root_logger.addHandler(file_handler)
    try:
        yield log_path
    finally:
        root_logger.removeHandler(file_handler)
        try:
            file_handler.close()
        except Exception:
            # close 失败不能掩盖 run 本身的异常；吞掉只保证 handler 不残留。
            pass
        finally:
            pass