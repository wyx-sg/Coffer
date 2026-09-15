"""``run_migrations(url)`` migrates ``url`` and nothing else.

Alembic's ``env.py`` used to resolve the database URL from ``COFFER_DB_URL``
alone, falling back to ``~/.coffer/coffer.db``, and ignored the URL the runner
was given — so any caller that passed an explicit URL without also exporting
the variable would upgrade the developer's real vault. The runner now pins the
URL on the Alembic config and ``env.py`` prefers that over the environment.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.surfaces.http.migrations_runner import _alembic_config, run_migrations


def _url(db: pathlib.Path) -> str:
    return f"sqlite+aiosqlite:///{db}"


@pytest.fixture
def isolated_home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """A throwaway HOME so a fallback to ``~/.coffer/coffer.db`` would be
    visible as a new directory rather than a write into the real vault."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def test_explicit_url_wins_when_env_is_unset(
    tmp_path: pathlib.Path, isolated_home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("COFFER_DB_URL", raising=False)
    target = tmp_path / "x.db"

    run_migrations(_url(target))

    assert target.is_file(), "the URL passed to run_migrations is the one migrated"
    assert not (isolated_home / ".coffer").exists(), "nothing was created under HOME"


def test_explicit_url_wins_over_env(
    tmp_path: pathlib.Path, isolated_home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_target = tmp_path / "from-env.db"
    monkeypatch.setenv("COFFER_DB_URL", _url(env_target))
    target = tmp_path / "x.db"

    run_migrations(_url(target))

    assert target.is_file()
    assert not env_target.exists(), "the environment's database is never touched"
    assert not (isolated_home / ".coffer").exists()


def test_percent_in_url_survives_the_config_round_trip(tmp_path: pathlib.Path) -> None:
    """``set_main_option`` runs through ConfigParser interpolation, so a bare
    ``%`` must be escaped on the way in and come back as itself."""
    url = _url(tmp_path / "100%.db")
    assert _alembic_config(url).get_main_option("sqlalchemy.url") == url
