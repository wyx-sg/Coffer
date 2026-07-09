"""Syntax-check the rendered openclaw extension entry with a real ``node``.

Integration tier because it spawns a process (`node --check`); the pure
rendering/transform coverage lives in
``tests/unit/domain/agent/test_plugin_drop_openclaw.py``.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from coffer.domain.agent.plugin_drop_openclaw import (
    OPENCLAW_ENTRY_FILENAME,
    render_openclaw_extension,
)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_rendered_entry_is_valid_javascript(tmp_path) -> None:
    # `node --check` parses ESM when the file is .mjs — the rendered module uses
    # import/export syntax.
    entry = render_openclaw_extension(hook_binary="/opt/coffer/coffer-hook", agent_name="ow")[
        OPENCLAW_ENTRY_FILENAME
    ]
    path = tmp_path / "index.mjs"
    path.write_text(entry, encoding="utf-8")
    proc = subprocess.run(
        ["node", "--check", str(path)], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
