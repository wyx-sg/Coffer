"""``engine.*`` and ``transcribe.model``: the keys stored on the engine's settings row.

All of them are thin shells over ``/api/v1/internal-engine-config``, so the
terminal and Settings → Coffer's model write the same row through the same
service and record the same audit entry (spec internal-engine "Keep every
engine setting under one key namespace"). The two connection flags,
``engine.provider`` and ``transcribe.provider``, live with the other
route-backed keys in ``_config_keys``.

``engine.curate_owner`` is the one key that reads two surfaces: the owner's
four states are only visible against the machine registry (spec vault-sync
"Report and change the rewriter's owner").
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from coffer.domain.internal_engine_config import CurationOwner, GlobalInternalEngineConfig
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli._config_registry import Reading, Session, Setting, switch, text, whole

_CONFIG = "/internal-engine-config"
#: The passes a key may name, in the order they run.
PASSES: tuple[str, ...] = ("aggregate", "distil", "curate")


def _config(s: Session) -> dict[str, Any]:
    body: dict[str, Any] = s.get(_CONFIG)
    return body


# --- engine.model / transcribe.model -----------------------------------------


def _model_key(key: str, field: str, route: str, help_: str, none_line: str, verb: str) -> Setting:
    def read(s: Session) -> Reading:
        value = _config(s)[field]
        return Reading(value, None, lines=[value if value is not None else none_line])

    def write(s: Session, value: str) -> list[str]:
        return [f"{verb}: {s.send('PUT', route, {'model': value})[field]}"]

    def unset(s: Session) -> list[str]:
        s.send("PUT", route, {"model": None})
        return [f"{verb} cleared — {none_line.split(' — ', 1)[-1]}"]

    return Setting(
        key, "model id", help_, f"PUT {route}", text(key, "a model id"), read, write, unset
    )


ENGINE_MODEL = _model_key(
    "engine.model",
    "model",
    _CONFIG,
    "The model Coffer's own passes run on (unset: every internal pass is a no-op)",
    "no engine model chosen — Coffer's own passes are a clean no-op",
    "internal engine model",
)
TRANSCRIBE_MODEL = _model_key(
    "transcribe.model",
    "transcribe_model",
    f"{_CONFIG}/transcribe-model",
    "The model Coffer transcribes speech with (unset: voice reaches the agent as a file)",
    "no transcription model chosen — voice reaches the agent as a file",
    "transcription model",
)


# --- engine.timeout ------------------------------------------------------------


def _timeout_read(s: Session) -> Reading:
    data = _config(s)
    chosen, default = data["model_timeout_s"], data["default_model_timeout_s"]
    line = f"default ({default}s)" if chosen is None else f"{chosen}s (default {default}s)"
    return Reading(chosen, default, lines=[line])


def _timeout_write(s: Session, seconds: int) -> list[str]:
    data = s.send("PUT", f"{_CONFIG}/timeout", {"seconds": seconds})
    return [f"model timeout: {data['model_timeout_s']}s"]


def _timeout_unset(s: Session) -> list[str]:
    data = s.send("PUT", f"{_CONFIG}/timeout", {"seconds": None})
    return [f"model timeout back to the default ({data['default_model_timeout_s']}s)"]


ENGINE_TIMEOUT = Setting(
    "engine.timeout",
    "seconds",
    "How long one call to Coffer's own model may take (the route refuses values out of range)",
    f"PUT {_CONFIG}/timeout",
    whole("engine.timeout", "a whole number of seconds"),
    _timeout_read,
    _timeout_write,
    _timeout_unset,
)


# --- engine.curate_owner ------------------------------------------------------------

_OWNER_LINE = {
    CurationOwner.UNOWNED: "curation owner: none — the pass runs wherever this vault is read",
    CurationOwner.SELF: "curation owner: {owner} (this machine)",
    CurationOwner.OTHER: "curation owner: {owner} (another machine)",
    CurationOwner.UNKNOWN: (
        "curation owner: {owner} — NO machine in this vault claims that id, "
        "so the pass runs nowhere at all"
    ),
}
_OWNER_REPAIR = "take it back with 'coffer config set engine.curate_owner this'"


def _machine_facts(s: Session) -> tuple[str, list[str]]:
    """This machine's id, and every machine id the registry holds."""
    this_machine = _cli_client.status_machine_id(s.get("/daemon/status")) or ""
    r = s.client().get("/sync/machines")
    _cli_client.check(r, verbose=s.verbose)
    ids = [str(m["machine_id"]) for m in (r.json().get("machines") or [])]
    # The list names this machine even before it ever converged; a registry of
    # this machine alone is no registry, and an owner id is then not a fault.
    return this_machine, [] if ids == [this_machine] else ids


