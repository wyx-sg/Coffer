"""The projection transforms are text in, text out (spec provider-switching).

Every file-touching entry point Python offers is replaced with one that fails
the test, then the anthropic and Codex apply/remove transforms run: if any of
them reached for the disk, the call would raise instead of returning text.
"""

from __future__ import annotations

import builtins
import io
import json
import os
import pathlib
import tomllib
from typing import Any, NoReturn

import pytest

from coffer.domain.provider import projection

_EXISTING_SETTINGS = json.dumps({"theme": "dark", "env": {"OTHER": "1"}}, indent=2) + "\n"
_EXISTING_TOML = '# user comment\napproval_policy = "never"\n'
_CATALOG = pathlib.Path("/absolute/elsewhere/coffer-models.json")


def _forbid_file_access(monkeypatch: pytest.MonkeyPatch, attempts: list[str]) -> None:
    def _refuse(name: str):  # type: ignore[no-untyped-def]
        def _raise(*args: Any, **kwargs: Any) -> NoReturn:
            attempts.append(name)
            raise AssertionError(f"projection transform touched the filesystem via {name}")

        return _raise

    monkeypatch.setattr(builtins, "open", _refuse("open"))
    monkeypatch.setattr(io, "open", _refuse("io.open"))
    monkeypatch.setattr(os, "open", _refuse("os.open"))
    monkeypatch.setattr(os, "stat", _refuse("os.stat"))
    monkeypatch.setattr(os, "replace", _refuse("os.replace"))
    for method in (
        "open",
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
        "exists",
        "stat",
        "unlink",
        "mkdir",
        "touch",
    ):
        monkeypatch.setattr(pathlib.Path, method, _refuse(f"Path.{method}"))


@pytest.mark.acceptance(spec="provider-switching", scenario="projection transforms touch no file")
def test_projection_transforms_touch_no_file(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[str] = []
    _forbid_file_access(monkeypatch, attempts)
    helper = projection.anthropic_api_key_helper("0123456789abcdef0123456789abcdef")

    applied_settings = projection.apply_anthropic_settings(
        _EXISTING_SETTINGS,
        base_url="https://gw/anthropic",
        model="m-primary",
        fast_model="m-fast",
        api_key_helper=helper,
    )
    removed_settings = projection.remove_anthropic_settings(applied_settings)

    applied_toml = projection.apply_codex_provider(
        _EXISTING_TOML,
        base_url="https://gw/v1",
        model="m-codex",
        wire_api="responses",
        display_name="Coffer (acme)",
        catalog_path=_CATALOG,
    )
    removed_toml = projection.remove_codex_provider(applied_toml)

    assert attempts == []
    monkeypatch.undo()

    # Each transform returned the new native-config text itself.
    settings = json.loads(applied_settings)
    assert settings["apiKeyHelper"] == helper
    assert settings["env"]["ANTHROPIC_BASE_URL"] == "https://gw/anthropic"
    assert settings["env"]["ANTHROPIC_MODEL"] == "m-primary"
    assert settings["theme"] == "dark"
    after = json.loads(removed_settings)
    assert "apiKeyHelper" not in after
    assert "ANTHROPIC_BASE_URL" not in after.get("env", {})
    assert after["theme"] == "dark"

    doc = tomllib.loads(applied_toml)
    assert doc["model_provider"] == "coffer"
    assert doc["model_providers"]["coffer"]["base_url"] == "https://gw/v1"
    assert doc["model_catalog_json"] == str(_CATALOG)
    assert "# user comment" in applied_toml
    cleared = tomllib.loads(removed_toml)
    assert "coffer" not in cleared.get("model_providers", {})
    assert cleared.get("model_provider") != "coffer"
    assert cleared["approval_policy"] == "never"
