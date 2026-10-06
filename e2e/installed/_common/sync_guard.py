"""Refuse to write to a target whose vault is pushed to a sync remote.

Every ``qa-`` object a run creates and deletes is a vault change; on a target
that syncs, both would be committed and pushed to the person's remote. Before
any write the guard reads the target's own state — the ``sync`` feature from
``GET /api/v1/daemon/status`` and the remote from ``GET /api/v1/sync/remote`` —
and refuses when a remote is configured and enabled, unless the run was given
``--allow-sync-remote``. Anything it cannot read is a refusal too: it fails
closed.
"""

from __future__ import annotations

from typing import Any

from e2e.installed._common.http import DaemonClient
from e2e.installed._common.target import RefusedError


async def check_sync_guard(client: DaemonClient, allow: bool) -> dict[str, Any]:
    status = await client.request("GET", "/api/v1/daemon/status")
    if status.status != 200:
        raise RefusedError(f"sync guard: daemon status answered HTTP {status.status}")
    feature = (status.json.get("features") or {}).get("sync")
    remote = await client.request("GET", "/api/v1/sync/remote")
    decision: dict[str, Any] = {"sync_feature": feature, "remote_http_status": remote.status}
    code = (remote.json.get("error") or {}).get("code")
    if remote.status == 200:
        state = remote.json
        configured = bool(state.get("configured"))
        enabled = bool((state.get("remote") or {}).get("enabled"))
        decision.update(configured=configured, remote_enabled=enabled)
        syncing = configured and enabled and feature is not False
    elif remote.status == 404 and code == "FEATURE_DISABLED" and feature is False:
        # The sync feature is off: no round runs, so nothing this run writes is pushed.
        decision.update(configured=None, remote_enabled=None)
        syncing = False
    else:
        raise RefusedError(
            f"sync guard: cannot read the sync remote (HTTP {remote.status} {code}); "
            "refusing to write",
            decision,
        )
    decision["syncing"] = syncing
    decision["allowed_by_flag"] = bool(syncing and allow)
    if syncing and not allow:
        raise RefusedError(
            "sync guard: the target pushes its vault to a configured, enabled sync remote; "
            "every qa- object would be committed and pushed there. Pass --allow-sync-remote "
            "to run anyway.",
            decision,
        )
    return decision
