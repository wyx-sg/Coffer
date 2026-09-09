"""Unit tests for ``ClaudeBinaryModelDiscovery``.

The real Claude Code executable is ~200 MB and is not installed on CI, so every
test here writes a tiny byte-string fixture in the exact shape the bundle uses
(the marker comment, a couple of catalog entries, and the two array literals the
alias anchor keys off) and points the adapter at it with a stubbed PATH lookup.

The point of the failure tests: this source reads an implementation detail of a
release Coffer does not control, so it MUST degrade to an empty list on every
shape it does not recognise rather than raise or return junk.
"""

from __future__ import annotations

import os
import pathlib

import pytest

from coffer.infrastructure.agent.claude_binary_models import ClaudeBinaryModelDiscovery

_MARKER = b"Hand-maintained baked-in model catalog"

#: The id array followed by the alias array, exactly as the bundle emits them:
#: minified variable names, one statement, no whitespace.
_ARRAYS = (
    b'var jVt=["claude-3-5-haiku","claude-opus-4-8","claude-opus-5"],'
    b'jP=["sonnet","opus","fable","opus[1m]","opusplan"],'
    b'BAt=["sonnet","opus"];'
)

#: Two catalog entries: one without a knowledge cutoff, one with — and in the
#: bundle's own oldest-first order, so a correct reader flips them.
_CATALOG = (
    b'models:[{id:"claude-3-5-haiku",family:"haiku",display_name:"Haiku 3.5",'
    b"provider_ids:{},advisor_rank:9},"
    b'{id:"claude-opus-5",family:"opus",display_name:"Opus 5",'
    b'knowledge_cutoff:"May 2026",provider_ids:{},advisor_rank:1}]'
)


def _bundle(
    path: pathlib.Path,
    *,
    arrays: bytes = _ARRAYS,
    marker: bytes = _MARKER,
    catalog: bytes = _CATALOG,
    padding: int = 0,
) -> pathlib.Path:
    """Write a fake bundle: filler, the arrays, the marker, then the catalog."""
    path.write_bytes(b"x" * padding + arrays + marker + b'",schema_version:1,' + catalog)
    return path


@pytest.fixture()
def discovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> ClaudeBinaryModelDiscovery:
    """An adapter whose PATH lookup resolves to ``tmp_path/claude``."""
    binary = tmp_path / "claude"
    monkeypatch.setattr(
        "coffer.infrastructure.agent.claude_binary_models.shutil.which",
        lambda name: str(binary) if binary.exists() else None,
    )
    return ClaudeBinaryModelDiscovery()


async def test_aliases_lead_then_the_catalog_newest_first(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    _bundle(tmp_path / "claude")

    models = await discovery.discover(agent_key="claude_code", config_dir=None)

    assert [m.id for m in models] == [
        # The alias array, verbatim and in bundle order.
        "sonnet",
        "opus",
        "fable",
        "opus[1m]",
        "opusplan",
        # Then the catalog, reversed out of its oldest-first order.
        "claude-opus-5",
        "claude-3-5-haiku",
    ]
    assert [m.source for m in models[:5]] == ["alias"] * 5
    assert [m.source for m in models[5:]] == ["discovered"] * 2


async def test_versioned_labels_and_the_knowledge_cutoff_survive(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """The display name is the reason this source exists: it is the only place
    that distinguishes one release of a tier from the next."""
    _bundle(tmp_path / "claude")

    models = {m.id: m for m in await discovery.discover(agent_key="claude_code", config_dir=None)}

    assert models["claude-opus-5"].label == "Opus 5"
    assert models["claude-opus-5"].description == "Knowledge cutoff May 2026"
    # No cutoff in the entry — no invented prose.
    assert models["claude-3-5-haiku"].label == "Haiku 3.5"
    assert models["claude-3-5-haiku"].description == ""


async def test_aliases_are_never_written_down_here(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """Renaming every alias in the bundle renames them in the output — proof the
    anchor is structural and no alias is hardcoded in the adapter."""
    (tmp_path / "claude").write_bytes(
        b'var a=["claude-x-1","claude-x-2"],b=["tier-one","tier-two"];' + _MARKER
    )

    models = await discovery.discover(agent_key="claude_code", config_dir=None)

    assert [m.id for m in models] == ["tier-one", "tier-two"]


async def test_the_scan_is_cached_until_the_binary_changes(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """A 200 MB scan must not run per HTTP request; an upgrade must still land."""
    binary = _bundle(tmp_path / "claude")
    first = await discovery.discover(agent_key="claude_code", config_dir=None)

    # Rewrite the content but keep the same mtime+size → the cache still wins.
    stat = binary.stat()
    binary.write_bytes(b"y" * stat.st_size)
    os.utime(binary, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert await discovery.discover(agent_key="claude_code", config_dir=None) == first

    # A genuine upgrade changes size (and mtime) → rescanned.
    _bundle(binary, catalog=b'models:[{id:"claude-opus-9",family:"opus",display_name:"Opus 9"}]')
    reread = await discovery.discover(agent_key="claude_code", config_dir=None)
    assert [m.id for m in reread if m.source == "discovered"] == ["claude-opus-9"]


async def test_marker_far_into_the_file_is_still_found(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """The real marker sits ~150 MB in, past many read blocks. Straddle the
    adapter's read-block boundary so a scan that forgot to stitch consecutive
    blocks together would miss the marker entirely."""
    _bundle(tmp_path / "claude", padding=4 * 1024 * 1024 - len(_ARRAYS) - 10)

    models = await discovery.discover(agent_key="claude_code", config_dir=None)

    assert [m.id for m in models if m.source == "discovered"] == [
        "claude-opus-5",
        "claude-3-5-haiku",
    ]


async def test_no_binary_on_path_is_empty(discovery: ClaudeBinaryModelDiscovery) -> None:
    assert await discovery.discover(agent_key="claude_code", config_dir=None) == []


async def test_a_binary_without_the_marker_is_empty(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """A future release that drops the marker costs us this source and nothing
    else."""
    (tmp_path / "claude").write_bytes(b"\x00\x01binary with no catalog in it\xff" * 100)

    assert await discovery.discover(agent_key="claude_code", config_dir=None) == []


async def test_garbage_after_the_marker_is_empty(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    (tmp_path / "claude").write_bytes(_MARKER + b"\xff\xfe not json, not js, not anything")

    assert await discovery.discover(agent_key="claude_code", config_dir=None) == []


async def test_a_window_truncated_mid_entry_yields_only_whole_entries(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """The window is a fixed byte slice, so it can cut an entry in half. A half
    entry is dropped; the whole ones before it still count."""
    (tmp_path / "claude").write_bytes(
        _MARKER
        + b'models:[{id:"claude-opus-5",family:"opus",display_name:"Opus 5"},'
        + b'{id:"claude-opus-6",family:"opus",display_na'
    )

    models = await discovery.discover(agent_key="claude_code", config_dir=None)

    assert [m.id for m in models] == ["claude-opus-5"]


async def test_another_agent_type_is_not_this_adapters_business(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    _bundle(tmp_path / "claude")

    assert await discovery.discover(agent_key="codex", config_dir=tmp_path) == []
