"""Unit tests for ``ClaudeBinaryModelDiscovery``.

The real Claude Code executable is ~200 MB and is not installed on CI, so every
test here writes a tiny byte-string fixture in the exact shape the bundle uses —
the tier-alias arrays, the marker comment, then a couple of catalog entries —
and points the adapter at it with a stubbed PATH lookup. The alias arrays are
kept in the fixture on purpose: they are what the bundle really carries, and one
test exists solely to prove they do NOT reach the picker.

The point of the failure tests: this source reads an implementation detail of a
release Coffer does not control, so it MUST degrade to an empty list on every
shape it does not recognise rather than raise or return junk.

The clock is injected everywhere a retirement date is involved. A test that
asserted "this model is gone by now" against the real clock would pass today and
fail on its own the day a date in the fixture stops being in the future.
"""

from __future__ import annotations

import datetime as dt
import os
import pathlib

import pytest

from coffer.infrastructure.agent.claude_binary_models import ClaudeBinaryModelDiscovery

_MARKER = b"Hand-maintained baked-in model catalog"

#: The day every test pretends it is, unless it says otherwise. It sits between
#: the fixture's past and future retirement dates.
_TODAY = dt.date(2026, 9, 11)

#: The id array followed by the alias array, exactly as the bundle emits them:
#: minified variable names, one statement, no whitespace. Present in the fixture
#: because it is present in the bundle — never because anything reads it.
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


#: The CLI's retirement table, in the bundle's own shape. ``claude-3-5-haiku``
#: is in the catalog above AND here with a date in the past, so a correct reader
#: drops it. ``claude-opus-5`` is here with a date in the FUTURE and must
#: survive. ``claude-opus-4-1`` carries a ``remappedTo`` — the CLI reroutes it
#: silently — and is gone whatever the clock says. ``claude-ghost-1`` is in the
#: table but not the catalog: retiring a model nothing lists is a no-op.
_RETIRE = (
    b'var xD={"claude-opus-4-1":{modelName:"Claude Opus 4.1",retirementDates:{'
    b"firstParty:null,bedrock:null,vertex:null,gateway:null},"
    b'remappedTo:"the latest Opus"},'
    b'"claude-3-5-haiku":{modelName:"Claude 3.5 Haiku",retirementDates:{'
    b'firstParty:"February 19, 2026",bedrock:null,vertex:null,gateway:null}},'
    b'"claude-ghost-1":{modelName:"Claude Ghost",retirementDates:{'
    b'firstParty:"January 5, 2026",bedrock:null,vertex:null,gateway:null}},'
    b'"claude-opus-5":{modelName:"Claude Opus 5",retirementDates:{'
    b'firstParty:"December 31, 2030",bedrock:null,vertex:null,gateway:null}}};'
)


