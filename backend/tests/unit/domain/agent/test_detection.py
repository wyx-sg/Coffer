"""Two-signal detection: program x config directory (spec agent-registry
"Detect an agent by its program and its config directory")."""

from __future__ import annotations

import pytest

from coffer.domain.agent.detection import DetectionState, ProgramInfo, classify, parse_version

_FOUND = ProgramInfo(path="/usr/local/bin/codex", version="0.155.1")


@pytest.mark.parametrize(
    ("program", "exists", "state"),
    [
        (_FOUND, True, DetectionState.INSTALLED_ACTIVE),
        (_FOUND, False, DetectionState.INSTALLED_NEVER_RUN),
        (ProgramInfo(), True, DetectionState.CONFIG_ONLY),
        (ProgramInfo(), False, DetectionState.MISSING),
    ],
)
def test_the_two_signals_name_the_state(
    program: ProgramInfo, exists: bool, state: DetectionState
) -> None:
    assert classify(program, config_dir_exists=exists) is state


def test_a_program_found_without_a_version_is_still_installed() -> None:
    silent = ProgramInfo(path="/opt/bin/claude", version=None)
    assert classify(silent, config_dir_exists=True) is DetectionState.INSTALLED_ACTIVE
    assert DetectionState.INSTALLED_NEVER_RUN.installed
    assert not DetectionState.CONFIG_ONLY.installed


@pytest.mark.parametrize(
    ("output", "version"),
    [
        ("2.1.281 (Claude Code)\n", "2.1.281"),
        ("codex-cli 0.155.1\n", "0.155.1"),
        ("codex-cli 0.156.0-alpha.3", "0.156.0-alpha.3"),
        ("tool v1.2", "1.2"),
        ("no version here", None),
        ("", None),
    ],
)
def test_the_version_is_the_first_dotted_number(output: str, version: str | None) -> None:
    assert parse_version(output) == version
