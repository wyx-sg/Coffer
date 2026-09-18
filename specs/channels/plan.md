# Implementation Plan: Channels

## Summary

A `channel` resource kind connects IM accounts (Telegram, SeaTalk)
to the turn platform (spec `chat`). The channel core (pairing, routing, commands,
queueing, rendering policy, notify) is kind-agnostic over
an adapter protocol; Telegram and SeaTalk are its two adapters.
A separate callback-listener process gives SeaTalk its webhook ingress, per
the constitution's public-surface rule. The frontend carries a Channels page in
the Agents nav group.

The two platforms this kind varies by have their own child specs
([`channels/telegram`](./telegram/spec.md), [`channels/seatalk`](./seatalk/spec.md)),
each of which carries a `spec.md` only: their implementation lands in the file
families named below, so there is one plan and not three.

SeaTalk has a second inbound transport (spec channels/seatalk FR-002): a channel on
`delivery: "websocket"` holds one outbound connection instead, so it needs
neither the listener nor a tunnel nor a signature. It is supervised inside the
daemon — a per-channel connector reconciled the way the managed tunnel is — over
the platform's own client library, which the operator supplies in
`~/.coffer/vendor` and which this repository never vendors or declares
(spec channels/seatalk FR-007,
[SeaTalk Inbound Over WebSocket](../../docs/decisions/seatalk-websocket-inbound.md)).
Both transports meet at the same ingest entry point, so nothing downstream of
ingress is aware of the difference.

## Technical Context

