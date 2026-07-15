"""测试项目级 Codex hook 的压缩自举与 commit 提醒契约。"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".codex" / "hooks" / "project_guard.py"
HOOKS_CONFIG = ROOT / ".codex" / "hooks.json"


def _run_hook(event: dict[str, object]) -> dict[str, object] | None:
    """向 hook 传入一个合成事件并解析可选 JSON 输出。"""

    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout) if result.stdout else None


def test_codex_hooks_config_registers_compact_and_commit_events() -> None:
    """配置必须只登记压缩恢复与 Bash commit 两个低噪声入口。"""

    payload = json.loads(HOOKS_CONFIG.read_text(encoding="utf-8"))
    hooks = payload["hooks"]
    assert hooks["SessionStart"][0]["matcher"] == "^compact$"
    assert hooks["PreToolUse"][0]["matcher"] == "^Bash$"


def test_compact_session_injects_bounded_recovery_gate() -> None:
    """压缩重启必须注入静默四步恢复门，并明确禁止全文扫文档。"""

    payload = _run_hook(
        {"hook_event_name": "SessionStart", "source": "compact"}
    )
    context = payload["hookSpecificOutput"]["additionalContext"]
    assert "git status --short" in context
    assert "git log -5 --oneline" in context
    assert "docs/workstreams/" in context
    assert "Codex 恢复胶囊" in context
    assert "禁止为恢复全局而通读全部" in context
    assert "恢复仅在后台执行" in context
    assert "不要自动向用户播报 compaction" in context


def test_bash_git_commit_injects_discipline_reminder() -> None:
    """Bash 命令含 git commit 时必须提醒显式暂存与 cached diff。"""

    payload = _run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m 'test'"},
        }
    )
    message = payload["systemMessage"]
    assert "显式路径" in message
    assert "cached diff" in message


def test_non_commit_bash_command_is_silent() -> None:
    """普通 Bash 命令不得产生提醒噪声。"""

    assert (
        _run_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "git status --short"},
            }
        )
        is None
    )


def test_git_dash_c_commit_also_injects_reminder() -> None:
    """带 git -C 前缀的提交同样不能绕过纪律提醒。"""

    payload = _run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git -C /tmp/project commit -m test"},
        }
    )
    assert "cached diff" in payload["systemMessage"]
