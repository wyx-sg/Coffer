"""The prompts Coffer hands to an agent for a local runtime and git: built from
Coffer's own facts, never an install command, and always ending with the
standing rules (``domain/handoff.py``)."""

from __future__ import annotations

from coffer.application.provider.local_runtime_handoff import local_runtime_handoff
from coffer.domain.git_handoff import git_install_handoff, git_missing_details
from coffer.domain.handoff import STANDING_RULES
from coffer.infrastructure.platform.memory import memory_label


def _ends_with_the_standing_rules(prompt: str) -> None:
    assert prompt.splitlines()[-len(STANDING_RULES) :] == list(STANDING_RULES)


def test_the_local_runtime_prompt_names_the_ports_and_the_memory() -> None:
    prompt = local_runtime_handoff("macOS 15.6, arm64", "32 GB")
    assert "This machine: macOS 15.6, arm64, 32 GB of memory." in prompt
    assert "Ollama on port 11434, LM Studio on port 1234" in prompt
    assert "Ollama serves both from 0.14.0; LM Studio serves both from 0.4.1" in prompt
    assert "64k tokens" in prompt
    _ends_with_the_standing_rules(prompt)


def test_the_local_runtime_prompt_leaves_unknown_memory_out() -> None:
    assert "This machine: Windows 11, AMD64.\n" in local_runtime_handoff("Windows 11, AMD64", None)


def test_the_git_prompt_rides_on_details() -> None:
    details = git_missing_details("Ubuntu 24.04 LTS, x86_64", needed_for="the knowledge history")
    assert details["reason"] == "git_missing"
    prompt = git_install_handoff("Ubuntu 24.04 LTS, x86_64", needed_for="the knowledge history")
    assert details["handoff"] == {"prompt": prompt}
    assert "apt" not in prompt and "brew" not in prompt
    _ends_with_the_standing_rules(prompt)


def test_memory_is_whole_gigabytes_or_unknown() -> None:
    label = memory_label()
    assert label is None or (label.endswith(" GB") and label.split()[0].isdigit())
