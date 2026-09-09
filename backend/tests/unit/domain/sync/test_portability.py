"""Path-portability pure helpers (spec 010 slice 5)."""

from __future__ import annotations

from coffer.domain.sync.portability import (
    apply_merge_patch,
    expand_home,
    normalize_home,
    strip_overridden,
)


def test_home_round_trip_across_two_homes() -> None:
    config = {
        "config_dir": "/Users/alice/.claude",
        "nested": {"paths": ["/Users/alice/repo", "/opt/tool"]},
        "not_a_path": "hello",
    }
    portable = normalize_home(config, "/Users/alice")
    assert portable["config_dir"] == "${HOME}/.claude"
    assert portable["nested"]["paths"] == ["${HOME}/repo", "/opt/tool"]
    landed = expand_home(portable, "/home/bob")
    assert landed["config_dir"] == "/home/bob/.claude"
    assert landed["nested"]["paths"][0] == "/home/bob/repo"
    assert landed["not_a_path"] == "hello"


def test_home_prefix_requires_path_boundary() -> None:
    config = {"a": "/Users/alicelong/x", "b": "/Users/alice"}
    portable = normalize_home(config, "/Users/alice")
    assert portable["a"] == "/Users/alicelong/x"  # not under the home
    assert portable["b"] == "${HOME}"


def test_literal_token_survives_normalize() -> None:
    config = {"a": "${HOME}/already"}
    assert normalize_home(config, "/Users/alice")["a"] == "${HOME}/already"


def test_merge_patch_semantics() -> None:
    target = {"a": 1, "b": {"x": 1, "y": 2}, "c": 3}
    patch = {"a": 9, "b": {"y": None, "z": 5}, "c": None}
    assert apply_merge_patch(target, patch) == {"a": 9, "b": {"x": 1, "z": 5}}


def test_strip_overridden_restores_shared_values() -> None:
    shared = {"cmd": "/usr/local/bin/x", "keep": 1}
    live = {"cmd": "/opt/homebrew/bin/x", "keep": 1, "extra": True}
    patch = {"cmd": "/opt/homebrew/bin/x", "extra": True}
    assert strip_overridden(live, patch, shared) == {"cmd": "/usr/local/bin/x", "keep": 1}


def test_strip_overridden_nested() -> None:
    shared = {"transport": {"command": "/usr/bin/npx", "args": ["-y"]}}
    live = {"transport": {"command": "/opt/npx", "args": ["-y"]}}
    patch = {"transport": {"command": "/opt/npx"}}
    out = strip_overridden(live, patch, shared)
    assert out == {"transport": {"command": "/usr/bin/npx", "args": ["-y"]}}
