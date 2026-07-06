"""测试共享 fake 语料构造器。"""

from __future__ import annotations

from memory_benchmark.core import Conversation, ImageRef, Question, Session, Turn


def build_multimodal_consecutive_speaker_conversation() -> Conversation:
    """构造含图片 caption 与连续同 speaker turn 的公开 conversation。"""

    question_id = "conv-rich:q1"
    return Conversation(
        conversation_id="conv-rich",
        sessions=[
            Session(
                session_id="conv-rich:s1",
                session_time="2026-07-06T10:00:00Z",
                turns=[
                    Turn(
                        turn_id="conv-rich:t1",
                        speaker="Alice",
                        content="我拍了一张花瓶照片",
                        normalized_role="user",
                        images=[
                            ImageRef(
                                image_id="img-1",
                                path="images/vase.jpg",
                                caption="a blue vase on a table",
                                metadata={"source": "fake"},
                            )
                        ],
                    ),
                    Turn(
                        turn_id="conv-rich:t2",
                        speaker="Alice",
                        content="它是昨天买的",
                        normalized_role="user",
                    ),
                    Turn(
                        turn_id="conv-rich:t3",
                        speaker="Bob",
                        content="我会记住这个花瓶。",
                        normalized_role="assistant",
                    ),
                ],
            )
        ],
        questions=[
            Question(
                question_id=question_id,
                conversation_id="conv-rich",
                text="Alice 昨天买了什么？",
            )
        ],
        gold_answers={},
        metadata={"speaker_a": "Alice", "speaker_b": "Bob"},
    )
