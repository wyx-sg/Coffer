# Implementation Plan: 009 — Channels

> 中文版: [plan.zh.md](./plan.zh.md)

## Summary

Add a `channel` resource kind that connects IM accounts (Telegram, SeaTalk)
to the spec-008 chat platform. The channel core (pairing, routing, commands,
queueing, rendering policy, approval bridging, notify) is kind-agnostic over
a small adapter protocol; Telegram and SeaTalk are the first two adapters.
A separate callback-listener process gives SeaTalk its webhook ingress, per
the constitution's public-surface rule. The frontend gains a Channels page in
the Agents nav group.

## Technical Context

- **Drives the platform in-process** — `ChatService.create_conversation`,
  `TurnOrchestrator.start_turn` (drain the returned queue to the `None`
  sentinel), `submit_approval`, `interrupt_turn`. No HTTP between channel
  core and chat platform.
- **No new SDKs.** Telegram and SeaTalk are spoken with `httpx` against fixed
  hosts (`api.telegram.org`, `openapi.seatalk.io`). No user-controlled URLs
  exist in channel config, so the skill-fetcher SSRF guard is not in this
  path.
- **Adapter runtime** — a reconciler task in the daemon (RetentionWorker
  pattern): every ~2 s, diff enabled channel resources against running
  adapter tasks; start/stop/restart on enable, disable, config change,
  delete. No new lifecycle hooks in the resource framework.