def _owner_lines(owner: str | None, s: Session) -> tuple[CurationOwner, str, list[str]]:
    this_machine, known = _machine_facts(s)
    probe = GlobalInternalEngineConfig(
        model=None, updated_at=datetime.min, curate_owner_machine_id=owner
    )
    state = probe.curation_owner(this_machine, known)
    lines = [_OWNER_LINE[state].format(owner=owner)]
    if state is CurationOwner.UNKNOWN:
        lines.append(_OWNER_REPAIR)
    return state, this_machine, lines


def _owner_read(s: Session) -> Reading:
    owner = _config(s)["curate_owner_machine_id"]
    state, this_machine, lines = _owner_lines(owner, s)
    extra = {
        "curate_owner_machine_id": owner,
        "state": state.value,
        "this_machine_id": this_machine,
    }
    return Reading(owner, None, lines=lines, extra=extra)


def _owner_write(s: Session, value: str) -> list[str]:
    machine_id = (
        _cli_client.status_machine_id(s.get("/daemon/status")) if value == "this" else value
    )
    owner = s.send("PUT", f"{_CONFIG}/curation-owner", {"machine_id": machine_id})[
        "curate_owner_machine_id"
    ]
    return _owner_lines(owner, s)[2]


def _owner_unset(s: Session) -> list[str]:
    s.send("PUT", f"{_CONFIG}/curation-owner", {"machine_id": None})
    return [_OWNER_LINE[CurationOwner.UNOWNED]]


ENGINE_CURATE_OWNER = Setting(
    "engine.curate_owner",
    "this|machine id",
    "The one machine allowed to run the curation pass (unset: none named)",
    f"PUT {_CONFIG}/curation-owner",
    text("engine.curate_owner", "'this' or a machine id"),
    _owner_read,
    _owner_write,
    _owner_unset,
)


# --- engine.upkeep.<pass>.enabled|interval -------------------------------------


def _pass_line(name: str, setting: dict[str, Any]) -> str:
    chosen = f"{setting['interval_s']}s" if setting["interval_s"] is not None else "default"
    state = "on" if setting["enabled"] else "off"
    return f"{name}: {state}, every {chosen} (default {setting['default_interval_s']}s)"


def _upkeep_put(s: Session, name: str, payload: dict[str, Any]) -> list[str]:
    body = s.send("PUT", f"{_CONFIG}/upkeep", {"pass": name, **payload})
    return [_pass_line(name, body["upkeep"][name])]


def _upkeep_keys(name: str) -> list[Setting]:
    route = f"PUT {_CONFIG}/upkeep"

    def enabled_read(s: Session) -> Reading:
        return Reading(_config(s)["upkeep"][name]["enabled"], True)

    def interval_read(s: Session) -> Reading:
        row = _config(s)["upkeep"][name]
        return Reading(row["interval_s"], row["default_interval_s"])

    return [
        Setting(
            f"engine.upkeep.{name}.enabled",
            "on|off",
            f"Whether the {name} pass runs on its own",
            route,
            switch(f"engine.upkeep.{name}.enabled"),
            enabled_read,
            lambda s, v: _upkeep_put(s, name, {"enabled": v}),
            lambda s: _upkeep_put(s, name, {"enabled": True}),
        ),
        Setting(
            f"engine.upkeep.{name}.interval",
            "seconds",
            f"Seconds between {name} passes (the route refuses one below its floor)",
            route,
            whole(f"engine.upkeep.{name}.interval", "a whole number of seconds"),
            interval_read,
            lambda s, v: _upkeep_put(s, name, {"interval_s": v}),
            lambda s: _upkeep_put(s, name, {"use_default_interval": True}),
        ),
    ]


def engine_settings() -> list[Setting]:
    """Every ``engine.*`` key stored on the row, then ``transcribe.model``."""
    upkeep = [k for name in PASSES for k in _upkeep_keys(name)]
    return [ENGINE_MODEL, ENGINE_TIMEOUT, ENGINE_CURATE_OWNER, *upkeep]
