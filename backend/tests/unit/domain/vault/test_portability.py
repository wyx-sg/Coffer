"""Home paths in vault documents (spec vault-sync "Store home paths against a
sentinel", "Store paths outside home verbatim")."""

from __future__ import annotations

import pytest

from coffer.domain.vault.portability import expand_home, normalize_home


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a path under the home directory applies on a machine with a different home",
)
def test_a_home_path_is_stored_against_the_sentinel_and_expanded_elsewhere() -> None:
    stored = normalize_home(
        {"config_dir": "/Users/xing/.codex", "args": ["/Users/xing"]}, "/Users/xing"
    )
    assert stored == {"config_dir": "${HOME}/.codex", "args": ["${HOME}"]}
    assert expand_home(stored, "/home/wu") == {
        "config_dir": "/home/wu/.codex",
        "args": ["/home/wu"],
    }
    # A sibling that merely shares the prefix is not under home.
    assert normalize_home({"p": "/Users/xingelse/x"}, "/Users/xing") == {"p": "/Users/xingelse/x"}


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a path outside the home directory is stored verbatim"
)
def test_a_path_outside_home_is_carried_exactly_as_written() -> None:
    config = {"command": "/opt/homebrew/bin/uvx", "nested": {"dir": "/srv/data"}}
    stored = normalize_home(config, "/Users/xing")
    assert stored == config
    assert expand_home(stored, "/home/wu") == config