- **Credential materialization** — `CredentialResolver` moves from
  `application/mcp/` to shared `application/credentials/resolver.py` (second
  consumer; the constitution's extraction rule). MCP imports update; behavior
  identical.

## Constitution Check

- **Local-first** — all state in SQLite/credential store; outbound calls are
  to the IM platforms the user explicitly registered. ✓
- **Public-reachable surfaces as separate process, signed paths only** — the
  SeaTalk listener is its own process, serves only
  `POST /seatalk/{channel}` + signature verification, binds 127.0.0.1, and
  the user's tunnel provides the public URL. The daemon itself stays
  loopback-only. ✓
- **Credentials** — bot token, app secret, signing secret live in the
  credential store; config carries refs; refs are probed at registration;
  secrets reach the listener child via env (the established MCP subprocess
  pattern) and are never persisted or logged. ✓
- **Layering** — domain stays pure (envelopes, config schemas, signature
  function are stdlib + pydantic); application defines the adapter protocol;
  infrastructure implements transports; surfaces wire. ✓

## Module layout — backend

```
backend/coffer/
├── domain/channel/
│   ├── config.py        # ChannelConfig discriminated union + ref validation
│   ├── envelopes.py     # InboundMessage, ApprovalClick, ChannelCapabilities
│   └── signing.py       # seatalk_signature(body, secret) — pure hashlib
├── application/
│   ├── credentials/resolver.py   # CredentialResolver (hoisted from mcp)
│   └── channel/
│       ├── ports.py     # ChannelAdapter protocol + AdapterCallbacks
│       ├── kind.py      # make_channel_kind (redactor, ref extractor, on_delete)
│       ├── pairing.py   # PairingManager (codes, TTL, attempt bounds)
│       ├── service.py   # ChannelService: pairing API, notify, status, peers
│       ├── inbound.py   # InboundProcessor: owner gate, commands, queueing,
│       │                #   conversation mapping, turn driving, approval bridge
│       └── runtime.py   # ChannelRuntime: reconciler loop + listener lifecycle
├── infrastructure/channel/
│   ├── persistence.py   # ChannelPeerModel + repo
│   ├── render.py        # markdown → telegram HTML / plain; chunking
│   ├── telegram.py      # TelegramAdapter: long poll, send/edit, buttons
│   ├── seatalk.py       # SeaTalkAdapter: token cache, send, cards, typing
│   └── listener_spawn.py# spawn/stop/health of the callback listener child
└── surfaces/
    ├── callback/        # the listener process (separate uvicorn app)
    │   ├── app.py       # POST /seatalk/{channel}: challenge echo, verify,
    │   │                #   forward to daemon over loopback
    │   └── __main__.py  # python -m coffer.surfaces.callback
    ├── http/
    │   ├── channel_routes.py   # pairing-code, status, notify, events ingest
    │   └── channel_wiring.py   # wire_channel_kind(): kind, service, runtime
    └── cli/channel_cmd.py      # list/register/pair/status/notify
```

Key seams:

- `ChannelAdapter` protocol: `capabilities`, `start(callbacks)`, `stop()`,
  `send_text`, `edit_text`, `delete_message`, `send_approval_prompt`,
  `resolve_approval_prompt`, `send_typing`. Optional surfaces are declared by
  `ChannelCapabilities`; the core consults capabilities, never adapter type.
- `AdapterCallbacks` (given to adapters): `on_message(InboundMessage)`,
  `on_approval_click(ApprovalClick)`. Adapters never import chat modules.
- The SeaTalk adapter has no poll loop; the daemon's events-ingest route
  feeds `handle_event` on the adapter via the runtime's registry.
- The listener child gets per-channel signing secrets, the daemon URL, and
  the daemon token via env at spawn; it keeps no other state. Source installs
  spawn `[sys.executable, -m, coffer.surfaces.callback]`; frozen builds
  locate a sibling `coffer-callback` binary (same probe pattern as
  `daemon_spawn_command`).

## Module layout — frontend

```
frontend/src/
├── pages/ChannelsPage.tsx            # list + add entry point
├── pages/ChannelDetailPage.tsx       # status, pairing, enable/disable, delete
├── kinds/channel/                    # AddChannelDialog, schema, cards
├── lib/api/channels.ts               # hand-written wire types (chat.ts pattern)
└── lib/hooks/useChannels.ts          # queries + mutations
```

Nav: `Channels` joins the `nav.group.agents` group (the slot ADR-007
reserved). Secrets flow through the existing keychain routes before resource
creation, with rollback on partial failure (AddMcpServerDialog pattern).
i18n: `channels` namespace in `en.json`/`zh.json` (parity test enforces).

## Tests

- **Unit**: config validation (refs, secret-looking rejection), pairing
  manager (TTL, attempts, replacement), markdown rendering + chunking,
  signature function, command parsing, capability-driven strategy selection.
- **Integration** (real SQLite, fake transports): a `FakeChannelAdapter`
  drives the full inbound pipeline against a scripted `AgentProvider`
  (register → pair → message → reply → /new → /stop → queue → approval
  allow/deny → notify); Telegram adapter against a local fake Bot API (ASGI
  httpx transport): polling, offset commit, HTML fallback, buttons; SeaTalk
  adapter against a fake openapi host: token refresh, send, cards, 429
  backoff; callback listener app: challenge echo, good/bad signature,
  forwarding; channel routes + CLI commands; runtime reconciler
  (enable/disable/delete/config-change).
- **Contract**: `/openapi.json` conformance for the new routes against
  `contracts/api.openapi.yaml`.
- **Acceptance**: every spec.md scenario carries a
  `@pytest.mark.acceptance(spec="009-channels", scenario=...)` (or frontend
  `acceptance(...)`) marker; audited by `make verify-acceptance`.

The fake channel adapter used by the suite doubles as the proof of SC-003
(new channel = adapter + schema only); the scripted second provider proves
SC-004 (any agent reachable).

## Importlinter & enforcement

- New modules join every cross-kind `forbidden_modules` list symmetrically;
  a new "Cross-kind imports forbidden (channel)" contract mirrors the
  existing five; the kind-agnostic core contract (C6) adds the channel
  modules.
- `application/credentials/` is kind-agnostic shared code (like
  `application/audit_service.py`); both mcp and channel may import it.
- `surfaces/callback` imports only domain/channel signing + httpx + fastapi;
  it never imports daemon internals.
- All files ≤ 400 lines; every route declares `response_model`; mypy strict.

## Risks & mitigations

- **Telegram/SeaTalk API drift** — transports are pinned behind adapters with
  fake-server integration tests; a platform change breaks one file.
- **Edit-rate limits on progress messages** — edits throttled ≥ 1.5 s and the
  progress message is best-effort: failures degrade to ack-then-final.
- **Listener port collisions** — port is env-configurable
  (`COFFER_CALLBACK_PORT`, default 8787) and surfaced in channel status so
  the tunnel target is always discoverable.
- **Daemon restart mid-pairing** — codes are memory-only by design; the
  status surface shows "no pending code", and re-issuing is one click.
