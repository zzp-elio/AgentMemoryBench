"""通用工具层。

当前只放跨模块复用且不属于业务实体的工具，例如 logger。
"""

from .logger import get_logger

__all__ = ["get_logger"]
