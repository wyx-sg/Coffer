"""Path-portability pure helpers (spec 010 "Path portability")."""

from __future__ import annotations

from coffer.domain.sync.portability import expand_home, normalize_home


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


def test_paths_outside_home_are_carried_verbatim() -> None:
    # They may simply not resolve on the other machine, which surfaces as a
    # reported import failure rather than a silent rewrite.
    config = {"cmd": "/opt/homebrew/bin/x"}
    assert expand_home(normalize_home(config, "/Users/alice"), "/home/bob") == config


def test_home_prefix_requires_path_boundary() -> None:
    config = {"a": "/Users/alicelong/x", "b": "/Users/alice"}
    portable = normalize_home(config, "/Users/alice")
    assert portable["a"] == "/Users/alicelong/x"  # not under the home
    assert portable["b"] == "${HOME}"


def test_literal_token_survives_normalize() -> None:
    config = {"a": "${HOME}/already"}
    assert normalize_home(config, "/Users/alice")["a"] == "${HOME}/already"


def test_blank_home_is_a_no_op() -> None:
    config = {"a": "/Users/alice/x"}
    assert normalize_home(config, "") == config
