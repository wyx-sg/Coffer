"""Labels, minted ids, the move to minted ids, who used a secret and the citation
index, against a real in-process daemon over a throwaway HOME (spec secret)."""

from __future__ import annotations

import pathlib
import re
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.infrastructure.vault.home import derived_root
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http.secret_index_wiring import get_citation_index
from coffer.surfaces.http.secret_notes_wiring import get_secret_notes
from tests.support.boundary_daemon import (
    BoundaryDaemon,
    get_secret_store,
    point_cli_at,
    prepare_home,
    running_daemon,
)

VALUE = "-".join(["fake", "token", "value"])
OLD_VALUE = "-".join(["old", "fake", "value"])
MINTED = re.compile(r"^secret/[0-9a-f]{32}$")


@pytest.fixture
def d(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as daemon:
        yield daemon


def _add(d: BoundaryDaemon, label: str, value: str = VALUE) -> dict[str, Any]:
    r = d.client.post("/api/v1/secrets", json={"label": label, "value": value})
    assert r.status_code == 201, r.text
    return dict(r.json())


def _row(d: BoundaryDaemon, ref: str) -> dict[str, Any]:
    rows = d.client.get("/api/v1/secrets").json()["refs"]
    return next(r for r in rows if r["ref"] == ref)


def _mint_for_resource(d: BoundaryDaemon, value: str = VALUE) -> str:
    """A resource dialog's way: mint an id and store the value before the
    resource that will cite it exists."""
    ref = "secret/" + uuid.uuid4().hex
    assert d.client.post("/api/v1/secrets", json={"ref": ref, "value": value}).status_code == 204
    return ref


def _eventually(check: Callable[[], bool]) -> None:
    for _ in range(50):
        if check():
            return
        time.sleep(0.1)
    raise AssertionError("did not become true")


@pytest.mark.acceptance(
    spec="secret",
    scenario="a label and description change nothing that cites the secret",
)
def test_a_label_and_description_change_nothing_that_cites_the_secret(d: BoundaryDaemon) -> None:
    ref = _mint_for_resource(d)
    server = d.register_stdio("jira", "jira-mcp", {"JIRA_TOKEN": ref})
    files = d.client.get("/api/v1/secrets").json()["refs"]

    r = d.client.put(
        "/api/v1/secrets/notes",
        json={"ref": ref, "label": "Jira PAT", "description": "release bot's token"},
    )

    assert r.status_code == 200, r.text
    assert r.json() == {"ref": ref, "label": "Jira PAT", "description": "release bot's token"}
    row = _row(d, ref)
    assert (row["label"], row["description"]) == ("Jira PAT", "release bot's token")
    assert [c["slot"] for c in row["cited_by"]] == ["JIRA_TOKEN"]
    assert len(d.client.get("/api/v1/secrets").json()["refs"]) == len(files)
    got = d.client.get(f"/api/v1/resources/{server['uid']}").json()
    assert got["config"]["transport"]["secret_refs"] == {"JIRA_TOKEN": ref}
    assert d.resolve_for(server) == {"JIRA_TOKEN": VALUE} and d.pending() == []
    entry = d.audit("secret_notes_updated")[0]
    assert entry["details"] == {"ref": ref, "fields": ["label", "description"]}
    # One field left out stays; an empty one is removed; a long one is refused.
    keep = d.client.put("/api/v1/secrets/notes", json={"ref": ref, "description": ""})
    assert keep.json()["label"] == "Jira PAT" and keep.json()["description"] is None
    assert (
        d.client.put("/api/v1/secrets/notes", json={"ref": ref, "label": "x" * 65}).status_code
        == 422
    )
    assert (
        d.client.put("/api/v1/secrets/notes", json={"ref": "secret/" + "0" * 32}).status_code == 404
    )


@pytest.mark.acceptance(spec="secret", scenario="notes go with the secret")
def test_notes_go_with_the_secret(d: BoundaryDaemon) -> None:
    ref = _add(d, "Scratch")["ref"]
    d.client.put("/api/v1/secrets/notes", json={"ref": ref, "description": "temporary"})
    assert ref in get_secret_notes().all()

    assert d.client.delete(f"/api/v1/secrets/{ref}").status_code == 204

    assert ref not in get_secret_notes().all()


@pytest.mark.acceptance(
    spec="secret", scenario="a secret added on the page gets a minted id and its label"
)
def test_a_secret_added_on_the_page_gets_a_minted_id_and_its_label(d: BoundaryDaemon) -> None:
    minted = _add(d, "GitHub token")

    assert MINTED.match(minted["ref"])
    assert minted["uri"] == "coffer://" + minted["ref"]
    assert d.value(minted["ref"]) == VALUE
    assert _row(d, minted["ref"])["label"] == "GitHub token"
    assert VALUE not in str(d.audit_all())


@pytest.mark.acceptance(spec="secret", scenario="a person cannot choose an id")
def test_a_person_cannot_choose_an_id(d: BoundaryDaemon, monkeypatch: pytest.MonkeyPatch) -> None:
    refused = d.client.post("/api/v1/secrets", json={"ref": "secret/orders-db", "value": VALUE})
    assert refused.status_code == 422 and d.value("secret/orders-db") is None
    point_cli_at(d, monkeypatch)

    out = CliRunner().invoke(cli_app, ["secret", "set", "--name", "Orders DB"], input=VALUE + "\n")

    assert out.exit_code == 0, out.output
    uri = re.search(r"coffer://secret/([0-9a-f]{32})", out.output)
    assert uri is not None
    assert d.value("secret/" + uri.group(1)) == VALUE
    assert _row(d, "secret/" + uri.group(1))["label"] == "Orders DB"
    again = CliRunner().invoke(cli_app, ["secret", "set", "secret/orders-db"], input=VALUE + "\n")
    assert again.exit_code != 0 and d.value("secret/orders-db") is None


@pytest.mark.acceptance(
    spec="secret", scenario="start-up moves old names to fixed ids and keeps them readable"
)
def test_start_up_moves_old_names_to_fixed_ids(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = prepare_home(tmp_path, monkeypatch)
    hexref = "mcp_server/" + "ab" * 16 + "/JIRA_TOKEN"
    skill = tmp_path / ".coffer" / "vault" / "skills" / "deploy"
    with running_daemon(tmp_path, db) as old:
        for ref in ("secret/github", "postman.AUTHORIZATION", "team.TOKEN", hexref):
            get_secret_store().set(ref, OLD_VALUE + ref)
        skill.mkdir(parents=True)
        (skill / "run.sh").write_text("curl -H coffer://secret/github\n")
        postman = old.register_stdio("postman", "p", {"AUTHORIZATION": "postman.AUTHORIZATION"})
        one = old.register_stdio("one", "p", {"TOKEN": "team.TOKEN"})
        two = old.register_stdio("two", "p", {"TOKEN": "team.TOKEN"})
        jira = old.register_stdio("jira", "p", {"JIRA_TOKEN": hexref})
        for waiting in old.pending():
            old.approve(waiting["id"])

    def refs(d: BoundaryDaemon, resource: dict[str, Any]) -> dict[str, str]:
        got = d.client.get(f"/api/v1/resources/{resource['uid']}").json()
        return dict(got["config"]["transport"]["secret_refs"])

    with running_daemon(tmp_path, db) as d:
        listed = d.client.get("/api/v1/secrets").json()["refs"]
        assert all(MINTED.match(r["ref"]) for r in listed), [r["ref"] for r in listed]
        by_label = {r["label"]: r for r in listed if r["label"]}
        github = by_label["github"]
        assert d.value(github["ref"]) == OLD_VALUE + "secret/github"
        assert github["ref"].removeprefix("secret/") in (skill / "run.sh").read_text()
        assert "secret/github" not in (skill / "run.sh").read_text()
        for resource, key, old in (
            (postman, "AUTHORIZATION", "postman.AUTHORIZATION"),
            (jira, "JIRA_TOKEN", hexref),
        ):
            new = refs(d, resource)[key]
            assert MINTED.match(new) and d.value(new) == OLD_VALUE + old
        shared = {refs(d, one)["TOKEN"], refs(d, two)["TOKEN"]}
        assert len(shared) == 1 and MINTED.match(next(iter(shared)))
        # Several resources share it, so it was minted for none of them; one
        # resource's own is minted for that resource.
        row = {r["ref"]: r for r in listed}
        assert row[next(iter(shared))]["created_for"] is None
        assert row[refs(d, postman)["AUTHORIZATION"]]["created_for"] == postman["uid"]
        assert d.pending() == [] and len(d.audit("secret_migrated")) == 4
        assert d.value("postman.AUTHORIZATION") is None and d.value("secret/github") is None
        assert d.resolve_for(d.client.get(f"/api/v1/resources/{postman['uid']}").json())
        first = sorted(r["ref"] for r in listed)

    with running_daemon(tmp_path, db) as again:
        assert sorted(r["ref"] for r in again.client.get("/api/v1/secrets").json()["refs"]) == first
        assert len(again.audit("secret_migrated")) == 4


@pytest.mark.acceptance(
    spec="secret", scenario="a server start and a coffer run each show as a use"
)
def test_a_server_start_and_a_coffer_run_each_show_as_a_use(d: BoundaryDaemon) -> None:
    server_ref = _mint_for_resource(d)
    run_ref = _add(d, "Run")["ref"]
    server = d.register_stdio("svc", "svc-mcp", {"SVC_TOKEN": server_ref})

    d.resolve_for(server)
    r = d.client.post(
        "/api/v1/secrets/resolve",
        json={"names": [run_ref.removeprefix("secret/")], "argv0": "psql", "cwd": "/tmp/work"},
    )
    assert r.status_code == 200, r.text

    def seen() -> bool:
        return bool(d.client.get("/api/v1/secrets/uses", params={"ref": server_ref}).json())

    _eventually(seen)
    use = d.client.get("/api/v1/secrets/uses", params={"ref": server_ref}).json()[0]
    assert (use["destination_kind"], use["destination_name"], use["slot"]) == (
        "mcp_server",
        "svc",
        "SVC_TOKEN",
    )
    run = d.client.get("/api/v1/secrets/uses", params={"ref": run_ref}).json()[0]
    assert (run["destination_kind"], run["argv0"], run["cwd"]) == ("run", "psql", "/tmp/work")
    assert VALUE not in str(d.audit("secret_resolved"))


@pytest.mark.acceptance(spec="secret", scenario="a new citation shows without a rescan")
def test_a_new_citation_shows_without_a_rescan(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = prepare_home(tmp_path, monkeypatch)
    src = tmp_path / "src"
    src.mkdir()
    (src / "SKILL.md").write_text("---\nname: hello\ndescription: A skill.\n---\n\nbody\n")

    with running_daemon(tmp_path, db) as d:
        ref = _add(d, "Indexed")["ref"]
        d.register_stdio("citer", "c", {"TOKEN": ref})
        assert [c["name"] for c in _row(d, ref)["cited_by"]] == ["citer"]
        uid = d.client.post("/api/v1/skills/import", json={"path": str(src)}).json()["uid"]
        content = d.client.get(f"/api/v1/skills/{uid}/files/content", params={"path": "SKILL.md"})
        d.client.put(
            f"/api/v1/skills/{uid}/files/content",
            json={
                "path": "SKILL.md",
                "content": content.json()["content"] + f"\ncoffer://{ref}\n",
                "expected_fingerprint": content.json()["fingerprint"],
            },
        )
        _eventually(lambda: _row(d, ref)["mentioned_by_skills"] == ["hello"])
        answer = {k: _row(d, ref)[k] for k in ("cited_by", "mentioned_by_skills")}

    (derived_root(tmp_path) / "secret-citations.json").unlink()
    with running_daemon(tmp_path, db) as again:
        assert {k: _row(again, ref)[k] for k in ("cited_by", "mentioned_by_skills")} == answer


@pytest.mark.acceptance(
    spec="secret", scenario="deleting a resource releases the secrets nothing else cites"
)
def test_deleting_a_resource_releases_the_secrets_nothing_else_cites(d: BoundaryDaemon) -> None:
    own, shared, in_skill = (_mint_for_resource(d) for _ in range(3))
    page = _add(d, "Added on the page")["ref"]
    first = d.register_stdio(
        "first", "p", {"OWN": own, "SHARED": shared, "SKILL": in_skill, "PAGE": page}
    )
    d.register_stdio("second", "p", {"SHARED": shared})
    skill = d.home / ".coffer" / "vault" / "skills" / "uses-it"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"Cite coffer://{in_skill} here.\n")
    get_citation_index().skill_files_changed("uses-it")
    assert get_secret_notes().get(own).created_for == first["uid"]
    assert get_secret_notes().get(page).created_for is None
    assert {c["slot"] for c in _row(d, shared)["cited_by"]} == {"SHARED"}

    assert d.client.delete(f"/api/v1/resources/{first['uid']}").status_code == 204

    assert d.value(own) is None
    assert ref_exists(d, shared) and ref_exists(d, in_skill) and ref_exists(d, page)
    assert [e["details"]["ref"] for e in d.audit("secret_deleted")] == [own]


def ref_exists(d: BoundaryDaemon, ref: str) -> bool:
    return bool(d.client.get(f"/api/v1/secrets/{ref}/exists").json()["present"])


def test_a_label_can_be_sent_with_the_ref_a_dialog_minted(d: BoundaryDaemon) -> None:
    ref = "secret/" + uuid.uuid4().hex
    r = d.client.post(
        "/api/v1/secrets", json={"ref": ref, "label": "From a dialog", "value": VALUE}
    )
    assert r.status_code == 204
    assert _row(d, ref)["label"] == "From a dialog"


@pytest.mark.acceptance(
    spec="secret", scenario="a dialog's secret is the server's and a page's is not"
)
def test_a_dialog_secret_needs_no_approval_and_is_released_with_its_server(
    d: BoundaryDaemon,
) -> None:
    ref = _mint_for_resource(d)
    d.client.put("/api/v1/secrets/notes", json={"ref": ref, "label": "Dialog token"})
    assert get_secret_notes().get(ref).origin == "dialog"

    server = d.register_stdio("dialog-srv", "p", {"TOKEN": ref})

    assert d.pending() == [] and d.resolve_for(server) == {"TOKEN": VALUE}
    note = get_secret_notes().get(ref)
    assert (note.origin, note.created_for, note.label) == ("dialog", server["uid"], "Dialog token")
    assert d.client.delete(f"/api/v1/resources/{server['uid']}").status_code == 204
    assert d.value(ref) is None


def test_a_page_secret_cited_by_a_new_server_waits_for_a_person(d: BoundaryDaemon) -> None:
    ref = _add(d, "Page token")["ref"]
    assert get_secret_notes().get(ref).origin == "page"

    d.register_stdio("page-srv", "p", {"TOKEN": ref})

    assert [p["ref"] for p in d.pending()] == [ref]
    note = get_secret_notes().get(ref)
    assert note.created_for is None and note.origin == "page"
    d.client.put("/api/v1/secrets/notes", json={"ref": ref, "label": "Renamed"})
    assert get_secret_notes().get(ref).origin == "page"


def test_saving_label_and_description_at_once_keeps_both(d: BoundaryDaemon) -> None:
    """The page saves the name on blur and the description right after; two
    saves at once must not fail on the notes document having moved, nor drop
    one of them."""
    import threading

    refs = [_add(d, f"secret {i}")["ref"] for i in range(3)]
    errors: list[int] = []

    def save(ref: str, field: str, text: str) -> None:
        r = d.client.put("/api/v1/secrets/notes", json={"ref": ref, field: text})
        if r.status_code != 200:
            errors.append(r.status_code)

    threads = [
        threading.Thread(target=save, args=(ref, field, f"{field} of {ref[-4:]}"))
        for ref in refs
        for field in ("label", "description")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    rows = {r["ref"]: r for r in d.client.get("/api/v1/secrets").json()["refs"]}
    for ref in refs:
        assert rows[ref]["label"] == f"label of {ref[-4:]}"
        assert rows[ref]["description"] == f"description of {ref[-4:]}"
