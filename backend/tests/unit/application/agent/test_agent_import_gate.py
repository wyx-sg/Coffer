"""The agent import gate tells "never on this machine" from "not yet".

An ``agent`` document whose ``config_dir`` does not exist here can never
apply: the round must record it as not applicable rather than retry it every
round (spec vault-sync). The gate is what names the difference, through the
error code the round classifies.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.agent.sync_reconcile import AgentImportGate
from coffer.application.sync.convergence_ops import is_inapplicable
from coffer.domain.errors import CofferError, SkillDirNotWritable


async def test_a_missing_config_dir_is_refused_as_not_applicable_here(
    tmp_path: pathlib.Path,
) -> None:
    missing = tmp_path / "no-such-agent-home"
    with pytest.raises(CofferError) as caught:
        await AgentImportGate().validate({"type": "claude_code", "config_dir": str(missing)})
    assert caught.value.code == "AGENT_CONFIG_DIR_MISSING"
    assert is_inapplicable(caught.value)
    # The gate never mkdir's a config dir into being.
    assert not missing.exists()


async def test_an_existing_config_dir_passes_and_gets_its_skill_dir(
    tmp_path: pathlib.Path,
) -> None:
    home = tmp_path / "claude-home"
    home.mkdir()
    await AgentImportGate().validate({"type": "claude_code", "config_dir": str(home)})
    assert (home / "skills").is_dir()


async def test_an_unusable_skill_dir_is_still_a_retryable_refusal(
    tmp_path: pathlib.Path,
) -> None:
    home = tmp_path / "claude-home"
    home.mkdir()
    (home / "skills").write_text("a file where the skill dir should be")
    with pytest.raises(SkillDirNotWritable) as caught:
        await AgentImportGate().validate({"type": "claude_code", "config_dir": str(home)})
    assert not is_inapplicable(caught.value)
