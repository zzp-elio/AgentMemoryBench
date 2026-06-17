"""统一日志工具。

库代码不主动配置全局 logging，也不向 stdout/stderr 直接打印。
`get_logger()` 给每个模块返回命名 logger，并挂一个 NullHandler，避免宿主项目
没有配置 logging 时出现 “No handler found” 或重复 handler 问题。
"""

from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    """返回带 NullHandler 的命名 logger。

    参数:
        name: 通常传 `__name__`，也可以传测试中的固定 logger 名。

    返回:
        logging.Logger: 不会重复添加 NullHandler 的 logger。
    """

    logger = logging.getLogger(name)
    has_null_handler = any(isinstance(handler, logging.NullHandler) for handler in logger.handlers)
    if not has_null_handler:
        logger.addHandler(logging.NullHandler())
    return logger
