"""Every tree Coffer keeps sits in the class directory its nature gives it
(ADR storage-is-five-classes-by-nature), resolved from ``HOME`` at the moment
it is asked for — no per-tree override, nothing cached.

- **vault** (the repository): knowledge collections, skill master folders,
  memory triggers;
- **content** (the user's only copy, not synced): chat uploads, channel media,
  the chat workspace;
- **derived** (always rebuildable): the memory tree, the builtin skill's
  rendered folder, the transcript summary cache.
"""

from __future__ import annotations

import os
import pathlib

import pytest

from coffer.application.binary_deploy import user_bin_dir
from coffer.infrastructure.channel import seatalk_media, telegram_media
from coffer.infrastructure.channel.media_root import default_media_dir
from coffer.infrastructure.channel.seatalk_sdk import sdk_dir
from coffer.infrastructure.chat.default_workspace import default_workspace_dir
from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.knowledge.paths import knowledge_root
from coffer.infrastructure.logging.files import log_dir
from coffer.infrastructure.memory.paths import memory_root
from coffer.infrastructure.model_proxy.info import info_path
from coffer.infrastructure.model_proxy.spool import spool_dir
from coffer.infrastructure.skill.master_store import MasterStore, default_master_root
from coffer.infrastructure.usage.spool_reader import default_spool_dir
from coffer.infrastructure.vault.home import daemon_json_path

_REMOVED_OVERRIDES = (
    "COFFER_KNOWLEDGE_ROOT",
    "COFFER_SKILLS_ROOT",
    "COFFER_MEMORY_ROOT",
    "COFFER_AGENT_STATE_ROOT",
)


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path / ".coffer"


def test_vault_trees_are_inside_the_vault_repository(home: pathlib.Path) -> None:
    assert knowledge_root() == home / "vault" / "knowledge"
    assert default_master_root() == home / "vault" / "skills"


def test_content_trees_are_under_content(home: pathlib.Path) -> None:
    assert default_media_dir() == home / "content" / "channel-media"
    # One helper names the channel media directory for every channel.
    assert telegram_media.default_media_dir is default_media_dir
    assert seatalk_media.default_media_dir is default_media_dir
    workspace = pathlib.Path(default_workspace_dir())
    assert workspace == home / "content" / "workspace"
    assert workspace.is_dir()


def test_derived_trees_are_under_derived(home: pathlib.Path) -> None:
    assert memory_root() == home / "derived" / "memory"
    store = MasterStore()
    assert store.paths_for("coffer-guide").folder == (home / "derived" / "skills" / "coffer-guide")
    assert store.paths_for("my-skill").folder == (home / "vault" / "skills" / "my-skill")


def test_every_root_follows_home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "one"))
    first = (knowledge_root(), memory_root(), default_media_dir())
    monkeypatch.setenv("HOME", str(tmp_path / "two"))
    second = (knowledge_root(), memory_root(), default_media_dir())
    for a, b in zip(first, second, strict=True):
        assert a.relative_to(tmp_path / "one") == b.relative_to(tmp_path / "two")


@pytest.mark.parametrize("name", _REMOVED_OVERRIDES)
def test_a_retired_override_moves_nothing(
    name: str, home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(name, "/elsewhere")
    roots = (
        knowledge_root(),
        default_master_root(),
        memory_root(),
    )
    assert all(str(root).startswith(str(home)) for root in roots), roots
    assert os.environ[name] == "/elsewhere"


def test_the_runtime_files_beside_the_classes_keep_their_names(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every helper that names an entry directly under ``~/.coffer`` asks
    ``vault/home.py`` for it, and the names are the ones earlier builds wrote."""
    for name in ("COFFER_LOG_DIR", "COFFER_PROXY_SPOOL_DIR", "COFFER_SEATALK_SDK_DIR"):
        monkeypatch.delenv(name, raising=False)
    assert daemon_json_path() == bootstrap._daemon_json_path() == home / "daemon.json"
    assert bootstrap._spawn_lock_path() == home / "daemon.lock"
    assert daemon_config.config_path() == home / "daemon-config.json"
    assert log_dir() == home / "logs"
    assert user_bin_dir() == home / "bin"
    assert sdk_dir() == home / "vendor"
    assert info_path() == home / "proxy.json"
    assert spool_dir() == default_spool_dir() == home / "proxy-usage"
