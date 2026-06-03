"""Sentinels for the Layer-1 security-pattern-scan hook templates.

Pins the portable security-guidance Layer-1 PostToolUse hook set that was
synced from the donor's ``security_pattern_scan`` advisory hook (the
GENERIC Anthropic Layer-1 patterns only; the donor's domain-specific
patterns stay donor-only):

  * ``devsystem/claude/hooks/security_pattern_scan.sh.template``
  * ``devsystem/claude/hooks/security_pattern_scan.py.template``
  * ``devsystem/claude/hooks/security_patterns_vendored.py.template``

Plus the ``settings.json.template`` PostToolUse wiring and the generic
kill-switch env var.

Stdlib-only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_CLAUDE = _REPO / "devsystem" / "claude"
_HOOKS = _CLAUDE / "hooks"

_GENERIC_KILL_SWITCH = "DEVSYS_SECURITY_PATTERN_SCAN_DISABLE"
# The donor's STE-specific kill-switch name must NOT leak into the
# portable templates.
_DONOR_KILL_SWITCH = "STE_SECURITY_PATTERN_SCAN_DISABLE"


def _text(path: Path) -> str:
    assert path.is_file(), f"missing {path.relative_to(_REPO)}"
    body = path.read_text(encoding="utf-8")
    assert body.strip(), f"empty {path.relative_to(_REPO)}"
    return body


# ─────────────────────────────────────────────────────────────────────
# Presence
# ─────────────────────────────────────────────────────────────────────

def test_security_pattern_scan_sh_template_present_and_shebanged() -> None:
    text = _text(_HOOKS / "security_pattern_scan.sh.template")
    assert text.startswith("#!"), "wrapper missing shebang"


def test_security_pattern_scan_py_template_present() -> None:
    text = _text(_HOOKS / "security_pattern_scan.py.template")
    assert text.lstrip().startswith("#!") or text.lstrip().startswith('"""'), (
        "entrypoint should start with shebang or module docstring"
    )


def test_security_patterns_vendored_py_template_present() -> None:
    text = _text(_HOOKS / "security_patterns_vendored.py.template")
    assert "SECURITY_PATTERNS" in text, (
        "vendored pattern data must define SECURITY_PATTERNS"
    )


# ─────────────────────────────────────────────────────────────────────
# Generic kill switch — donor name must not leak
# ─────────────────────────────────────────────────────────────────────

def test_wrapper_uses_generic_kill_switch() -> None:
    text = _text(_HOOKS / "security_pattern_scan.sh.template")
    assert _GENERIC_KILL_SWITCH in text, (
        f"wrapper must reference the generic kill switch {_GENERIC_KILL_SWITCH!r}"
    )
    assert _DONOR_KILL_SWITCH not in text, (
        f"donor kill-switch name {_DONOR_KILL_SWITCH!r} leaked into wrapper"
    )


def test_entrypoint_uses_generic_kill_switch() -> None:
    text = _text(_HOOKS / "security_pattern_scan.py.template")
    assert _GENERIC_KILL_SWITCH in text, (
        f"entrypoint must reference the generic kill switch {_GENERIC_KILL_SWITCH!r}"
    )
    assert _DONOR_KILL_SWITCH not in text, (
        f"donor kill-switch name {_DONOR_KILL_SWITCH!r} leaked into entrypoint"
    )


# ─────────────────────────────────────────────────────────────────────
# STE-specific patterns are intentionally NOT ported
# ─────────────────────────────────────────────────────────────────────

def test_no_ste_specific_patterns_module_shipped() -> None:
    """The donor's ``security_patterns_ste`` (no-yfinance / no-Discord /
    hardcoded-postgres-URL etc.) is domain-specific and must NOT be
    vendored into the generic scaffold."""
    assert not (_HOOKS / "security_patterns_ste.py").exists()
    assert not (_HOOKS / "security_patterns_ste.py.template").exists()


def test_entrypoint_does_not_hard_require_ste_patterns() -> None:
    """The entrypoint must import only the generic vendored set as a hard
    dependency; any project-local patterns must be optional."""
    text = _text(_HOOKS / "security_pattern_scan.py.template")
    assert "security_patterns_ste" not in text, (
        "entrypoint must not reference the donor's STE-specific pattern module"
    )
    # The vendored import is the only hard requirement.
    assert "from security_patterns_vendored import SECURITY_PATTERNS" in text


# ─────────────────────────────────────────────────────────────────────
# settings.json.template PostToolUse wiring
# ─────────────────────────────────────────────────────────────────────

def _settings_json() -> dict:
    text = _text(_CLAUDE / "settings.json.template")
    text = text.replace("{{ project_name }}", "example-project")
    leftovers = re.findall(r"\{\{\s*[A-Za-z0-9_]+\s*\}\}", text)
    assert not leftovers, f"unexpected placeholders in settings template: {leftovers}"
    return json.loads(text)


def test_settings_template_wires_security_scan_post_tool_use() -> None:
    data = _settings_json()
    hooks = data.get("hooks", {})
    post = hooks.get("PostToolUse")
    assert isinstance(post, list) and post, (
        "settings template must define a PostToolUse hook block"
    )
    # Find an entry matching the Edit|Write|MultiEdit|NotebookEdit matcher
    # that wires the security scanner.
    found = False
    for entry in post:
        matcher = entry.get("matcher", "")
        for verb in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            assert verb in matcher, (
                f"PostToolUse matcher must cover {verb}; got {matcher!r}"
            )
        for hook in entry.get("hooks", []):
            if "security_pattern_scan.sh" in hook.get("command", ""):
                found = True
    assert found, (
        "PostToolUse must wire $CLAUDE_PROJECT_DIR/.claude/hooks/"
        "security_pattern_scan.sh"
    )
