"""0093 — a channel's and an mcp_server's credential refs stop naming the resource.

Every assertion here is about a pair that has to move together. A credential's
ciphertext lives at ``credentials.ref`` and the only thing that can find it is a
resource config citing that same string, so a rewrite of one half without the
other is a secret the resource can no longer reach — and nothing reports it
until an unrelated delete runs ``release_orphaned_credentials`` over citations
that no longer line up.

The two-machine test is the one that would be easy to leave out and expensive to
miss: the synced bundle keys a secret's blob on the ref, so two vaults that
never talk have to derive the same new one or the next converge round pairs a
delete on one side with an add on the other over a file neither can read.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import uuid

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig

MIGRATIONS = pathlib.Path("backend/coffer/infrastructure/persistence/migrations")
NAMESPACE = uuid.UUID("e1917b6e-1ceb-42cf-9a60-d89ec9321ef7")


def _alembic_config() -> AlembicConfig:
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    return cfg


def expected_ref(kind: str, old_ref: str, tail: str) -> str:
    return f"{kind}/{uuid.uuid5(NAMESPACE, old_ref).hex}/{tail}"


def _insert_resource(conn: sqlite3.Connection, kind: str, name: str, config: dict) -> None:
    """A resource as it exists at 0092 — with the uid 0089 would have derived
    for it, so the row is the shape a real vault holds rather than one this
    revision happens not to read."""
    conn.execute(
        "INSERT INTO resources (uid, kind, name, config_json, enabled, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 1, '2026-01-01', '2026-01-01')",
        (
            uuid.uuid5(uuid.UUID("cd180388-8e6e-4bd0-a240-a8facba5ce53"), f"{kind}:{name}").hex,
            kind,
            name,
            json.dumps(config),
        ),
    )


def _insert_credential(conn: sqlite3.Connection, ref: str, value: bytes = b"cipher") -> None:
    conn.execute(
        "INSERT INTO credentials (ref, ciphertext, created_at, updated_at) "
        "VALUES (?, ?, '2026-01-01', '2026-01-01')",
        (ref, value),
    )


def _channel_config(bot_token_ref: str) -> dict:
    return {
        "channel_type": "telegram",
        "bot_token_ref": bot_token_ref,
        "default_agent": "claude-code",
        "runs_on": "machine-1",
    }


def _mcp_config(ref: str, key: str = "SMART_PAT") -> dict:
    return {
        "transport": {
            "type": "http",
            "url": "https://example.invalid/mcp",
            "headers": {},
            "credential_refs": {key: ref},
        }
    }


def _configs(db: pathlib.Path) -> dict[str, dict]:
    """``{name: parsed config}``, skipping rows whose JSON does not parse — one
    test deliberately plants such a row and reads it back raw."""
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT name, config_json FROM resources").fetchall()
    out: dict[str, dict] = {}
    for name, config in rows:
        try:
            out[name] = json.loads(config)
        except ValueError:
            continue
    return out


def _refs(db: pathlib.Path) -> set[str]:
    with sqlite3.connect(db) as conn:
        return {row[0] for row in conn.execute("SELECT ref FROM credentials")}


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "refs.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{path}")
    return path


def _seed(db: pathlib.Path, at: str = "0092") -> AlembicConfig:
    """A vault at ``at`` holding one channel and one mcp_server, each with a
    name-derived ref whose secret IS in the store."""
    cfg = _alembic_config()
    command.upgrade(cfg, at)
    with sqlite3.connect(db) as conn:
        _insert_resource(conn, "channel", "tg", _channel_config("channel/tg/bot-token"))
        _insert_resource(conn, "mcp_server", "smart", _mcp_config("smart.SMART_PAT"))
        _insert_credential(conn, "channel/tg/bot-token")
        _insert_credential(conn, "smart.SMART_PAT")
    return cfg


def test_rewrites_both_halves_in_lockstep(db):
    """The config and the credentials row move to the same new string.

    Asserted as a JOIN rather than as two independent equalities: what makes a
    ref correct is that the citation and the stored row agree, not that either
    one has a particular value.
    """
    cfg = _seed(db)
    command.upgrade(cfg, "0093")

    configs = _configs(db)
    cited = {
        configs["tg"]["bot_token_ref"],
        configs["smart"]["transport"]["credential_refs"]["SMART_PAT"],
    }
    assert cited == _refs(db)

    assert configs["tg"]["bot_token_ref"] == expected_ref(
        "channel", "channel/tg/bot-token", "bot-token"
    )
    assert configs["smart"]["transport"]["credential_refs"]["SMART_PAT"] == expected_ref(
        "mcp_server", "smart.SMART_PAT", "SMART_PAT"
    )
    # The rest of each config survived untouched — this revision rewrites refs,
    # not configs.
    assert configs["tg"]["default_agent"] == "claude-code"
    assert configs["smart"]["transport"]["url"] == "https://example.invalid/mcp"


def test_every_channel_secret_field_maps_to_its_own_logical_key(db):
    """``<field>_ref`` -> ``<field with dashes>``, for all four.

    The mapping is how a legacy channel ref is recognised at all, so a field
    this got wrong would simply be skipped — silently, leaving one secret on a
    name-derived address while its three siblings moved.
    """
    cfg = _alembic_config()
    command.upgrade(cfg, "0092")
    config = {
        "channel_type": "seatalk",
        "app_id": "app-1",
        "app_secret_ref": "channel/st/app-secret",
        "signing_secret_ref": "channel/st/signing-secret",
        "tunnel_token_ref": "channel/st/tunnel-token",
        "default_agent": "claude-code",
        "runs_on": "machine-1",
    }
    with sqlite3.connect(db) as conn:
        _insert_resource(conn, "channel", "st", config)
        _insert_resource(conn, "channel", "tg", _channel_config("channel/tg/bot-token"))
        for ref in ("app-secret", "signing-secret", "tunnel-token"):
            _insert_credential(conn, f"channel/st/{ref}")
        _insert_credential(conn, "channel/tg/bot-token")
    command.upgrade(cfg, "0093")

    st = _configs(db)["st"]
    assert st["app_secret_ref"] == expected_ref("channel", "channel/st/app-secret", "app-secret")
    assert st["signing_secret_ref"] == expected_ref(
        "channel", "channel/st/signing-secret", "signing-secret"
    )
    assert st["tunnel_token_ref"] == expected_ref(
        "channel", "channel/st/tunnel-token", "tunnel-token"
    )
    assert _configs(db)["tg"]["bot_token_ref"] == expected_ref(
        "channel", "channel/tg/bot-token", "bot-token"
    )
    # Every citation still names something the store holds.
    assert {st["app_secret_ref"], st["signing_secret_ref"], st["tunnel_token_ref"]} <= _refs(db)


def test_new_ref_carries_no_trace_of_the_resource_name(db):
    """The point of the whole revision: rename the resource, and nothing about
    the address it stored its secret at is now wrong."""
    cfg = _seed(db)
    command.upgrade(cfg, "0093")
    for ref in _refs(db):
        assert "tg" not in ref.split("/")[1]
        assert "smart" not in ref.split("/")[1]
        assert len(ref.split("/")[1]) == 32


def test_two_independent_databases_derive_the_same_ref(db, tmp_path, monkeypatch):
    """Two vaults, different row ids, no contact — one address per secret.

    The bundle stores ciphertext at ``credentials/<ref>.enc``. If these drifted,
    converging would look like one machine deleting a blob and another adding an
    unrelated one, over a file whose contents neither side can compare.
    """
    cfg = _seed(db)
    command.upgrade(cfg, "0093")
    first = _refs(db)

    other = tmp_path / "other.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{other}")
    cfg2 = _alembic_config()
    command.upgrade(cfg2, "0092")
    with sqlite3.connect(other) as conn:
        # Inserted in the OTHER order, so the row ids differ, and with the
        # SECRETS' values differing too — neither can influence the address.
        _insert_resource(conn, "mcp_server", "smart", _mcp_config("smart.SMART_PAT"))
        _insert_resource(conn, "channel", "tg", _channel_config("channel/tg/bot-token"))
        _insert_credential(conn, "smart.SMART_PAT", b"a different ciphertext")
        _insert_credential(conn, "channel/tg/bot-token", b"and another")
    command.upgrade(cfg2, "0093")

    assert first == _refs(other)
    with sqlite3.connect(db) as a, sqlite3.connect(other) as b:
        ids_a = dict(a.execute("SELECT name, id FROM resources"))
        ids_b = dict(b.execute("SELECT name, id FROM resources"))
    assert ids_a != ids_b


def test_second_run_is_a_no_op(db):
    """Idempotency, and specifically the ALREADY-OPAQUE branch: a re-run must
    not derive a second address from the first one."""
    cfg = _seed(db)
    command.upgrade(cfg, "0093")
    after_first = (_configs(db), _refs(db))

    command.downgrade(cfg, "0092")
    command.upgrade(cfg, "0093")
    assert (_configs(db), _refs(db)) == after_first


def test_a_citation_with_no_stored_secret_is_left_alone(db):
    """Both halves stay put when there is no half to move.

    An unstored ref is usually one still in the OS keychain, which
    ``credential_migration`` looks up by the CITED string — rewriting the
    citation would ask the keychain for an address it has never held.
    """
    cfg = _alembic_config()
    command.upgrade(cfg, "0092")
    with sqlite3.connect(db) as conn:
        _insert_resource(conn, "channel", "tg", _channel_config("channel/tg/bot-token"))
    command.upgrade(cfg, "0093")

    assert _configs(db)["tg"]["bot_token_ref"] == "channel/tg/bot-token"
    assert _refs(db) == set()


def test_a_credential_nothing_cites_is_untouched(db):
    """This revision walks citations; it never enumerates the store."""
    cfg = _alembic_config()
    command.upgrade(cfg, "0092")
    with sqlite3.connect(db) as conn:
        _insert_credential(conn, "channel/gone/bot-token")
    command.upgrade(cfg, "0093")

    assert _refs(db) == {"channel/gone/bot-token"}


def test_an_unparseable_config_is_skipped_whole(db):
    """A config that cannot be read cannot be rewritten correctly either, and a
    half rewrite is the exact failure this revision exists to prevent. Its
    neighbour still migrates."""
    cfg = _seed(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO resources (uid, kind, name, config_json, enabled, created_at, updated_at)"
            " VALUES ('deadbeef', 'channel', 'broken', 'not json{', 1, '2026-01-01', '2026-01-01')"
        )
    command.upgrade(cfg, "0093")

    with sqlite3.connect(db) as conn:
        raw = conn.execute("SELECT config_json FROM resources WHERE name = 'broken'").fetchone()[0]
    assert raw == "not json{"
    assert _configs(db)["tg"]["bot_token_ref"].startswith("channel/")
    assert len(_configs(db)["tg"]["bot_token_ref"]) > len("channel/tg/bot-token")


def test_a_minted_ref_a_second_config_also_cites_moves_for_both(db):
    """One secret, two citations: both end up on the new address.

    Only ``one`` minted this ref — it reconstructs from ``one``'s name and not
    from ``two``'s — so the move is planned once. Repointing only the minting
    half would leave ``two`` citing a string the store no longer holds, and the
    next delete of either would release a credential the other still needs.
    """
    cfg = _alembic_config()
    command.upgrade(cfg, "0092")
    with sqlite3.connect(db) as conn:
        _insert_resource(conn, "mcp_server", "one", _mcp_config("one.TOKEN", "TOKEN"))
        _insert_resource(conn, "mcp_server", "two", _mcp_config("one.TOKEN", "TOKEN"))
        _insert_credential(conn, "one.TOKEN")
    command.upgrade(cfg, "0093")

    configs = _configs(db)
    moved = expected_ref("mcp_server", "one.TOKEN", "TOKEN")
    assert configs["one"]["transport"]["credential_refs"]["TOKEN"] == moved
    assert configs["two"]["transport"]["credential_refs"]["TOKEN"] == moved
    assert _refs(db) == {moved}


def test_a_ref_the_user_chose_is_left_alone(db):
    """Only a ref that reconstructs WHOLE from the resource's name is moved.

    These are the ones a person picked and reads the vault by: the editable
    ``mcp/<agent>/<entry>/<KEY>`` default the adopt dialog prefills, a
    hand-typed one, and a legacy channel ref cited by a channel that is not the
    one it names. Nothing resolves a secret by matching a ref against a name, so
    moving these would cost the label and buy nothing.
    """
    cfg = _alembic_config()
    command.upgrade(cfg, "0092")
    left_alone = {
        "adopted": "mcp/claude-code/filesystem/FS_TOKEN",
        "typed": "my-github-token",
        # `channel/other/bot-token` is the legacy shape — but for a channel
        # called `tg` it is somebody else's address, not one `tg` minted.
        "borrowed": "channel/other/bot-token",
    }
    with sqlite3.connect(db) as conn:
        _insert_resource(conn, "mcp_server", "a", _mcp_config(left_alone["adopted"], "FS_TOKEN"))
        _insert_resource(conn, "mcp_server", "b", _mcp_config(left_alone["typed"], "GH"))
        _insert_resource(conn, "channel", "tg", _channel_config(left_alone["borrowed"]))
        for ref in left_alone.values():
            _insert_credential(conn, ref)
    command.upgrade(cfg, "0093")

    assert _refs(db) == set(left_alone.values())
    configs = _configs(db)
    assert configs["a"]["transport"]["credential_refs"]["FS_TOKEN"] == left_alone["adopted"]
    assert configs["b"]["transport"]["credential_refs"]["GH"] == left_alone["typed"]
    assert configs["tg"]["bot_token_ref"] == left_alone["borrowed"]


def test_downgrade_leaves_the_opaque_refs_in_place(db):
    """Documented as a no-op, and asserted as one: a guessed inverse would write
    an address derived from whatever the name is NOW."""
    cfg = _seed(db)
    command.upgrade(cfg, "0093")
    migrated = (_configs(db), _refs(db))
    command.downgrade(cfg, "0092")
    assert (_configs(db), _refs(db)) == migrated
