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


# ---------------------------------------------------------------------------
# read_contents — the per-plugin detail read
# ---------------------------------------------------------------------------


def test_read_contents_lists_components_with_descriptions(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "hud" / "0.2.0"
    _write(root / ".claude-plugin" / "plugin.json", json.dumps({"name": "hud"}))
    _write(root / "skills" / "tdd" / "SKILL.md", "---\nname: tdd\ndescription: Test first\n---\n")
    (root / "skills" / "bare").mkdir(parents=True)  # no SKILL.md → no description
    _write(root / "commands" / "setup.md", "---\ndescription: Set it up\n---\nbody")
    _write(root / "commands" / "plain.md", "# no frontmatter")
    _write(
        root / "agents" / "rev.md",
        "---\nname: code-reviewer\ndescription: Reviews diffs\n---\n",
    )
    _write(root / "agents" / "broken.md", "---\nname: [unclosed\n---\n")  # bad YAML
    _write(
        root / "hooks" / "hooks.json",
        json.dumps({"hooks": {"SessionStart": [], "PreToolUse": []}}),
    )
    _write(root / ".mcp.json", json.dumps({"mcpServers": {"hud-srv": {}}}))

    c = FsPluginDetailReader().read_contents(str(root))

    assert c is not None
    assert c.root == str(root)
    assert [(s.name, s.description) for s in c.skills] == [("bare", None), ("tdd", "Test first")]
    assert [(s.name, s.description) for s in c.commands] == [
        ("plain", None),
        ("setup", "Set it up"),
    ]
    # A subagent is named by its frontmatter; unparseable frontmatter falls
    # back to the file stem with no description rather than failing the read.
    assert [(s.name, s.description) for s in c.agents] == [
        ("broken", None),
        ("code-reviewer", "Reviews diffs"),
    ]
    assert c.hooks == ("PreToolUse", "SessionStart")
    assert c.mcp_servers == ("hud-srv",)


def test_read_contents_descends_into_newest_version_dir(tmp_path: pathlib.Path) -> None:
    """Codex hands the ``<marketplace>/<name>`` parent; the root reported is
    the version dir the manifest sits in."""
    parent = tmp_path / "cache" / "m" / "lint"
    _write(parent / "1.0.0" / ".codex-plugin" / "plugin.json", "{}")
    _write(parent / "1.0.0" / "commands" / "fix.md", "")

    c = FsPluginDetailReader().read_contents(str(parent))

    assert c is not None
    assert c.root == str(parent / "1.0.0")
    assert [x.name for x in c.commands] == ["fix"]
    assert c.skills == () and c.agents == () and c.hooks == () and c.mcp_servers == ()


def test_read_contents_missing_dir_is_none(tmp_path: pathlib.Path) -> None:
    assert FsPluginDetailReader().read_contents(str(tmp_path / "gone")) is None
    assert FsPluginDetailReader().read_contents("") is None


def test_read_contents_ignores_malformed_hooks_and_mcp(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "p"
    _write(root / ".claude-plugin" / "plugin.json", "{}")
    _write(root / "hooks" / "hooks.json", "{not json")
    _write(root / ".mcp.json", json.dumps({"mcpServers": ["not", "a", "map"]}))

    c = FsPluginDetailReader().read_contents(str(root))

    assert c is not None
    assert c.hooks == ()
    assert c.mcp_servers == ()


def test_resolve_root_matches_read_contents_root(tmp_path: pathlib.Path) -> None:
    name_dir = tmp_path / "cache" / "mkt" / "hud"
    _write(name_dir / "9.0" / ".codex-plugin" / "plugin.json", "{}")
    _write(name_dir / "26.1" / ".codex-plugin" / "plugin.json", "{}")
    reader = FsPluginDetailReader()

    contents = reader.read_contents(str(name_dir))

    assert contents is not None
    assert reader.resolve_root(str(name_dir)) == contents.root == str(name_dir / "26.1")
    assert reader.resolve_root(str(tmp_path / "missing")) is None
    assert reader.resolve_root("") is None
