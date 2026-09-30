"""The ``coffer config`` key registry.

Every key is stored where its owning spec already stores the setting (spec
resource-framework "Change every setting through one key-value command"):

- ``daemon.port`` in the pre-bind settings file, read and written here with no
  daemon involved, because the state it most needs changing from is "the
  daemon cannot start" (spec daemon "Bind a fixed, settable port");
- ``engine.*`` and ``transcribe.model`` on the engine's settings row
  (``_config_engine``);
- ``engine.provider`` and ``transcribe.provider`` as the connection flags;
- ``credentials.storage`` through the daemon, the sole owner of the master key
  — this module imports no credential code (spec credentials "Route every credential
  command through the daemon");
- ``feature.<key>`` and ``retention.<table>``, whose members only the daemon
  knows, as families expanded on demand.
"""

from __future__ import annotations

from typing import Any

import typer

from coffer.infrastructure.daemon import bootstrap
from coffer.infrastructure.daemon import config as daemon_config
from coffer.surfaces.cli._approvals import WAITING
from coffer.surfaces.cli._config_engine import TRANSCRIBE_MODEL, engine_settings
from coffer.surfaces.cli._config_registry import (
    Family,
    Reading,
    Session,
    Setting,
    SettingValueError,
    choice,
    days_or_forever,
    switch,
    text,
)
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli._resolve import resolve_uid

# --- daemon.port -------------------------------------------------------------------


def _parse_port(raw: str) -> int:
    try:
        return daemon_config.validate_port(int(raw))
    except (ValueError, daemon_config.InvalidPort):
        raise SettingValueError(
            f"daemon.port takes a port number between {daemon_config.MIN_PORT} and "
            f"{daemon_config.MAX_PORT}, got {raw!r}"
        ) from None


def _port_read(_s: Session) -> Reading:
    configured = daemon_config.read_fixed_port()
    value = daemon_config.DEFAULT_PORT if configured is None else configured
    lines = [str(value)]
    if not daemon_config.config_is_readable():
        lines.append(
            f"the config file at {daemon_config.config_path()} exists but could not be read; "
            f"the default port {daemon_config.DEFAULT_PORT} is in effect"
        )
    return Reading(
        value, daemon_config.DEFAULT_PORT, lines=lines, extra={"configured_port": configured}
    )


def _port_apply(port: int | None) -> list[str]:
    """Write the file whatever the daemon is doing, then say whether a restart
    is owed — only when a live daemon is on a different port."""
    daemon_config.write_fixed_port(port)
    lines = [f"daemon.port = {daemon_config.effective_port()}"]
    info = bootstrap.live_daemon()
    if info is None:
        lines.append("daemon not running — the setting applies at the next start")
    elif daemon_config.effective_port() != info.port:
        lines.append(
            f"the daemon is still on port {info.port}; "
            "the change applies at the next start — run: coffer daemon restart"
        )
    return lines


DAEMON_PORT = Setting(
    "daemon.port",
    "port",
    "The port the daemon listens on (works with no daemon running)",
    "~/.coffer/daemon-config.json",
    _parse_port,
    _port_read,
    lambda _s, port: _port_apply(port),
    lambda _s: _port_apply(None),
)


# --- engine.provider / transcribe.provider ------------------------------------------


def _flag_key(key: str, flag: str, help_: str, said: str) -> Setting:
    route = f"/providers/{{uid}}/{flag.replace('_', '-')}"

    def read(s: Session) -> Reading:
        flagged = [p["name"] for p in s.get("/providers")["providers"] if p.get(flag)]
        value = flagged[0] if flagged else None
        lines = [value if value is not None else "no connection carries the flag"]
        return Reading(value, None, has_default=False, lines=lines)

    def write(s: Session, name: str) -> list[str]:
        uid = resolve_uid(s.client(), "provider", name, verbose=s.verbose)
        data = s.send("POST", route.format(uid=uid))
        return [f"{said} {data['name']} [{data['protocol']}]"]

    return Setting(
        key,
        "connection name",
        help_,
        f"POST {route}",
        text(key, "a connection name"),
        read,
        write,
        None,
        f"{key} has no default: the flag moves by naming another connection — "
        f"run: coffer config set {key} <name>",
    )


ENGINE_PROVIDER = _flag_key(
    "engine.provider",
    "internal_default",
    "The connection Coffer's own model runs on",
    "internal engine now uses",
)
TRANSCRIBE_PROVIDER = _flag_key(
    "transcribe.provider",
    "transcribe_default",
    "The connection Coffer transcribes speech on",
    "speech is now transcribed on",
)


# --- credentials.storage -----------------------------------------------------------------


def _storage_write(s: Session, where: str) -> list[str]:
    now = s.send("PUT", "/settings/credentials", {"master_key_storage": where})
    return [f"master key storage: {now['master_key_storage']}"]


CREDENTIALS_STORAGE = Setting(
    "credentials.storage",
    "file|keychain",
    "Where the credential master key is kept (moved and verified by the daemon)",
    "PUT /settings/credentials",
    choice("credentials.storage", ("file", "keychain")),
    lambda s: Reading(s.get("/settings/credentials")["master_key_storage"], "file"),
    _storage_write,
    lambda s: _storage_write(s, "file"),
)


# --- secrets.require_approval ------------------------------------------------------------


