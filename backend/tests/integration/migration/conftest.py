from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from coffer.infrastructure.vault.instance import forget
from coffer.surfaces.http.migrations_runner import upgrade_to

from .legacy_home import LegacyHome, build_legacy_home


@pytest.fixture(autouse=True)
def _fresh_writers() -> Iterator[None]:
    """Each test's vault gets its own writer, not one a previous test left."""
    forget()
    yield
    forget()


@pytest.fixture
def legacy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> LegacyHome:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text("[user]\n\tname = t\n\temail = t@t\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("COFFER_DB_URL", raising=False)
    return build_legacy_home(home)


UPGRADE = upgrade_to
