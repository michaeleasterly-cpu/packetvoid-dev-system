"""Cloud-memstore behavior matrix for the renderer.

Pins the 4-case truth table that ``memstore_mode`` enforces:

  | api_memstores_enabled | raw IDs | memstore_reference | expected         |
  |---|---|---|---|
  | false                 | n/a     | n/a                | "disabled"       |
  | true                  | both    | n/a                | "enabled_raw"    |
  | true                  | none    | yes                | "enabled_reference" |
  | true                  | none    | none               | "invalid"        |

Plus rendered-output sanity for the new pointer-only block:

  * MEMSTORE_HANDOFF.md mentions ``memstore_reference``
  * MEMSTORE_HANDOFF.md does NOT contain raw memstore IDs in pointer
    mode (no ``memstore_<20+ alphanumerics>``, no
    ``MEMSTORE_ID=`` curl-example body).

Stdlib only.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_BOOTSTRAP = _REPO / "devsystem" / "scripts" / "bootstrap_project.py"
_MEMSTORE_TEMPLATE = (
    _REPO / "devsystem" / "docs" / "MEMSTORE_HANDOFF.md.template"
)


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location(
        "_pvds_bootstrap_memref", _BOOTSTRAP,
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_pvds_bootstrap_memref"] = mod
    spec.loader.exec_module(mod)
    return mod


def _base_profile(**memory_policy) -> dict:
    """Minimal profile that ``render_template`` accepts.
    ``memory_policy`` kwargs override the defaults."""
    mem = {
        "local_memory_limit_bytes": 24400,
        "memory_boundary_doc": True,
        "api_memstores_enabled": False,
    }
    mem.update(memory_policy)
    return {
        "schema_version": 1,
        "project_name": "test-project",
        "language": "python",
        "deployment": "none",
        "database": "none",
        "critical_paths": [],
        "deployment_specific_paths": [],
        "claude_system_paths": [],
        "security_sensitive_paths": [],
        "forbidden_assumptions": [],
        "memory_policy": mem,
        "review_mode": "claude-review-only",
        "output_paths": {"operator_reports": ".operator/reports/claude/"},
        "home_session_path": "~/.claude/projects/-Users-USERNAME-test-project/",
        "python_version": "3.11",
        "test_command": "python -m pytest -q",
        "gitleaks_version": "8.30.1",
    }


# ─────────────────────────────────────────────────────────────────────
# Truth table for memstore_mode
# ─────────────────────────────────────────────────────────────────────


def testmemstore_mode_disabled_by_default() -> None:
    mod = _load_bootstrap()
    profile = _base_profile()
    assert mod.memstore_mode(profile) == "disabled"


def testmemstore_mode_enabled_raw_when_both_ids_present() -> None:
    mod = _load_bootstrap()
    profile = _base_profile(
        api_memstores_enabled=True,
        dev_memstore_id="memstore_TestDevId01234567890",
        agent_memstore_id="memstore_TestAgentId01234567890",
    )
    assert mod.memstore_mode(profile) == "enabled_raw"


def testmemstore_mode_enabled_reference_when_pointer_present() -> None:
    mod = _load_bootstrap()
    profile = _base_profile(
        api_memstores_enabled=True,
        memstore_reference="docs/MEMSTORE_HANDOFF.md",
    )
    assert mod.memstore_mode(profile) == "enabled_reference"


def testmemstore_mode_invalid_when_enabled_with_neither() -> None:
    mod = _load_bootstrap()
    profile = _base_profile(api_memstores_enabled=True)
    assert mod.memstore_mode(profile) == "invalid"


def testmemstore_mode_raw_wins_when_both_present() -> None:
    """When a consumer (perhaps mid-migration) sets BOTH raw IDs and
    memstore_reference, raw IDs take precedence — that's the more
    specific declaration and matches the legacy rendering path."""
    mod = _load_bootstrap()
    profile = _base_profile(
        api_memstores_enabled=True,
        dev_memstore_id="memstore_TestDevId01234567890",
        agent_memstore_id="memstore_TestAgentId01234567890",
        memstore_reference="docs/MEMSTORE_HANDOFF.md",
    )
    assert mod.memstore_mode(profile) == "enabled_raw"


# ─────────────────────────────────────────────────────────────────────
# render_template enforcement
# ─────────────────────────────────────────────────────────────────────


def test_render_raises_when_enabled_with_neither_ids_nor_reference() -> None:
    mod = _load_bootstrap()
    profile = _base_profile(api_memstores_enabled=True)
    with pytest.raises(ValueError) as exc:
        mod.render_template(
            _MEMSTORE_TEMPLATE.read_text(encoding="utf-8"), profile,
        )
    # Error message must guide the operator toward both fixes.
    msg = str(exc.value)
    assert "dev_memstore_id" in msg
    assert "memstore_reference" in msg
    assert "api_memstores_enabled" in msg


def test_render_accepts_pointer_only_profile() -> None:
    mod = _load_bootstrap()
    profile = _base_profile(
        api_memstores_enabled=True,
        memstore_reference="docs/MEMSTORE_HANDOFF.md",
    )
    rendered = mod.render_template(
        _MEMSTORE_TEMPLATE.read_text(encoding="utf-8"), profile,
    )
    # Pointer block kept.
    assert "Cloud memstores are enabled by posture" in rendered, (
        "rendered pointer-only output must include the enabled-by-"
        "posture banner"
    )
    assert "docs/MEMSTORE_HANDOFF.md" in rendered, (
        "rendered pointer-only output must surface the "
        "memstore_reference value"
    )


def test_render_pointer_mode_strips_raw_id_block() -> None:
    """In pointer mode, the rendered MEMSTORE_HANDOFF.md must NOT
    contain the raw-ID table, the ``MEMSTORE_ID=`` curl examples, or
    any 20+-char memstore-ID literal."""
    mod = _load_bootstrap()
    profile = _base_profile(
        api_memstores_enabled=True,
        memstore_reference="docs/MEMSTORE_HANDOFF.md",
    )
    rendered = mod.render_template(
        _MEMSTORE_TEMPLATE.read_text(encoding="utf-8"), profile,
    )
    # No raw-ID table row.
    assert "MEMSTORE_ID=" not in rendered, (
        "pointer mode must not render raw-ID curl examples"
    )
    # No raw memstore-ID literal of any length 20+.
    memstore_id_re = re.compile(r"memstore_[A-Za-z0-9]{20,}")
    leaks = memstore_id_re.findall(rendered)
    assert not leaks, (
        f"pointer mode must not contain raw memstore-ID literal(s): "
        f"{leaks}"
    )
    # And the unrendered placeholder must NOT survive either.
    assert "{{ dev_memstore_id }}" not in rendered
    assert "{{ agent_memstore_id }}" not in rendered


def test_render_raw_id_mode_strips_pointer_block_and_keeps_raw_table() -> None:
    """Legacy mode unchanged: raw IDs render the curl-table body and
    drop the pointer-only banner."""
    mod = _load_bootstrap()
    profile = _base_profile(
        api_memstores_enabled=True,
        dev_memstore_id="memstore_TestDevAaaaaaaaaaaa",
        agent_memstore_id="memstore_TestAgntBbbbbbbbbbbb",
    )
    rendered = mod.render_template(
        _MEMSTORE_TEMPLATE.read_text(encoding="utf-8"), profile,
    )
    assert "MEMSTORE_ID=" in rendered, (
        "raw-ID mode must keep the curl-protocol example"
    )
    assert "memstore_TestDevAaaaaaaaaaaa" in rendered, (
        "raw-ID mode must substitute dev_memstore_id"
    )
    assert "Cloud memstores are enabled by posture" not in rendered, (
        "pointer-only banner must not appear in raw-ID mode"
    )
    # No surviving conditional markers either way.
    for marker in (
        "<!-- BEGIN_API_MEMSTORES_DISABLED -->",
        "<!-- END_API_MEMSTORES_DISABLED -->",
        "<!-- BEGIN_API_MEMSTORES_ENABLED -->",
        "<!-- END_API_MEMSTORES_ENABLED -->",
        "<!-- BEGIN_API_MEMSTORES_ENABLED_REFERENCE -->",
        "<!-- END_API_MEMSTORES_ENABLED_REFERENCE -->",
    ):
        assert marker not in rendered, (
            f"conditional-block marker {marker!r} survived rendering"
        )


def test_render_disabled_mode_unchanged() -> None:
    """Default-posture path remains identical to pre-feature behavior."""
    mod = _load_bootstrap()
    profile = _base_profile()  # api_memstores_enabled: false
    rendered = mod.render_template(
        _MEMSTORE_TEMPLATE.read_text(encoding="utf-8"), profile,
    )
    assert "Cloud memstores are disabled for this project" in rendered
    assert "MEMSTORE_ID=" not in rendered, (
        "disabled mode must not render the raw-ID curl example"
    )
    assert "Cloud memstores are enabled by posture" not in rendered
