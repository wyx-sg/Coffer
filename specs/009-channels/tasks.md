# Tasks: 009 — Channels

Work breakdown. Order respects layering and TDD (tests land with the code
they pin).

## Phase 1 — Domain & shared

- [ ] T001 `domain/channel/config.py` — ChannelConfig union (telegram/seatalk),
      ref fields, secret-looking-value rejection + unit tests
- [ ] T002 `domain/channel/envelopes.py` — InboundMessage,
      OutboundText, ChannelCapabilities + unit tests
- [ ] T003 `domain/channel/signing.py` — seatalk signature + unit tests
- [ ] T004 hoist `CredentialResolver` → `application/credentials/resolver.py`;
      update mcp imports; keep tests green
- [ ] T005 `domain/audit.py` — add channel audit event types

## Phase 2 — Application core

- [ ] T006 `application/channel/ports.py` — ChannelAdapter protocol +
      AdapterCallbacks
- [ ] T007 `application/channel/pairing.py` — PairingManager + unit tests
      (TTL, attempts, replacement, claim)
- [ ] T008 `infrastructure/channel/persistence.py` — ChannelPeerModel + repo;
      migration `20260612_0015_channel_tables.py`; env.py import; integration
      tests
- [ ] T009 `application/channel/kind.py` — make_channel_kind (ref extractor,
      redactor, on_delete) + integration tests via ResourceService
- [ ] T010 `application/channel/inbound.py` — InboundProcessor: owner gate,
      pairing claim, commands (/new /stop /status /help), conversation
      mapping, queueing, turn driving, rendering dispatch +
      integration tests with FakeChannelAdapter + scripted AgentProvider
- [ ] T011 `application/channel/service.py` — ChannelService (issue code,
      status, notify, peer queries) + integration tests
- [ ] T012 `application/channel/runtime.py` — reconciler loop (start/stop on
      enabled/config change/delete) + listener lifecycle + integration tests

## Phase 3 — Transports

- [ ] T013 `infrastructure/channel/render.py` — markdown → telegram HTML,
      plain fallback, chunking + unit tests
- [ ] T014 `infrastructure/channel/telegram.py` — long poll loop, offset
      commit-after-dispatch, send/edit/delete, inline keyboard,
      answerCallbackQuery, setMyCommands, typing, backoff + integration tests
      against fake Bot API (ASGI transport)
- [ ] T015 `infrastructure/channel/seatalk.py` — token cache, single_chat
      send, interactive card, typing, 429 backoff, handle_event + integration
      tests against fake openapi host
- [ ] T016 `surfaces/callback/` — listener app (challenge echo, signature
      verify, forward) + `__main__` + integration tests
- [ ] T017 `infrastructure/channel/listener_spawn.py` — spawn/stop/health,
      env injection, pidfile + integration tests

## Phase 4 — Surfaces & wiring

- [ ] T018 `surfaces/http/channel_routes.py` — pairing-code, status, notify,
      events ingest + integration tests (auth, validation, errors)
- [ ] T019 `surfaces/http/channel_wiring.py` + lifespan hookup (after
      wire_chat) + shutdown ordering
- [ ] T020 `surfaces/cli/channel_cmd.py` — list/register/pair/status/notify +
      integration tests
- [ ] T021 contract test for the new routes vs contracts/api.openapi.yaml
- [ ] T022 importlinter: symmetric cross-kind updates + channel contract +
      C6 additions

## Phase 5 — Frontend

- [ ] T023 `lib/api/channels.ts` + `useChannels.ts`
- [ ] T024 ChannelsPage + AddChannelDialog (keychain write + rollback) + tests
- [ ] T025 ChannelDetailPage (status, pairing code, toggle, delete, callback
      info) + tests
- [ ] T026 nav entry (Agents group), router, i18n en/zh
- [ ] T027 frontend acceptance-tagged tests for UI scenarios

## Phase 6 — Docs & verify

- [ ] T028 acceptance markers complete; `make verify-acceptance` green
- [ ] T029 `.zh.md` companions for all spec docs
- [ ] T030 roadmap row, architecture.md kind table + layout, ADR-014 (+ zh)
- [ ] T031 `make verify` + frontend test/lint green; self-review; squash; PR
