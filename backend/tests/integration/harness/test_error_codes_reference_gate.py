"""Tests for scripts/check_error_codes_reference.py — the error-code reference
lists every code the management API maps, at the status it is sent with."""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType

import pytest

from .conftest import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "check_error_codes_reference.py"


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_error_codes_reference", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_error_codes_reference"] = mod
    spec.loader.exec_module(mod)
    return mod


_PAGE = """# Error codes

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `A_CODE` | 404 | a | a |
| `HTTP_<status>` | as named | bare | read it |

## Startup

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `B_CODE` | 409 | b | b |

## Chat turn errors

| Code | Meaning |
| --- | --- |
| `turn_failed` | not an API code |
| `NOT_MAPPED_HERE` | a table without an HTTP column is not compared |
"""


def test_a_page_listing_every_mapped_code_at_its_status_passes(gate) -> None:
    assert gate.check_page("p.md", _PAGE, {"A_CODE": 404, "B_CODE": 409}) == []


def test_a_mapped_code_with_no_row_fails(gate) -> None:
    (problem,) = gate.check_page("p.md", _PAGE, {"A_CODE": 404, "B_CODE": 409, "C_CODE": 422})
    assert problem == "p.md: no row for `C_CODE` (HTTP 422)"


def test_a_row_at_another_status_fails(gate) -> None:
    (problem,) = gate.check_page("p.md", _PAGE, {"A_CODE": 400, "B_CODE": 409})
    assert "`A_CODE` says HTTP '404'; the daemon sends 400" in problem


def test_a_row_for_a_code_the_daemon_does_not_map_fails(gate) -> None:
    (problem,) = gate.check_page("p.md", _PAGE, {"A_CODE": 404})
    assert problem.endswith("`B_CODE` is not a code the daemon maps")


def test_the_real_pages_match_the_daemon(gate) -> None:
    codes = gate.mapped_codes()
    for page in gate.PAGES:
        text = (REPO_ROOT / page).read_text(encoding="utf-8")
        assert gate.check_page(page.as_posix(), text, codes) == []
