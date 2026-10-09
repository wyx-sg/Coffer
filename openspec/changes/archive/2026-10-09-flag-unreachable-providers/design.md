## Context

The provider detail page probed the open connection with
`POST /models/list-models` and classified the answer in the browser. Nothing
on the daemon knew a connection's health, so nothing else could show it.

## Decisions

**Where the verdict comes from.** The person chose (decision card in the
project thread, 2026-10-09) the combination of a periodic check and real
requests over either alone:

- the check is the same model listing the detail page makes, so it spends no
  token and needs no model id; it runs at boot and every 30 minutes over the
  enabled connections, and one second after a connection's resource is written
  (a key replaced clears its error without waiting for the sweep);
- the proxy's usage records already carry `connection_uid`, `status` and
  `outcome`; the ingest hands each file's records to the health service after
  their commit. 401/403 → key rejected, `connect_error` → unreachable, a
  completed 2xx → reachable; a 429, a 5xx or a cut stream says nothing about
  the connection and changes nothing.

A verdict older than the kept one is dropped, so a usage file ingested late
does not undo a fresh check. `since` keeps when the status was first seen, for
the Overview's "since".

**Storage.** A verdict can be made again, so it lives in `derived.db`
(ADR storage-is-five-classes-by-nature), one row per connection uid, beside
the MCP server health rows. A deleted connection's row is forgotten.

**Secrets.** A check uses the stored key only after `require_key` passes; a
connection whose key waits for approval is skipped (the secret source already
lists the approval).

**Which connections reach Overview.** Only those something runs on — an agent
whose `connection_uid` names it and that it still reaches, or the
speech-to-text default. A local runtime nobody uses may be stopped on purpose;
the provider list still marks it.

**Tests.** `COFFER_PROVIDER_HEALTH=off` leaves out the sweep and the re-check
after an edit (the test suite pins it, as it pins the price refresh); a check
someone asks for still runs.
