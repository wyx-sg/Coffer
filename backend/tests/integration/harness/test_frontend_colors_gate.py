"""Tests for scripts/check_frontend_colors.py — the frontend colour-literal gate.

The gate fails on a hex colour, a colour function or a Tailwind palette class
anywhere in ``frontend/src/`` outside ``index.css``, which holds the theme
tokens. Each rule is proved to bite on synthetic source and to stay quiet on
code that only looks similar; the real tree is proved clean.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from types import ModuleType

import pytest

from .conftest import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "check_frontend_colors.py"


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_frontend_colors", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_frontend_colors"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ('const c = "#4353d8";', "hex colour"),
        ("<div style={{ color: '#fff' }} />", "hex colour"),
        ('<div className="bg-[#16181D]" />', "hex colour"),
        ('const c = "rgba(0, 0, 0, 0.5)";', "colour function"),
        ('const c = "rgb(22 24 29)";', "colour function"),
        ('const c = "hsl(var(--primary))";', "colour function"),
        ('<div className="shadow-[0_1px_2px_rgba(0,0,0,.1)]" />', "colour function"),
        ('<div className="bg-red-500" />', "Tailwind palette class"),
        ('<div className="hover:text-emerald-600" />', "Tailwind palette class"),
        ('<div className="text-white" />', "Tailwind palette class"),
        ('<div className="border-l-amber-300/50" />', "Tailwind palette class"),
    ],
)
@pytest.mark.acceptance(
    spec="web-ui", scenario="a colour literal outside the tokens fails the lint gate"
)
def test_each_colour_literal_is_caught(gate: ModuleType, source: str, rule: str) -> None:
    assert [label for _line, label, _lit in gate.scan_source(source)] == [rule]


@pytest.mark.parametrize(
    "source",
    [
        # Token reads.
        'const c = "rgb(var(--accent) / 0.45)";',
        '<div className="bg-surface-raised text-text-muted border-border-subtle" />',
        '<div className="bg-danger/10 text-neutral bg-neutral-soft" />',
        # Issue references and anchors in comments.
        "// scrolls under the sticky header (#227)\nconst x = 1;",
        "/* see #412 */ const y = 2;",
        # Things shaped like colours that are not.
        'const url = "https://example.com/#section";',
        'const id = "item#1234abcd-x";',
        'const tab = "?tab=tools#top";',
    ],
)
def test_token_uses_and_lookalikes_pass(gate: ModuleType, source: str) -> None:
    assert gate.scan_source(source) == []


def test_comments_are_blanked_but_lines_stay_put(gate: ModuleType) -> None:
    source = '// "#ffffff"\n/* rgba(0,0,0,1)\n */\nconst c = "#000";\n'
    assert gate.scan_source(source) == [(4, "hex colour", "#000")]


def test_real_tree_is_clean() -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