- **Drives the platform in-process** — `ChatService.create_conversation`,
  `TurnOrchestrator.enqueue_message` (its `on_start` hook hands the channel
  the turn's event queue, drained to the `None` sentinel), `interrupt_turn`. No HTTP between channel
  core and turn platform.
- **No new SDKs.** Telegram and SeaTalk are spoken with `httpx` against fixed
  hosts (`api.telegram.org`, `openapi.seatalk.io`). No user-controlled URLs
  exist in channel config, so the SSRF guard (used for provider-URL checks) is not in this
  path.
- **Adapter runtime** — a reconciler task in the daemon (RetentionWorker
  pattern): every ~2 s it asks `application/channel/wanted.py` which channels
  are this machine's to run and diffs that answer against the running adapter
  tasks, starting, stopping and restarting on enable, disable, config change and
  delete. The answer is **three gates**, not one — `enabled`, then the machine
  binding (`runs_on` names this machine, FR-026), then scope (the channel may
  drive its own `default_agent`, FR-025) — and they are asked in that order so a
  channel that belongs to another machine is never weighed against this one's
  agent registry. The gate also carries the two things a reader needs out of it:
  each live channel's scope rewritten into agent keys, and a memory of which
  bindings it has already reported, so "bound elsewhere" is logged once instead
  of every tick. No new lifecycle hooks in the resource framework.
- **Credential materialization** — `CredentialResolver` lives in shared
  `application/credentials/resolver.py` rather than under `application/mcp/`,
  because channel is its second consumer (the constitution's extraction rule).

## Constitution Check

- **Local-first** — all state in SQLite/credential store; outbound calls are
  to the IM platforms the user explicitly registered. ✓
- **Public-reachable surfaces as separate process, signed paths only** — the
  SeaTalk listener is its own process, serves only
  `POST /seatalk/{channel_uid}` + signature verification, binds 127.0.0.1, and the
  public URL is provided by a tunnel — one the owner runs, or a `cloudflared`
  child the daemon supervises from a connector token on the channel. The daemon
  itself stays loopback-only. A channel on websocket delivery has no reachable
  surface at all (the socket is outbound), so the rule is satisfied without a
  process. ✓
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
│   ├── envelopes.py     # InboundMessage/Callback/Lifecycle/Stop, ChannelCapabilities
│   ├── commands.py      # COMMAND_ROSTER — the one list the menu, the help
│   │                    #   text and the FR-048 privacy flag all render from
│   ├── dedup.py         # seen-event ids (FR-039)
│   ├── rich_content.py  # markdown → the platform's own rich format (FR-045)
│   ├── media_retention.py # which media files are past the prune window
│   ├── signing.py       # seatalk_signature(body, secret) — pure hashlib
│   └── errors.py
├── application/
│   ├── credentials/resolver.py   # CredentialResolver (kind-agnostic, shared)
│   └── channel/         # the kind-agnostic core, ~30 modules, grouped:
│       ├── ports.py     # ChannelAdapter + LiveText protocols, AdapterCallbacks,
│       │                #   ChannelBinding, catalogue + context ports — the
│       │                #   TRANSPORT side
│       ├── store_ports.py # ChannelPeer + ChannelThreadConversation and their
│       │                #   repo ports — the two tables a channel owns
│       ├── kind.py      # make_channel_kind (ref extractor, on_delete, the
│       │                #   default_agent/scope invariant on both write paths)
│       ├── wanted.py    # the three gates deciding which channels run here
│       ├── runtime.py / runtime_supervision.py / supervision_ports.py
│       │                # the reconcile loop, and the listener / tunnel /
│       │                #   websocket connectors it keeps in step
│       ├── service.py   # ChannelService: pairing API, notify, status, ingest
│       ├── callback_ops.py # the SeaTalk callback path (keyed by channel uid),
│       │                #   the transport block it reports, and its self-test
│       ├── pairing.py / callback_probe.py
│       ├── inbound.py / inbound_events.py
│       │                # owner gate, dedup, command dispatch, session registry
│       ├── commands.py / agent_routing.py / model_switch.py / effort_switch.py
│       │                # the slash commands and the switches they perform
│       ├── selection_cards.py / card_delivery.py / ephemeral.py
│       │                # FR-015 cards, their in-place rewrite, FR-048 delivery
│       ├── conversation_ops.py / conversation_spec.py
│       ├── turn_driver.py / turn_render.py / turn_progress.py /
│       │   turn_text.py / turn_media.py
│       │                # one message → one turn → the reply, rendered live
│       ├── document_save.py / save_ports.py   # `/save` (FR-014, into spec
│       │                #   knowledge's own ingest path)
│       └── sync_state.py # pairing identity as a synced state area
├── infrastructure/channel/    # the transports, ~30 modules, grouped:
│   ├── persistence.py   # ChannelPeerModel, ChannelThreadConversationModel, repos
│   ├── render.py        # markdown → telegram HTML / seatalk markdown; chunking
│   ├── live_text.py     # the shared live-surface plumbing both transports use
│   ├── telegram*.py     # transport, poll loop, updates, album debounce, media,
│   │                    #   parse, send, cards, drafts, rich text, profile,
│   │                    #   capability probe
│   ├── seatalk*.py      # transport, token cache, send, cards, typing, media,
│   │                    #   history/thread fetch, parse, stream text, the
│   │                    #   websocket connector and its controller, SDK loader
│   ├── listener_spawn.py / tunnel_spawn.py
│   │                    # spawn/stop/health of the callback listener child and
│   │                    #   of the managed `cloudflared` child
│   └── media_retention.py # the media dir's 30-day prune (FR-033)
└── surfaces/
    ├── callback/        # the listener process (separate uvicorn app)
    │   ├── app.py       # POST /seatalk/{channel_uid}: challenge echo, verify,
    │   │                #   forward to daemon over loopback
    │   └── __main__.py  # python -m coffer.surfaces.callback
    ├── http/
    │   ├── channel_routes.py   # pairing-code, status, notify, callback-test,
    │   │                       #   events ingest
    │   ├── channel_wiring.py   # wire_channel_kind(): kind, service, runtime
    │   └── chat/               # the turn platform's own routes (spec chat),
    │                           #   which a channel turn drives in-process
    └── cli/channel_cmd.py      # list/register/bind/pair/status/notify
```

Key seams:

- `ChannelAdapter` protocol: `capabilities`, `start(callbacks)`, `stop()`,
  `send_text`, `open_live_text`, `edit_text`, `update_card`, `delete_message`,
  `send_typing`, `set_reaction`, `send_media`. Everything past `stop()` is
  optional and declared by `ChannelCapabilities` — `supports_live_text`,
  `supports_edit`, `supports_card_update`, `supports_buttons`,
  `supports_typing`, `supports_reactions`, `supports_media`, `supports_groups`,
  `supports_history_fetch`, plus `max_message_chars`. The core consults
  capabilities, never adapter type, and `supports_live_text` / `supports_edit`
  are deliberately independent (FR-038).
- `LiveText` protocol: the ONE surface a turn grows in place — opened once,
  offered every snapshot, closed carrying the final text. Each transport buffers
  updates to what it can sustain; the core adds no throttle of its own.
- `AdapterCallbacks` (given to adapters): `on_message(InboundMessage)`, plus
  three optional ones a transport supplies only where it has them —
  `on_callback` (a selection-card tap, FR-015), `on_lifecycle` (the bot's own
  standing in a chat, FR-042) and `on_stop` (the platform's own stop control,
  FR-047). Adapters never import turn-platform modules.
- The SeaTalk adapter has no poll loop. On webhook delivery the daemon's
  events-ingest route feeds the adapter through the runtime's registry; on
  websocket delivery a supervised connector feeds the same entry point from the
  SDK's listen thread.
- The listener child gets per-channel signing secrets, the daemon URL, and
  the daemon token via env at spawn; it keeps no other state. Source installs
  spawn `[sys.executable, -m, coffer.surfaces.callback]`; frozen builds
  locate a sibling `coffer-callback` binary (same probe pattern as
  `daemon_spawn_command`).
- `wanted.Routing` is the ONE place a channel's agent **uids** — its `scope` and
  its `default_agent` — become the turn platform's agent **keys**, and it runs
  one way: the gate projects them onto the live `ChannelBinding`, and nothing
  below the binding holds a uid to compare wrongly (FR-025). It replaced
  `agent_vocabulary.py`, a module that existed only to translate between the two
  names an agent used to answer to.
- The SeaTalk callback path is `/seatalk/<channel uid>`, composed once in
  `callback_ops.callback_path` and used by both the URL the owner registers and
  the probe that tests it. The listener's signing-secret map, the cloudflared
  tunnels and the SeaTalk websockets are all keyed by that same uid: two of the
  three have a seam the outside world can see, and a label the owner may rename
  is the wrong thing on either.

## Module layout — frontend

There is no `frontend/src/kinds/` directory. A kind's own React lives under
`components/<kind>/`, its routed pages under `pages/`, and its data access in
`lib/api/` + `lib/hooks/`.

```
frontend/src/
├── pages/ChannelsPage.tsx            # list + add entry point
├── pages/ChannelDetailPage.tsx       # status, pairing, enable/disable, delete
├── components/channel/               # AddChannelDialog + EditChannelDialog and
│                                     #   their secret fields, the channels
│                                     #   table and its row cells, the status
│                                     #   and callback cards, the delivery and
│                                     #   machine selects, the schema, the
│                                     #   health/binding helpers, agent labels
├── lib/api/channels.ts               # wire types over the generated schema
└── lib/hooks/useChannels.ts          # queries + mutations
```

Nav: `Channels` joins the `nav.group.agents` group (the slot
[Everything Is a Resource Kind](../../docs/decisions/everything-is-a-resource-kind.md)
reserved). Secrets flow through the existing keychain routes before resource
creation, with rollback on partial failure (AddMcpServerDialog pattern).
i18n: a `channels` namespace in `en.json`/`zh.json` (parity test enforces) —
the UI is bilingual even though the documentation is not.

## Tests

- **Unit**: config validation (refs, secret-looking rejection), pairing
  manager (TTL, attempts, replacement), markdown rendering + chunking,
  signature function, command parsing, capability-driven strategy selection.
- **Integration** (real SQLite, fake transports): a `FakeChannelAdapter`
  drives the full inbound pipeline against a scripted `AgentProvider`
  (register → pair → message → reply → /new → /stop → queue →
  notify); Telegram adapter against a local fake Bot API (ASGI
  httpx transport): polling, offset commit, HTML fallback, buttons; SeaTalk
  adapter against a fake openapi host: token refresh, send, cards, 429
  backoff; callback listener app: challenge echo, good/bad signature,
  forwarding; channel routes + CLI commands; runtime reconciler
  (enable/disable/delete/config-change).
- **Contract**: `/openapi.json` conformance for every channel route against
  `contracts/api.openapi.yaml`. The turn-platform routes a channel drives are
  spec chat's contract, not this one's.
- **Acceptance**: every scenario carries a marker naming the spec that holds
  it — `@pytest.mark.acceptance(spec="channels", ...)` for the parent's, and
  `spec="channels/telegram"` / `spec="channels/seatalk"` for a child's (or the
  frontend `acceptance(...)`); audited by `make verify-acceptance`.

The fake channel adapter used by the suite doubles as the proof of SC-003
(new channel = adapter + schema only); the scripted second provider proves
SC-004 (any agent reachable).

## Importlinter & enforcement

- The channel modules sit in every cross-kind `forbidden_modules` list
  symmetrically, under a "Cross-kind imports forbidden (channel)" contract that
  mirrors the other kinds'; the kind-agnostic core contract names them too.
- `application/credentials/` is kind-agnostic shared code (like
  `application/audit_service.py`); both mcp and channel may import it.
- `surfaces/callback` imports only domain/channel signing + httpx + fastapi;
  it never imports daemon internals.
- All files ≤ 400 lines; every route declares `response_model`; mypy strict.

## Risks & mitigations

- **Telegram/SeaTalk API drift** — transports are pinned behind adapters with
  fake-server integration tests; a platform change breaks one file.
- **Rate limits on the live surface** — each transport buffers its own
  updates to what it can sustain (SeaTalk ~100 ms, Telegram far slower since it
  edits a real message) and the core adds no throttle on top, which is what
  FR-038 requires. Every update, close and heartbeat is best-effort: a refused
  one leaves the final reply to carry the answer, and never fails the turn.
- **Listener port collisions** — port is env-configurable
  (`COFFER_CALLBACK_PORT`, default 8787) and surfaced in channel status so
  the tunnel target is always discoverable.
- **Daemon restart mid-pairing** — codes are memory-only by design; the
  status surface shows "no pending code", and re-issuing is one click.
