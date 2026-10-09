"""The upgrade hand-off (spec daemon "Hand an upgrade of Coffer to an agent")."""

from __future__ import annotations

import pytest

from coffer.application.upgrade_handoff import (
    INSTALL_PAGE,
    InstallFacts,
    InstallMethod,
    upgrade_handoff,
)
from coffer.infrastructure.daemon.install_method import install_facts


@pytest.mark.acceptance(
    spec="daemon", scenario="the upgrade hand-off names how this copy was installed"
)
def test_the_prompt_names_the_version_the_install_method_and_the_upgrade_page() -> None:
    prompt = upgrade_handoff(
        "0.3.1",
        InstallFacts(
            method=InstallMethod.BINARIES, executable="/h/.coffer/bin/0.3.1/coffer-daemon"
        ),
        "macOS 15.6, arm64",
    )
    assert "Coffer 0.3.1." in prompt
    assert "/h/.coffer/bin/0.3.1/coffer-daemon" in prompt
    assert f"{INSTALL_PAGE}#upgrade" in prompt
    assert "`coffer update`" in prompt
    assert "Keep ~/.coffer exactly as it is" in prompt
    assert "`coffer daemon status`" in prompt and "`coffer --version`" in prompt
    assert "macOS 15.6, arm64" in prompt
    assert "I will log in myself" in prompt


def test_a_source_run_names_its_checkout() -> None:
    prompt = upgrade_handoff(
        "0.3.1",
        InstallFacts(method=InstallMethod.SOURCE, executable="/r/.venv/bin/python", checkout="/r"),
        "m",
    )
    assert "the source checkout at /r" in prompt


def test_the_install_method_is_read_off_the_process() -> None:
    app = install_facts(
        frozen=True, executable="/Applications/Coffer.app/Contents/MacOS/coffer-daemon"
    )
    assert app.method is InstallMethod.APP
    binaries = install_facts(frozen=True, executable="/h/.coffer/bin/coffer-daemon")
    assert binaries.method is InstallMethod.BINARIES
    source = install_facts(frozen=False, executable="/x/python")
    assert source.method is InstallMethod.SOURCE
