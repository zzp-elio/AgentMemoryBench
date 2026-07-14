"""method 注入侧统一的图片 caption 文本表示。"""

from __future__ import annotations

from memory_benchmark.core import Turn


def turn_text_with_images(turn: Turn) -> str:
    """把 turn 文本与有 caption 的图片按统一公开格式拼接。"""

    parts: list[str] = []
    if turn.content and turn.content.strip():
        parts.append(turn.content.strip())
    parts.extend(
        f"[Sharing image that shows: {image.caption.strip()}]"
        for image in turn.images
        if image.caption and image.caption.strip()
    )
    return " ".join(parts)


__all__ = ["turn_text_with_images"]
