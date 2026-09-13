"""Unit tests for ``ClaudeBinaryModelDiscovery``.

The real Claude Code executable is ~200 MB and is not installed on CI, so every
test here writes a tiny byte-string fixture in the exact shape the bundle uses —
the tier-alias arrays, the marker comment, a couple of catalog entries, then the
alias table — and points the adapter at it with a stubbed PATH lookup.

What the tests are for: this source reads an implementation detail of a release
Coffer does not control, so it MUST degrade to an empty list on every shape it
does not recognise rather than raise or return junk — and it must offer the
ALIASES, labelled from the catalog, rather than the catalog's own cumulative
list of versioned ids (which carries models the account cannot run).
"""

from __future__ import annotations

import os
import pathlib

import pytest

from coffer.infrastructure.agent.claude_binary_models import ClaudeBinaryModelDiscovery

_MARKER = b"Hand-maintained baked-in model catalog"

#: The id array followed by the alias array, exactly as the bundle emits them:
#: minified variable names, one statement, no whitespace. Present in the fixture
#: because it is present in the bundle — never because anything reads it.
_ARRAYS = (
    b'var jVt=["claude-3-5-haiku","claude-opus-4-8","claude-opus-5"],'
    b'jP=["sonnet","opus","fable","opus[1m]","opusplan"],'
    b'BAt=["sonnet","opus"];'
)

#: Three catalog entries, in the bundle's own oldest-first order. Only two of
#: them are an alias target; the third is the cumulative history this source no
#: longer offers.
_CATALOG = (
    b'models:[{id:"claude-3-5-haiku",family:"haiku",display_name:"Haiku 3.5",'
    b"provider_ids:{},advisor_rank:9},"
    b'{id:"claude-opus-4-8",family:"opus",display_name:"Opus 4.8",'
    b'knowledge_cutoff:"January 2026",provider_ids:{},advisor_rank:4},'
    b'{id:"claude-opus-5",family:"opus",display_name:"Opus 5",'
    b'knowledge_cutoff:"May 2026",provider_ids:{},advisor_rank:1}]'
)

#: The alias table as the bundle writes it: each alias's first-party default,
#: some with the per-provider deployments Coffer does not configure, then the
#: sibling tables that must stay out of the answer.
_ALIASES = (
    b'aliases:{opus:{default:"claude-opus-5",per_provider:{bedrock:"claude-opus-4-8",'
    b'gateway:"claude-opus-4-8"}},'
    b'haiku:{default:"claude-3-5-haiku"}},'
    b'defaults:{},best:"fable",'
    b'latest_per_family:{opus:"claude-opus-5",haiku:"claude-3-5-haiku"},'
    b"alias_migration:{}"
)


def _bundle(
    path: pathlib.Path,
    *,
    arrays: bytes = _ARRAYS,
    marker: bytes = _MARKER,
    catalog: bytes = _CATALOG,
    aliases: bytes = _ALIASES,
    padding: int = 0,
) -> pathlib.Path:
    """Write a fake bundle: filler, the arrays, the marker, the catalog, and —
    immediately after it, as in the real bundle — the alias table."""
    path.write_bytes(
        b"x" * padding + arrays + marker + b'",schema_version:1,' + catalog + b"," + aliases
    )
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


