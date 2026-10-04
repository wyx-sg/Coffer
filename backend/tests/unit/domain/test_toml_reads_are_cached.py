"""Reading an agent's TOML config does not pay for a layout-preserving parse
every time: the reconciler reads the same Codex ``config.toml`` several times
per pass, and a ``tomlkit`` parse of a real one costs hundreds of milliseconds
on the event loop."""

from __future__ import annotations

import pytest
import tomlkit

from coffer.domain.agent.config_files import ConfigFileFormat
from coffer.domain.agent.mcp_install import installed_entry
from coffer.domain.errors import ConfigFileFormatInvalid
from coffer.domain.provider.codex_projection import remove_codex_provider

_TEXT = '[mcp_servers.coffer]\ncommand = "/bin/shim"\nargs = ["--agent-uid", "u1"]\n'


def test_reading_the_installed_entry_never_runs_the_tomlkit_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise AssertionError("a read must not use the layout-preserving parser")

    monkeypatch.setattr(tomlkit, "parse", boom)
    entry = installed_entry(ConfigFileFormat.TOML, _TEXT)
    assert entry == {"command": "/bin/shim", "args": ["--agent-uid", "u1"]}


def test_a_malformed_toml_read_is_still_a_format_error() -> None:
    with pytest.raises(ConfigFileFormatInvalid):
        installed_entry(ConfigFileFormat.TOML, "[mcp_servers\n")


def test_removing_the_provider_from_the_same_text_parses_it_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remove_codex_provider.cache_clear()
    calls = 0
    real = tomlkit.parse

    def counting(text: str):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return real(text)

    monkeypatch.setattr(tomlkit, "parse", counting)
    text = 'model = "x"\n' + _TEXT
    first = remove_codex_provider(text)
    for _ in range(5):
        assert remove_codex_provider(text) == first
    assert calls == 1
