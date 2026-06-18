"""Unit tests for FsPluginDetailReader — reads a plugin's manifest + bundles
from a real (tmp) install dir, degrading to None/empty on missing or malformed
input rather than raising.
"""

from __future__ import annotations

import json
import pathlib

from coffer.infrastructure.agent.plugin_bundle import FsPluginDetailReader


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_reads_manifest_and_bundles(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "cache" / "mkt" / "hud" / "0.1.0"
    _write(
        root / ".claude-plugin" / "plugin.json",
        json.dumps(
            {
                "name": "hud",
                "version": "0.1.0",
                "description": "Real-time HUD",
                "author": {"name": "Jarrod Watts", "url": "https://example"},
                "homepage": "https://example/hud",
                "repository": "https://example/repo",
            }
        ),
    )
    # Bundled skills (dirs), commands (*.md), and an .mcp.json with two servers.
    (root / "skills" / "brainstorming").mkdir(parents=True)
    (root / "skills" / "tdd").mkdir(parents=True)
    (root / "skills" / ".hidden").mkdir(parents=True)  # ignored
    _write(root / "commands" / "setup.md", "# setup")
    _write(root / "commands" / "configure.md", "# configure")
    _write(root / "commands" / "notes.txt", "ignored")  # not a .md
    _write(root / ".mcp.json", json.dumps({"mcpServers": {"weather": {}, "files": {}}}))

    detail = FsPluginDetailReader().read(str(root))

    assert detail is not None
    assert detail.version == "0.1.0"
    assert detail.description == "Real-time HUD"
    assert detail.author == "Jarrod Watts"  # object → name
    assert detail.homepage == "https://example/hud"  # homepage preferred over repository
    assert detail.skills == ("brainstorming", "tdd")  # sorted, hidden excluded
    assert detail.commands == ("configure", "setup")  # stems, sorted, .txt excluded
    assert detail.mcp_servers == ("files", "weather")


def test_codex_shape_descends_to_version_subdir(tmp_path: pathlib.Path) -> None:
    # Codex records no install path, so the service passes the cache
    # <marketplace>/<name> parent; the manifest lives one level down in the
    # version dir, at .codex-plugin/plugin.json (not .claude-plugin/).
    name_dir = tmp_path / "cache" / "openai-primary-runtime" / "documents"
    version_dir = name_dir / "26.506.11943"
    _write(
        version_dir / ".codex-plugin" / "plugin.json",
        json.dumps(
            {
                "version": "26.506.11943",
                "description": "Edit documents",
                "author": {"name": "OpenAI"},
                "homepage": "https://openai.com/",
            }
        ),
    )
    (version_dir / "skills" / "documents").mkdir(parents=True)

    detail = FsPluginDetailReader().read(str(name_dir))  # the parent, not the version dir

    assert detail is not None
    assert detail.version == "26.506.11943"
    assert detail.description == "Edit documents"
    assert detail.author == "OpenAI"
    assert detail.skills == ("documents",)


def test_multiple_version_subdirs_picks_highest(tmp_path: pathlib.Path) -> None:
    # When several versions are cached, pick the highest by real version order —
    # a plain string sort would wrongly rank "9.0" above "26.1".
    name_dir = tmp_path / "cache" / "mkt" / "p"
    for ver in ("9.0", "26.1"):
        _write(
            name_dir / ver / ".codex-plugin" / "plugin.json",
            json.dumps({"version": ver, "description": f"v{ver}"}),
        )

    detail = FsPluginDetailReader().read(str(name_dir))

    assert detail is not None
    assert detail.version == "26.1"  # not "9.0"


def test_missing_path_returns_none(tmp_path: pathlib.Path) -> None:
    assert FsPluginDetailReader().read("") is None
    assert FsPluginDetailReader().read(str(tmp_path / "nope")) is None


def test_empty_dir_yields_empty_detail(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "bare"
    root.mkdir()
    detail = FsPluginDetailReader().read(str(root))
    assert detail is not None
    assert detail.description is None and detail.author is None and detail.homepage is None
    assert detail.skills == () and detail.commands == () and detail.mcp_servers == ()


def test_malformed_manifest_tolerated_bundles_still_read(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "p"
    _write(root / ".claude-plugin" / "plugin.json", "{not json")
    (root / "skills" / "only").mkdir(parents=True)
    detail = FsPluginDetailReader().read(str(root))
    assert detail is not None
    assert detail.description is None  # manifest unreadable → no metadata
    assert detail.skills == ("only",)  # but bundle enumeration is independent


def test_author_as_string_and_repository_fallback(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "p"
    _write(
        root / ".claude-plugin" / "plugin.json",
        json.dumps({"author": "Jane Doe", "repository": "https://example/repo"}),
    )
    detail = FsPluginDetailReader().read(str(root))
    assert detail is not None
    assert detail.author == "Jane Doe"  # bare string author
    assert detail.homepage == "https://example/repo"  # falls back to repository