async def test_the_tier_aliases_are_what_is_offered(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """In the table's own order, and nothing else: the versioned ids stay out
    because nothing on this machine says which of them the account may run."""
    _bundle(tmp_path / "claude")

    models = await discovery.discover(agent_key="claude_code", config_dir=None)

    assert [m.id for m in models] == ["opus", "haiku"]


async def test_each_alias_is_labelled_with_the_model_it_is_today(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """The version is the reason this source exists — it just lives in the
    label now, read from the catalog entry the alias points at."""
    _bundle(tmp_path / "claude")

    models = {m.id: m for m in await discovery.discover(agent_key="claude_code", config_dir=None)}

    assert models["opus"].label == "Opus 5"
    assert models["haiku"].label == "Haiku 3.5"


async def test_the_per_provider_deployments_are_not_aliases(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """``opus`` resolves elsewhere on Bedrock/Vertex/a gateway — deployments
    Coffer does not configure. Reading those as aliases would put ``bedrock``
    in the picker."""
    _bundle(tmp_path / "claude")

    ids = {m.id for m in await discovery.discover(agent_key="claude_code", config_dir=None)}

    assert not {"bedrock", "gateway", "per_provider", "latest_per_family"} & ids


async def test_an_alias_the_catalog_does_not_describe_keeps_its_own_name(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """A model launched into the alias table before the catalog entry lands
    still reaches the picker — with a plainer label, not an empty one."""
    _bundle(
        tmp_path / "claude",
        aliases=b'aliases:{mythos:{default:"claude-mythos-9"}},defaults:{}',
    )

    models = await discovery.discover(agent_key="claude_code", config_dir=None)

    assert [(m.id, m.label) for m in models] == [("mythos", "Mythos")]


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
    _bundle(
        binary,
        catalog=b'models:[{id:"claude-opus-9",family:"opus",display_name:"Opus 9"}]',
        aliases=b'aliases:{opus:{default:"claude-opus-9"}},defaults:{}',
    )
    reread = await discovery.discover(agent_key="claude_code", config_dir=None)
    assert [(m.id, m.label) for m in reread] == [("opus", "Opus 9")]


async def test_marker_far_into_the_file_is_still_found(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """The real marker sits ~150 MB in, past many read blocks. Straddle the
    adapter's read-block boundary so a scan that forgot to stitch consecutive
    blocks together would miss the marker entirely."""
    _bundle(tmp_path / "claude", padding=4 * 1024 * 1024 - len(_ARRAYS) - 10)

    models = await discovery.discover(agent_key="claude_code", config_dir=None)

    assert [m.id for m in models] == ["opus", "haiku"]


async def test_no_binary_on_path_is_empty(discovery: ClaudeBinaryModelDiscovery) -> None:
    assert await discovery.discover(agent_key="claude_code", config_dir=None) == []


async def test_a_binary_without_the_marker_is_empty(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """A future release that drops the marker costs us this source and nothing
    else."""
    (tmp_path / "claude").write_bytes(b"\x00\x01binary with no catalog in it\xff" * 100)

    assert await discovery.discover(agent_key="claude_code", config_dir=None) == []


async def test_a_bundle_without_the_alias_table_is_empty(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """The catalog alone is not an answer any more: a release that moved the
    alias table somewhere this cannot see must cost the source, not put the
    cumulative list of versioned ids back in the picker."""
    _bundle(tmp_path / "claude", aliases=b"")

    assert await discovery.discover(agent_key="claude_code", config_dir=None) == []


async def test_garbage_after_the_marker_is_empty(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    (tmp_path / "claude").write_bytes(_MARKER + b"\xff\xfe not json, not js, not anything")

    assert await discovery.discover(agent_key="claude_code", config_dir=None) == []


async def test_a_window_truncated_mid_alias_yields_only_whole_entries(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """The window is a fixed byte slice, so it can cut an entry in half. A half
    entry is dropped; the whole ones before it still count."""
    (tmp_path / "claude").write_bytes(
        _MARKER
        + b'models:[{id:"claude-opus-5",family:"opus",display_name:"Opus 5"}],'
        + b'aliases:{opus:{default:"claude-opus-5"},sonnet:{default:"claude-sonn'
    )

    models = await discovery.discover(agent_key="claude_code", config_dir=None)

    assert [m.id for m in models] == ["opus"]


async def test_another_agent_type_is_not_this_adapters_business(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    _bundle(tmp_path / "claude")

    assert await discovery.discover(agent_key="codex", config_dir=tmp_path) == []
