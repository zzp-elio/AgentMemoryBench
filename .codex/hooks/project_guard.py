#!/usr/bin/env python3
"""为本项目的 Codex 生命周期注入压缩恢复门与 commit 纪律提醒。"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIVE_WORKSTREAM_ROW = re.compile(
    r"\|\s*\[[^]]+\]\((workstreams/[^)]+/README\.md)\)\s*\|"
    r"[^|]*\|\s*in-progress\s*\|\s*P0\s*\|"
)
GIT_COMMIT_COMMAND = re.compile(r"\bgit\b[^\n;&|]*\bcommit\b")


def _active_capsule_target() -> str:
    """从 roadmap 唯一的 P0 活跃行解析恢复胶囊路径；歧义时不猜。"""

    roadmap = REPO_ROOT / "docs" / "roadmap.md"
    try:
        matches = ACTIVE_WORKSTREAM_ROW.findall(roadmap.read_text(encoding="utf-8"))
    except OSError:
        matches = []
    if len(matches) == 1:
        return f"docs/{matches[0]}"
    return "活跃 workstream README（先只用 rg 定位 docs/roadmap.md 的 in-progress P0 行）"


def _recovery_context() -> str:
    """生成不依赖某个固定 workstream 的压缩恢复门。"""

    capsule_target = _active_capsule_target()
    return f"""[Codex 压缩恢复门]
本 task 刚发生 context compaction，原始逐字对话已不可见；恢复仅在后台执行，不得把摘要冒充完整记忆。除非缺失上下文实质影响当前回答/裁决，或用户明确询问，否则不要自动向用户播报 compaction。
在任何项目判断、编辑或大范围读文档前，只执行：
1. git status --short
2. git log -5 --oneline
3. 读取 {capsule_target} 顶部“Codex 恢复胶囊”
4. 只定点读取当前动作对应的一份判据或 note
禁止为恢复全局而通读全部 workstream/手册/历史；若胶囊与 git 冲突，以 git + 最新裁决 note 为准。默认只写 actor 卡交给用户派发，不自动启动 Codex subagent。
"""

COMMIT_REMINDER = (
    "[commit 纪律 hook] 提交前完成 playbook 三问；git add 只用显式路径，禁 -A/.；"
    "先查看 git status --short 与 cached diff，确认未暂存用户资产。"
)


def _read_event() -> dict[str, Any]:
    """从标准输入读取 Codex hook 事件；畸形输入安全地视为空事件。"""

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _emit(payload: dict[str, Any]) -> None:
    """以 UTF-8 JSON 输出 Codex hook 响应。"""

    sys.stdout.write(json.dumps(payload, ensure_ascii=False))


def main() -> None:
    """按事件类型输出压缩恢复 context 或 commit 提醒；其余事件静默放行。"""

    event = _read_event()
    event_name = event.get("hook_event_name")
    if event_name == "SessionStart" and event.get("source") == "compact":
        _emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": _recovery_context(),
                }
            }
        )
        return

    if event_name != "PreToolUse":
        return
    tool_input = event.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if isinstance(command, str) and GIT_COMMIT_COMMAND.search(command):
        _emit({"systemMessage": COMMIT_REMINDER})


if __name__ == "__main__":
    main()
