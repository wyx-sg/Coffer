"""Which kinds converge with the sync remote, read off the real registry.

``Kind.converges`` is the whole of the rule (see `application/sync/exporter.py`)
and `test_bundle_roundtrip.py` proves the exporter and the applier honour it —
but it proves that against the sync harness's own kinds, which this repository
defines for the test. A flag can be honoured perfectly and still be wired onto
nothing.

So this boots the real composition root and asks the registry it built. It is
an exact-set assertion in both directions on purpose: a kind that quietly opts
out of convergence stops a second machine ever seeing it, which is not the kind
of decision that should be possible to make without a reviewer noticing.
"""

from __future__ import annotations

import pathlib

import pytest

_NON_CONVERGING = {"memory"}


@pytest.fixture
def kinds(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59810")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59819")
    from starlette.testclient import TestClient

    from coffer.surfaces.http.app import create_app
    from coffer.surfaces.http.auth import set_active_token

    app = create_app()
    set_active_token("test-token-kind-convergence")
    # Most kinds are registered by the per-kind wiring modules during startup,
    # not by `create_app` itself, so the registry is only complete once the
    # lifespan has run — which is what entering the client does.
    with TestClient(app):
        registered = dict(app.state.kinds)
        # The exporter asks the ResourceService, not this dict, so the answer
        # has to survive the hop: the service is handed `app.state.kinds` by
        # reference and the per-kind wiring registers into that same object
        # after the service exists. A copy anywhere in that chain would make
        # every late-registered kind answer "does not converge" — which the
        # exporter would honour by publishing nothing at all.
        from coffer.surfaces.http.dependencies import get_resource_service

        service = get_resource_service()
        assert service.converges("memory") is False
        assert service.converges("mcp_server") is True
    set_active_token(None)
    return registered


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a kind that declares itself derived never reaches the tree",
)
def test_memory_is_the_one_kind_whose_rows_do_not_converge(kinds) -> None:  # type: ignore[no-untyped-def]
    """spec memory FR-016, asserted where the kinds are actually built.

    A partition row is derived from the agents installed on THIS machine. Sent
    to a second one it becomes a partition naming a project root that machine
    may not have, holding no facts — because the derived tree under
    ``~/.coffer/memory/`` is not mirrored either — until the next local pass
    recomputes it away. memory FR-016 forbids exactly that.
    """
    withheld = {name for name, kind in kinds.items() if not kind.converges}
    assert withheld == _NON_CONVERGING, (
        f"kinds that do not converge drifted: "
        f"newly-withheld={sorted(withheld - _NON_CONVERGING)}, "
        f"now-converging={sorted(_NON_CONVERGING - withheld)}"
    )


def test_every_kind_the_daemon_registers_answers_the_question(kinds) -> None:  # type: ignore[no-untyped-def]
    """The flag is on ``Kind``, so it cannot be absent — but a kind missing
    from this registry entirely would make the assertion above vacuously true,
    and the sync layer would then publish rows nobody had decided about."""
    assert kinds, "the composition root registered no kinds at all"
    assert set(kinds) >= _NON_CONVERGING, (
        f"{sorted(_NON_CONVERGING - set(kinds))} is named above but is not a registered kind"
    )
