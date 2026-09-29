"""Memory triggers, pure and on disk (spec memory "Guard a known trap once per
session", "Keep triggers in the vault, armed only by a person"): how a shell
command splits into executing segments, what a ``block`` and a ``context``
trigger match, what ``validate`` refuses, the vault file round trip, and the
per-session ledger that makes a guard fire once."""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.memory.session_ledger import SessionLedger
from coffer.application.memory.triggers import TriggerDraft, TriggerService
from coffer.domain.memory.trigger import (
    KIND_BLOCK,
    KIND_CONTEXT,
    Trigger,
    TriggerInvalid,
    TriggerNotFound,
    matches_command,
    matches_error,
    segments,
    validate,
)
from coffer.infrastructure.memory import paths, trigger_store
from tests.unit.memory.conftest import FakeAudit


@pytest.fixture(autouse=True)
def _triggers_root(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    root = tmp_path / "vault" / "memory-triggers"
    monkeypatch.setenv("COFFER_MEMORY_TRIGGERS_ROOT", str(root))
    return root


def _block(command: str, *, unless: str = "", note: str = "coffer/node-20") -> Trigger:
    return Trigger(id="t1", note=note, kind=KIND_BLOCK, command=command, unless=unless)


# --- segments -----------------------------------------------------------------


def _programs(command: str) -> list[str]:
    return [s.program for s in segments(command)]


def test_a_plain_command_is_one_segment() -> None:
    (seg,) = segments("make verify")
    assert (seg.env, seg.program, seg.text) == ("", "make", "make verify")


def test_var_prefixes_are_split_off_the_program() -> None:
    (seg,) = segments("PATH=/opt/node20/bin:$PATH CI=1 make verify")
    assert seg.program == "make"
    assert seg.env.split() == ["PATH=/opt/node20/bin:$PATH", "CI=1"]
    assert seg.text == "make verify"


def test_separators_start_new_segments() -> None:
    assert _programs("cd web && npm test || echo failed; ls | wc -l") == [
        "cd",
        "npm",
        "echo",
        "ls",
        "wc",
    ]
    assert _programs("echo one\nmake verify") == ["echo", "make"]


def test_a_program_named_by_path_is_matched_by_its_base_name() -> None:
    assert _programs("/usr/bin/make verify") == ["make"]
    assert _programs("./scripts/e2e.sh --headed") == ["e2e.sh"]


def test_a_subshell_or_command_substitution_is_its_own_segment() -> None:
    assert "make" in _programs("echo $(make verify)")
    assert "git" in _programs("$(git rev-parse --show-toplevel)/run.sh")
    assert _programs("(cd web; npm test)")[:1] == ["cd"]
    assert [s.text for s in segments("(cd web && make verify)")] == ["cd web", "make verify"]
    assert "make verify" in [s.text for s in segments("echo `make verify`")]


def test_an_interpreter_skips_leading_flags_but_not_inline_code() -> None:
    (seg,) = segments("sh -x scripts/e2e.sh")
    assert seg.text.startswith("e2e.sh")
    assert matches_command(_block("e2e"), "sh -x scripts/e2e.sh")
    (seg,) = segments("python3 -m pytest")
    assert seg.text.startswith("python3 -m")
    (seg,) = segments("bash -c 'make verify'")
    assert seg.text.startswith("bash -c")


def test_an_empty_command_has_no_segments() -> None:
    assert list(segments("")) == []


# --- matches_command ------------------------------------------------------------


def test_block_matches_the_executing_segment() -> None:
    t = _block(r"^make\s+verify\b")
    assert matches_command(t, "make verify")
    assert matches_command(t, "cd repo && make verify")
    assert matches_command(t, "CI=1 /usr/bin/make verify -j4")
    assert not matches_command(t, "make test")
    assert not matches_command(t, "echo make verify is slow")


def test_unless_matched_on_the_whole_command_keeps_the_trigger_quiet() -> None:
    t = _block(r"^make\s+verify\b", unless="v20")
    assert matches_command(t, "make verify")
    assert not matches_command(t, "PATH=$HOME/.nvm/versions/node/v20.20.2/bin:$PATH make verify")


@pytest.mark.acceptance(spec="memory", scenario="a command that only mentions the pattern passes")
def test_a_pattern_naming_e2e_passes_cat_and_holds_the_script_run() -> None:
    t = _block("e2e")
    assert not matches_command(t, "cat scripts/e2e.sh")
    assert not matches_command(t, "grep -n e2e Makefile")
    assert matches_command(t, "bash scripts/e2e.sh")
    assert matches_command(t, "./scripts/e2e.sh --headed")
    assert matches_command(t, "CI=1 python3 tools/e2e.py")


def test_an_interpreter_running_a_script_starts_at_the_script() -> None:
    (seg,) = segments("bash scripts/e2e.sh --headed")
    assert seg.text == "e2e.sh --headed"
    (seg,) = segments("cat scripts/e2e.sh")
    assert seg.text == "cat scripts/e2e.sh"
    (seg,) = segments("python3 -m pytest")
    assert seg.text == "python3 -m pytest"


def test_matching_is_anchored_at_the_start_of_what_executes() -> None:
    t = _block(r"make\b.*\bverify")
    assert matches_command(t, "PATH=$HOME/.nvm/bin:$PATH make verify")
    assert not matches_command(t, "echo make verify")
    assert not matches_command(_block("install"), "pip install requests")
    assert matches_command(_block(r"pip3?\s+install\b"), "pip install requests")


def test_no_pattern_or_no_command_matches_nothing() -> None:
    assert not matches_command(_block(""), "make verify")
    assert not matches_command(_block("make"), "")


# --- matches_error ---------------------------------------------------------------


def _context(error: str, command: str = "") -> Trigger:
    return Trigger(
        id="c1", note="global/gnu-timeout", kind=KIND_CONTEXT, error=error, command=command
    )


def test_context_matches_the_output() -> None:
    t = _context("timeout: command not found")
    assert matches_error(t, "timeout 5 make", "zsh: timeout: command not found\n")
    assert not matches_error(t, "timeout 5 make", "ok\n")
    assert not matches_error(t, "timeout 5 make", "")


def test_context_with_a_command_also_needs_the_command() -> None:
    t = _context("not found", command=r"^timeout\b")
    assert matches_error(t, "timeout 5 make", "timeout: command not found")
    assert not matches_error(t, "ls missing", "ls: missing: not found")


# --- validate --------------------------------------------------------------------


def test_a_well_formed_trigger_validates_unchanged() -> None:
    t = _block(r"^make verify", unless="v20")
    assert validate(t) is t


@pytest.mark.parametrize(
    ("trigger", "says"),
    [
        (Trigger(id="t", note="coffer/x", kind="shout", command="x"), "kind"),
        (Trigger(id="t", note="coffer/x", kind=KIND_BLOCK, command="(unclosed"), "command"),
        (Trigger(id="t", note="coffer/x", kind=KIND_BLOCK, command="x", unless="["), "unless"),
        (Trigger(id="t", note="coffer/x", kind=KIND_BLOCK), "command pattern"),
        (Trigger(id="t", note="coffer/x", kind=KIND_CONTEXT), "error pattern"),
        (Trigger(id="t", note="no-slash", kind=KIND_BLOCK, command="x"), "note"),
        (Trigger(id="t", note="../etc/passwd", kind=KIND_BLOCK, command="x"), "note"),
        (Trigger(id="t", note="coffer/../x", kind=KIND_BLOCK, command="x"), "note"),
        (Trigger(id="../evil", note="coffer/x", kind=KIND_BLOCK, command="x"), "id"),
    ],
)
def test_validate_refuses_what_cannot_be_used(trigger: Trigger, says: str) -> None:
    with pytest.raises(TriggerInvalid, match=says) as caught:
        validate(trigger)
    assert caught.value.code == "MEMORY_TRIGGER_INVALID"


# --- the vault file ----------------------------------------------------------------


def test_a_trigger_round_trips_through_its_file(_triggers_root: pathlib.Path) -> None:
    t = Trigger(
        id="node-20-abc123",
        note="coffer/node-20-for-make-verify",
        kind=KIND_BLOCK,
        command=r"^make\s+verify\b",
        unless="v20",
        armed_by="user",
        armed_at="2026-09-30T00:00:00+00:00",
        created="2026-09-30T00:00:00+00:00",
        body="Use Node 20.",
    )
    path = trigger_store.write_trigger(t)
    assert path == _triggers_root / "node-20-abc123.md"
    assert paths.triggers_root() == _triggers_root
    assert trigger_store.read_trigger(t.id) == t
    assert trigger_store.list_triggers() == [t]
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n") and "note: coffer/node-20-for-make-verify" in text


def test_a_proposal_reads_back_unarmed() -> None:
    t = Trigger(id="p1", note="coffer/x", kind=KIND_BLOCK, command="x", proposed_by="distil")
    trigger_store.write_trigger(t)
    back = trigger_store.read_trigger("p1")
    assert back.proposed_by == "distil" and not back.armed
    assert back.arm("user", "now").armed and not back.arm("user", "now").disarm().armed


def test_an_unparseable_file_is_skipped_not_fatal(_triggers_root: pathlib.Path) -> None:
    good = Trigger(id="good", note="coffer/x", kind=KIND_BLOCK, command="x", armed_by="user")
    trigger_store.write_trigger(good)
    (_triggers_root / "bad-regex.md").write_text(
        "---\nnote: coffer/x\nkind: block\ncommand: '(unclosed'\n---\n", encoding="utf-8"
    )
    (_triggers_root / "not-yaml.md").write_text("---\n: : :\n  - [\n---\n", encoding="utf-8")
    assert [t.id for t in trigger_store.list_triggers()] == ["good"]


def test_an_invalid_trigger_is_never_written(_triggers_root: pathlib.Path) -> None:
    with pytest.raises(TriggerInvalid):
        trigger_store.write_trigger(Trigger(id="x", note="coffer/x", kind=KIND_BLOCK, command="("))
    assert not _triggers_root.exists() or not any(_triggers_root.iterdir())


def test_no_directory_lists_nothing_and_a_missing_id_is_not_found() -> None:
    assert trigger_store.list_triggers() == []
    with pytest.raises(TriggerNotFound):
        trigger_store.read_trigger("nope")
    with pytest.raises(TriggerNotFound):
        trigger_store.delete_trigger("nope")


def test_delete_removes_the_file(_triggers_root: pathlib.Path) -> None:
    trigger_store.write_trigger(Trigger(id="d", note="coffer/x", kind=KIND_BLOCK, command="x"))
    trigger_store.delete_trigger("d")
    assert not (_triggers_root / "d.md").exists()


# --- the session ledger ---------------------------------------------------------------


def test_a_trigger_fires_once_per_session_not_once_ever() -> None:
    ledger = SessionLedger()
    assert not ledger.has_fired("s1", "t1")
    ledger.mark_fired("s1", "t1")
    assert ledger.has_fired("s1", "t1")
    assert not ledger.has_fired("s2", "t1")
    assert not ledger.has_fired("s1", "t2")


def test_delivered_notes_are_per_session() -> None:
    ledger = SessionLedger()
    ledger.mark_delivered("s1", ["coffer/a", "global/b"])
    ledger.mark_delivered("s1", ["coffer/c"])
    assert ledger.delivered("s1") == {"coffer/a", "global/b", "coffer/c"}
    assert ledger.delivered("s2") == frozenset()


def test_the_ledger_forgets_the_least_recently_used_session_past_its_bound() -> None:
    ledger = SessionLedger(max_sessions=2)
    ledger.mark_fired("old", "t")
    ledger.mark_fired("mid", "t")
    ledger.mark_delivered("old", ["coffer/a"])  # touching "old" makes "mid" the oldest
    ledger.mark_fired("new", "t")
    assert ledger.has_fired("old", "t")
    assert not ledger.has_fired("mid", "t")
    assert ledger.has_fired("new", "t")


# --- the trigger service's audit trail -------------------------------------------------


@pytest.mark.asyncio
async def test_every_trigger_act_is_audited_with_the_trigger_and_its_note_only() -> None:
    audit = FakeAudit()
    svc = TriggerService(audit=audit)  # type: ignore[arg-type]
    note = "coffer/node-20-for-make-verify"
    tid = (await svc.add(TriggerDraft(note=note, command=r"make\s+verify"), actor="user")).id
    await svc.disarm(tid, actor="user")
    await svc.arm(tid, actor="user")
    await svc.delete(tid, actor="user")
    assert [(e, a) for e, a, _d in audit.events] == [
        ("memory_trigger_added", "user"),
        ("memory_trigger_disarmed", "user"),
        ("memory_trigger_armed", "user"),
        ("memory_trigger_deleted", "user"),
    ]
    for _e, _a, details in audit.events:
        assert details == {"trigger": tid, "note": note, "kind": "block"}
    assert svc.all() == []