def _bundle(
    path: pathlib.Path,
    *,
    arrays: bytes = _ARRAYS,
    marker: bytes = _MARKER,
    catalog: bytes = _CATALOG,
    retire: bytes = b"",
    padding: int = 0,
) -> pathlib.Path:
    """Write a fake bundle: filler, the arrays, the marker, the catalog, and —
    well past it, as in the real bundle — the retirement table.

    ``retire`` defaults to ABSENT so the catalog tests below say only what they
    are about; the retirement tests pass ``_RETIRE`` explicitly."""
    path.write_bytes(
        b"x" * padding + arrays + marker + b'",schema_version:1,' + catalog + b"y" * 4096 + retire
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
    return ClaudeBinaryModelDiscovery(today=lambda: _TODAY)


async def test_the_catalog_is_returned_newest_first(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    _bundle(tmp_path / "claude")

    models = await discovery.discover(agent_key="claude_code", config_dir=None)

    # The catalog, reversed out of its oldest-first order. Nothing else.
    assert [m.id for m in models] == ["claude-opus-5", "claude-3-5-haiku"]


async def test_the_tier_aliases_are_not_offered(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """The bundle carries ``sonnet``/``opus``/``opus[1m]``/``opusplan`` and this
    source used to emit them, which put label-less duplicates in the picker next
    to the real models they resolve to. Every id returned now names a concrete,
    version-bearing model."""
    _bundle(tmp_path / "claude")

    ids = [m.id for m in await discovery.discover(agent_key="claude_code", config_dir=None)]

    assert not {"sonnet", "opus", "fable", "opus[1m]", "opusplan"} & set(ids)
    assert all(i.startswith("claude-") for i in ids)


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
    assert [m.id for m in reread] == ["claude-opus-9"]


async def test_marker_far_into_the_file_is_still_found(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """The real marker sits ~150 MB in, past many read blocks. Straddle the
    adapter's read-block boundary so a scan that forgot to stitch consecutive
    blocks together would miss the marker entirely."""
    _bundle(tmp_path / "claude", padding=4 * 1024 * 1024 - len(_ARRAYS) - 10)

    models = await discovery.discover(agent_key="claude_code", config_dir=None)

    assert [m.id for m in models] == ["claude-opus-5", "claude-3-5-haiku"]


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


# --- the retirement table ----------------------------------------------------
#
# The catalog is cumulative: it keeps every model the CLI has ever shipped, so a
# raw scan offers names that fail the moment they are picked. The bundle carries
# the CLI's own answer for some of them, and these tests pin that we apply
# exactly the CLI's predicate — a ``remappedTo``, or a first-party date already
# past — and nothing cleverer.


async def test_a_model_whose_retirement_date_has_passed_is_dropped(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    _bundle(tmp_path / "claude", retire=_RETIRE)

    ids = [m.id for m in await discovery.discover(agent_key="claude_code", config_dir=None)]

    # Retired February 2026, and the injected clock says September 2026.
    assert "claude-3-5-haiku" not in ids


async def test_a_model_whose_retirement_is_still_ahead_survives(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """The table lists a date for plenty of models that still work. Only a date
    in the PAST removes one — the CLI's own rule."""
    _bundle(tmp_path / "claude", retire=_RETIRE)

    ids = [m.id for m in await discovery.discover(agent_key="claude_code", config_dir=None)]

    assert ids == ["claude-opus-5"]


async def test_a_remapped_model_is_gone_whatever_the_clock_says(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """``remappedTo`` means the CLI silently reroutes the name to another model,
    so offering it is offering a lie. It carries no date at all."""
    catalog = (
        b'models:[{id:"claude-opus-4-1",family:"opus",display_name:"Opus 4.1"},'
        b'{id:"claude-opus-5",family:"opus",display_name:"Opus 5"}]'
    )
    binary = tmp_path / "claude"
    monkeypatch.setattr(
        "coffer.infrastructure.agent.claude_binary_models.shutil.which",
        lambda name: str(binary),
    )
    _bundle(binary, catalog=catalog, retire=_RETIRE)
    # Long before any date in the fixture — the remap still wins.
    adapter = ClaudeBinaryModelDiscovery(today=lambda: dt.date(2020, 1, 1))

    ids = [m.id for m in await adapter.discover(agent_key="claude_code", config_dir=None)]

    assert ids == ["claude-opus-5"]


async def test_retiring_a_model_the_catalog_never_listed_changes_nothing(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """The two tables are independent lists; the retirement one names models the
    catalog does not carry, and that must not perturb the result."""
    _bundle(tmp_path / "claude", retire=_RETIRE)

    ids = [m.id for m in await discovery.discover(agent_key="claude_code", config_dir=None)]

    assert "claude-ghost-1" not in ids
    assert ids == ["claude-opus-5"]


async def test_a_bundle_without_the_retirement_table_filters_nothing(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """The stated contract: a landmark that stops matching costs a filter, never
    a model wrongly hidden. The whole catalog comes back."""
    _bundle(tmp_path / "claude", retire=b"")

    ids = [m.id for m in await discovery.discover(agent_key="claude_code", config_dir=None)]

    assert ids == ["claude-opus-5", "claude-3-5-haiku"]


async def test_an_unparseable_retirement_date_is_not_a_retirement(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """A date shape this module does not recognise means "no opinion". Reading
    it as "retired" would hide a working model on a release that merely changed
    how it writes dates."""
    _bundle(
        tmp_path / "claude",
        retire=(
            b'var xD={"claude-3-5-haiku":{modelName:"Claude 3.5 Haiku",'
            b'retirementDates:{firstParty:"2026-02-19",bedrock:null}}};'
        ),
    )

    ids = [m.id for m in await discovery.discover(agent_key="claude_code", config_dir=None)]

    assert ids == ["claude-opus-5", "claude-3-5-haiku"]


async def test_the_retirement_verdict_is_recomputed_after_a_date_falls_due(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """The 200 MB scan is cached for the life of the installed binary, which can
    outlast a retirement date. The TABLE is cached; the verdict is not."""
    binary = tmp_path / "claude"
    monkeypatch.setattr(
        "coffer.infrastructure.agent.claude_binary_models.shutil.which",
        lambda name: str(binary),
    )
    _bundle(binary, retire=_RETIRE)
    clock = {"today": dt.date(2026, 1, 1)}
    adapter = ClaudeBinaryModelDiscovery(today=lambda: clock["today"])

    before = [m.id for m in await adapter.discover(agent_key="claude_code", config_dir=None)]
    clock["today"] = dt.date(2026, 3, 1)
    after = [m.id for m in await adapter.discover(agent_key="claude_code", config_dir=None)]

    assert before == ["claude-opus-5", "claude-3-5-haiku"]
    assert after == ["claude-opus-5"]


async def test_a_retirement_table_far_into_the_file_is_still_found(
    discovery: ClaudeBinaryModelDiscovery, tmp_path: pathlib.Path
) -> None:
    """In the real bundle the two landmarks sit half a megabyte apart and the
    scan finds both in ONE pass. Straddle the read-block boundary between them
    so a pass that stopped at the first landmark would miss the table."""
    binary = tmp_path / "claude"
    padding = 4 * 1024 * 1024 - len(_ARRAYS) - 10
    binary.write_bytes(
        b"x" * padding
        + _ARRAYS
        + _MARKER
        + b'",schema_version:1,'
        + _CATALOG
        + b"y" * (4 * 1024 * 1024)
        + _RETIRE
    )

    ids = [m.id for m in await discovery.discover(agent_key="claude_code", config_dir=None)]

    assert ids == ["claude-opus-5"]
