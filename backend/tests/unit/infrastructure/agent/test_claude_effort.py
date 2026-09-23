"""Unit tests for ``claude_effort`` and the two sources that carry its answer.

The point of the module is that Coffer writes no level down: the menu is the
installed SDK's own ``EffortLevel``, the same alias the SDK turns into the CLI's
``--effort`` flag. So these assert the RELATIONSHIP — every Claude Code entry
reports exactly what that alias says — rather than a copy of today's five
levels, which is the list this design exists to avoid pinning anywhere.
"""

from __future__ import annotations

import pathlib
from typing import get_args

import pytest

from coffer.infrastructure.agent.claude_effort import claude_effort_levels
from coffer.infrastructure.agent.model_discovery import NativeConfigModelDiscovery


def test_the_levels_are_the_installed_sdks_own_alias() -> None:
    from claude_agent_sdk import EffortLevel

    assert claude_effort_levels() == tuple(get_args(EffortLevel))
    # Non-empty on a real install: an empty answer would silently hide every
    # effort control, which is the failure this source exists to end.
    assert claude_effort_levels()


@pytest.mark.acceptance(
    spec="agent-registry", scenario="offer no effort levels when the runtime declares none"
)
def test_an_sdk_without_the_alias_simply_offers_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """An older pin or a partial install is an ordinary state of the world, not
    an error: the pickers hide themselves and turns run as they did before."""
    claude_effort_levels.cache_clear()
    monkeypatch.delitem(__import__("sys").modules, "claude_agent_sdk", raising=False)
    monkeypatch.setattr(
        "builtins.__import__",
        _refusing_import("claude_agent_sdk"),
    )
    try:
        assert claude_effort_levels() == ()
    finally:
        claude_effort_levels.cache_clear()


def _refusing_import(blocked: str):  # type: ignore[no-untyped-def]
    real = __import__

    def _import(name: str, *args: object, **kw: object):  # type: ignore[no-untyped-def]
        if name == blocked:
            raise ImportError(name)
        return real(name, *args, **kw)  # type: ignore[arg-type]

    return _import


async def test_the_native_config_options_carry_the_same_levels(tmp_path: pathlib.Path) -> None:
    """The ``.claude.json`` cache describes extra MODELS; the level is the
    runtime's option, not any model's property — so an option chosen from here
    must not make the effort control blink out."""
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    (config_dir / ".claude.json").write_text(
        '{"additionalModelOptionsCache": [{"value": "claude-opus-5[1m]", "label": "Opus 1M"}]}',
        encoding="utf-8",
    )

    models = await NativeConfigModelDiscovery().discover(
        agent_key="claude_code", config_dir=config_dir
    )

    assert [m.id for m in models] == ["claude-opus-5[1m]"]
    assert models[0].efforts == claude_effort_levels()
    # No default is named: the SDK exposes none machine-readably, and a picker
    # naming the wrong one is worse than one naming none.
    assert models[0].default_effort is None