def _approval_write(s: Session, on: bool) -> list[str]:
    now = s.send("PUT", "/settings/secret-boundary", {"require_approval": on})
    if now.get("pending_approval_id"):
        # Switching it off widens where secrets may go, so it waits for the
        # desktop app like any new destination (spec credentials "Turn the
        # protection off only through the desktop app").
        typer.echo(
            f"{WAITING}: turn off approval for new secret destinations "
            f"(approval {now['pending_approval_id']})",
            err=True,
        )
        raise typer.Exit(int(ExitCode.APPROVAL_PENDING))
    return [f"secrets.require_approval: {'on' if now['require_approval'] else 'off'}"]


SECRETS_REQUIRE_APPROVAL = Setting(
    "secrets.require_approval",
    "on|off",
    "Hold a secret for approval in the Coffer app before it goes somewhere new",
    "PUT /settings/secret-boundary",
    switch("secrets.require_approval"),
    lambda s: Reading(
        "on" if s.get("/settings/secret-boundary")["require_approval"] else "off", "on"
    ),
    _approval_write,
    lambda s: _approval_write(s, True),
)


# --- prices.refresh ------------------------------------------------------------------
#
# The daily refresh of the model price list from genai-prices (spec
# provider-switching "Refresh the bundled price list in the background").


def _price_read(s: Session) -> Reading:
    doc = s.get("/providers/price-list")
    updated = doc.get("updated") or "unknown"
    note = f"prices from the {doc['origin']} list, updated {updated}"
    if doc.get("pinned_off"):
        note += "; COFFER_PRICE_REFRESH=off pins the refresh off"
    return Reading("on" if doc["refresh"] else "off", "on", note=note)


def _price_write(s: Session, value: bool) -> list[str]:
    doc = s.send("PUT", "/providers/price-list", {"refresh": value})
    return [f"prices.refresh: {'on' if doc['refresh'] else 'off'}"]


PRICES_REFRESH = Setting(
    "prices.refresh",
    "on|off",
    "Refresh the model price list from genai-prices once a day (off: use the bundled one)",
    "PUT /providers/price-list",
    switch("prices.refresh"),
    _price_read,
    _price_write,
    lambda s: _price_write(s, True),
)


# --- feature.<key> ------------------------------------------------------------------

_SOURCE_LABEL = {
    "pin": "pinned by COFFER_FEATURES",
    "setting": "set on this machine",
    "channel": "channel default",
}


def _feature_line(feature: dict[str, Any]) -> str:
    state = "on" if feature["enabled"] else "off"
    source = _SOURCE_LABEL.get(feature["source"], feature["source"])
    return f"feature.{feature['key']} = {state} ({source})"


def _feature(row: dict[str, Any]) -> Setting:
    key = row["key"]
    route = f"/daemon/features/{key}"

    def read(_s: Session) -> Reading:
        note = _SOURCE_LABEL.get(row["source"], row["source"])
        return Reading(row["enabled"], "channel", note=note, extra={"source": row["source"]})

    return Setting(
        f"feature.{key}",
        "on|off",
        f"Experimental feature '{key}' (unset: the channel default)",
        f"PUT {route}",
        switch(f"feature.{key}"),
        read,
        lambda s, on: [_feature_line(s.send("PUT", route, {"enabled": on}))],
        lambda s: [_feature_line(s.send("DELETE", route))],
    )


FEATURES = Family(
    "feature.", lambda s: [_feature(row) for row in s.get("/daemon/features")["features"]]
)


# --- retention.<table> --------------------------------------------------------------


def _days(value: int | None) -> int | str:
    return "forever" if value is None else value


def _retention(policy: dict[str, Any]) -> Setting:
    table = policy["table_name"]
    route = f"/retention/policies/{table}"

    def write(s: Session, days: int | None) -> list[str]:
        s.send("PATCH", route, {"retention_days": days})
        return [f"retention for {table}: {'forever' if days is None else f'{days}d'}"]

    return Setting(
        f"retention.{table}",
        "days|forever",
        f"How long {policy['display_name']} entries are kept",
        f"PATCH {route}",
        days_or_forever(f"retention.{table}"),
        lambda _s: Reading(
            _days(policy["retention_days"]), _days(policy["default_retention_days"])
        ),
        write,
        lambda s: write(s, policy["default_retention_days"]),
    )


RETENTION = Family(
    "retention.",
    lambda s: [_retention(p) for p in s.get("/retention/policies")["policies"]],
)


# --- the registry ------------------------------------------------------------------------


def static_settings() -> list[Setting]:
    return [
        DAEMON_PORT,
        ENGINE_PROVIDER,
        *engine_settings(),
        TRANSCRIBE_PROVIDER,
        TRANSCRIBE_MODEL,
        CREDENTIALS_STORAGE,
        SECRETS_REQUIRE_APPROVAL,
        PRICES_REFRESH,
    ]


FAMILIES: tuple[Family, ...] = (FEATURES, RETENTION)


def lookup(s: Session, key: str) -> Setting | None:
    """The key's setting, asking the daemon only for a family member."""
    for setting in static_settings():
        if setting.key == key:
            return setting
    for family in FAMILIES:
        if key.startswith(family.prefix):
            return next((m for m in family.members(s) if m.key == key), None)
    return None


def is_family(prefix: str) -> bool:
    """Whether ``prefix`` is exactly a family's prefix — one that may have no
    members at all (``feature.`` while no feature is experimental)."""
    return any(prefix == family.prefix for family in FAMILIES)


def listing(s: Session, prefix: str) -> list[Setting]:
    """Every key under ``prefix``; a family is expanded only when the prefix
    can reach it, so ``config list daemon.`` needs no daemon."""
    out = [st for st in static_settings() if st.key.startswith(prefix)]
    for family in FAMILIES:
        if prefix.startswith(family.prefix) or family.prefix.startswith(prefix):
            out += [m for m in family.members(s) if m.key.startswith(prefix)]
    return out
