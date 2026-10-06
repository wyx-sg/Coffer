"""A new environment's binding key is found in bounded time, and stays valid.

Spec mcp-gateway "Keep a custom-tool group's environments in the group". The
key search runs inside an ``async`` add, on the daemon's event loop, so a search
that never ends freezes every session. Each case runs ``_fresh_key`` in a child
process with a hard timeout: a regression shows up as a failed test, never as a
hung suite.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[4]
_TIMEOUT_S = 10.0


def _fresh_key_in_child(name: str, taken: list[str]) -> str:
    script = textwrap.dedent(
        """
        import json, sys
        from coffer.application.mcp.custom_tool_environments import _fresh_key
        name, taken = json.loads(sys.stdin.read())
        print(json.dumps(_fresh_key(name, set(taken))))
        """
    )
    try:
        out = subprocess.run(
            [sys.executable, "-c", script],
            input=json.dumps([name, taken]),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            cwd=_BACKEND,
            env={"PYTHONPATH": str(_BACKEND), "PATH": "/usr/bin:/bin", "HOME": os.environ["HOME"]},
            check=True,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"_fresh_key({name!r}, {len(taken)} taken) did not finish in {_TIMEOUT_S}s")
    result = json.loads(out.stdout)
    assert isinstance(result, str)
    return result


@pytest.mark.parametrize("length", [1, 37, 38, 39, 40])
def test_a_reused_name_of_any_length_gets_a_new_valid_key(length: int) -> None:
    from coffer.domain.mcp.http_api_environment import ENV_NAME_RE

    name = "a" * length
    key = _fresh_key_in_child(name, [name])
    assert key != name
    assert ENV_NAME_RE.match(key), key
    assert len(key) <= 40


def test_many_earlier_suffixes_are_skipped_and_the_search_ends() -> None:
    from coffer.domain.mcp.http_api_environment import ENV_NAME_RE

    name = "b" * 40
    taken = [name] + [name[: 40 - len(f"-{n}")] + f"-{n}" for n in range(2, 60)]
    key = _fresh_key_in_child(name, taken)
    assert key not in taken
    assert ENV_NAME_RE.match(key) and len(key) <= 40


def test_a_name_not_yet_taken_is_its_own_key() -> None:
    assert _fresh_key_in_child("billing", ["other"]) == "billing"
