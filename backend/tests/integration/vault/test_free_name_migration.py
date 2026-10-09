"""The one-time move of a provider's or a channel's title into its name, and of
its file to ``<uid>.json`` (ADR provider-and-channel-names-are-free-text).
Delete with ``free_name_migration``."""

from __future__ import annotations

import json
from typing import Any

import pytest

from coffer.domain.vault.document import encode
from coffer.domain.vault.writers import OP_UPDATE
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.vault.actor_meta import commit_meta
from coffer.infrastructure.vault.free_name_migration import SUMMARY, name_by_title, plan
from coffer.infrastructure.vault.home import local_root
from coffer.infrastructure.vault.instance import vault_repository, vault_writer

A, B, C = "a" * 32, "b" * 32, "c" * 32


def _doc(uid: str, kind: str, name: str, title: str | None = None) -> bytes:
    doc: dict[str, Any] = {"uid": uid, "kind": kind, "format_version": 1, "name": name}
    if title is not None:
        doc["title"] = title
    doc["config"] = {}
    return encode(doc)


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a title becomes the name on the first start"
)
def test_a_title_becomes_the_name_on_the_first_start_and_a_second_start_changes_nothing() -> None:
    # The second file is `acme2.json`, not the spec's `acme-b.json`: the plan
    # orders by path and "-" sorts before ".", so `acme-b.json` would be first.
    d = "resources/provider"
    files = {
        f"{d}/acme.json": _doc(A, "provider", "acme", "Acme EU"),
        f"{d}/acme2.json": _doc(B, "provider", "acme2", "acme eu"),
        f"{d}/plain.json": _doc(C, "provider", "plain"),
    }
    out = plan(files, d)
    names = {old: json.loads(data)["name"] for old, (_, data) in out.items()}
    assert names == {
        f"{d}/acme.json": "Acme EU",
        f"{d}/acme2.json": "acme eu (2)",
        f"{d}/plain.json": "plain",
    }
    assert {old: new for old, (new, _) in out.items()} == {
        f"{d}/acme.json": f"{d}/{A}.json",
        f"{d}/acme2.json": f"{d}/{B}.json",
        f"{d}/plain.json": f"{d}/{C}.json",
    }
    assert all("title" not in json.loads(data) for _, data in out.values())
    # A second start: the migrated files plan nothing.
    assert plan(dict(out.values()), d) == {}


def test_a_title_becomes_the_name_and_the_file_moves_to_its_uid() -> None:
    d = "resources/provider"
    files = {
        f"{d}/deepseek.json": _doc(A, "provider", "deepseek", "DeepSeek 官方"),
        f"{d}/openai.json": _doc(B, "provider", "openai", "  "),
    }
    out = plan(files, d)
    assert {old: new for old, (new, _) in out.items()} == {
        f"{d}/deepseek.json": f"{d}/{A}.json",
        f"{d}/openai.json": f"{d}/{B}.json",
    }
    first = json.loads(out[f"{d}/deepseek.json"][1])
    assert first["name"] == "DeepSeek 官方" and "title" not in first
    # A blank title keeps the name.
    assert json.loads(out[f"{d}/openai.json"][1])["name"] == "openai"


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a kept name wins over a title that would take it"
)
def test_a_title_that_takes_a_kept_name_ignoring_case_is_numbered() -> None:
    d = "resources/channel"
    files = {
        f"{d}/{A}.json": _doc(A, "channel", "Work"),
        f"{d}/bot.json": _doc(B, "channel", "bot", "work"),
        f"{d}/bot2.json": _doc(C, "channel", "bot2", "WORK"),
    }
    out = plan(files, d)
    assert f"{d}/{A}.json" not in out  # already in the new shape
    assert json.loads(out[f"{d}/bot.json"][1])["name"] == "work (2)"
    assert json.loads(out[f"{d}/bot2.json"][1])["name"] == "WORK (3)"


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a kept name wins over a title that would take it"
)
def test_a_provider_with_no_title_keeps_its_name_against_a_title_that_would_take_it() -> None:
    d = "resources/provider"
    files = {
        f"{d}/{A}.json": _doc(A, "provider", "Work"),
        f"{d}/work-2.json": _doc(B, "provider", "work-2", "work"),
    }
    out = plan(files, d)
    assert f"{d}/{A}.json" not in out  # "Work" is kept
    assert json.loads(out[f"{d}/work-2.json"][1])["name"] == "work (2)"


def test_the_plan_is_the_same_on_every_machine_and_empty_once_applied() -> None:
    d = "resources/provider"
    files = {f"{d}/x.json": _doc(A, "provider", "x", "X")}
    assert plan(files, d) == plan(dict(files), d)
    [(new, data)] = plan(files, d).values()
    assert plan({new: data}, d) == {}


async def test_the_vault_and_local_files_are_rewritten_in_one_pass() -> None:
    with vault_writer().begin(commit_meta(OP_UPDATE, "seed", "system")) as txn:
        txn.write(
            "resources/provider/kimi.json", _doc(A, "provider", "kimi", "Kimi"), Expect.ABSENT
        )
    channels = local_root() / "resources/channel"
    channels.mkdir(parents=True, exist_ok=True)
    (channels / "team-bot.json").write_bytes(_doc(B, "channel", "team-bot", "Team bot!"))

    assert name_by_title() == 2

    repo = vault_repository()
    assert list(repo.tree("HEAD", "resources/provider")) == [f"resources/provider/{A}.json"]
    assert repo.log(limit=1)[0].meta.summary == SUMMARY
    assert [f.name for f in channels.glob("*.json")] == [f"{B}.json"]
    assert json.loads((channels / f"{B}.json").read_text())["name"] == "Team bot!"
    # Nothing left to do on the next start.
    assert name_by_title() == 0
