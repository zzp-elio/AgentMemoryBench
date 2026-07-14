"""统一图片 caption 文本 helper 的离线测试。"""

from memory_benchmark.core import ImageRef, Turn
from memory_benchmark.methods.image_text import turn_text_with_images


def test_turn_text_with_images_uses_shared_wording_and_skips_query() -> None:
    """文本与有 caption 图片应统一拼接，query 等 metadata 不得进入内容。"""

    turn = Turn(
        turn_id="t1",
        speaker="Alice",
        content="Look at this",
        images=[
            ImageRef(caption="a red kite"),
            ImageRef(caption=None),
        ],
        metadata={"query": "synthetic search hint"},
    )

    assert turn_text_with_images(turn) == (
        "Look at this [Sharing image that shows: a red kite]"
    )


def test_turn_text_with_images_allows_caption_only_turn() -> None:
    """纯图片 turn 可只输出统一 photo tag。"""

    turn = Turn(
        turn_id="t1",
        speaker="Alice",
        content="",
        images=[ImageRef(caption="snowy mountains")],
    )

    assert turn_text_with_images(turn) == (
        "[Sharing image that shows: snowy mountains]"
    )
