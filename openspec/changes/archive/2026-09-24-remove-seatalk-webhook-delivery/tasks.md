The four groups own disjoint file sets and can run in parallel. Group 2's codegen
reads the contract, which is already updated in this change. Update every code
comment that cites a removed requirement title (`scripts/check_spec_citations.py`
lists them as notes) in the group that owns the file.

## 1. Backend (`backend/coffer/**`, `backend/tests/**`, `backend/pyproject.toml`)

- [x] 1.1 Delete `backend/coffer/surfaces/callback/` (package, `__main__`, `app.py`) and remove `coffer.surfaces.callback` from every import-linter contract in `backend/pyproject.toml`, plus any console-script or package-data entry for it
- [x] 1.2 Delete `infrastructure/channel/listener_spawn.py`, `infrastructure/channel/tunnel_spawn.py`, `domain/channel/signing.py`, `application/channel/callback_probe.py`; remove the listener and tunnel ports from `application/channel/supervision_ports.py` and their reconcilers from `application/channel/runtime_supervision.py`
- [x] 1.3 `application/channel/runtime.py`: drop `listener`, `tunnel`, `service_hold`, `listener_port`, `listener_running`, `tunnel_running`, the two latches and their reconcile steps; websocket reconciliation stays
- [x] 1.4 `surfaces/http/channel_wiring.py`: drop `CallbackListenerController`, `TunnelController`, `_daemon_info`, `_CHANNEL_HOLD` and `_hold_for_channel_listener` (the listener's idle hold goes with the listener; the idle stand-down itself is change `remove-daemon-idle-stand-down`'s), and the service's callback-probe `http_client` if nothing else uses it
- [x] 1.5 `domain/channel/config.py`: `SeaTalkChannelConfig` carries `app_id` and `app_secret_ref` only; delete `delivery`, `signing_secret_ref`, `public_base_url`, `tunnel_token_ref` and the delivery validator; update `credential_ref_extractor` in `application/channel/kind.py`
- [x] 1.6 Migration `backend/coffer/infrastructure/persistence/migrations/versions/20260924_0103_seatalk_channels_drop_webhook_fields.py`: strip `delivery`, `signing_secret_ref`, `public_base_url`, `tunnel_token_ref` from every `channel` row whose `config_json.channel_type` is `seatalk`, leaving credential rows untouched; downgrade writes `delivery: "websocket"`. Test it under `backend/tests/integration/infrastructure/persistence/` (upgrade strips the keys and leaves the credential rows; downgrade writes `websocket`; a telegram row is untouched)
- [x] 1.7 `application/channel/callback_ops.py` → status now builds an `inbound` block (`websocket_state`, `websocket_error`); rename the module if its name no longer fits; `application/channel/service.py`: remove the callback probe and keep `ingest_event`, which the websocket controller calls
- [x] 1.8 `surfaces/http/channel_routes.py`: delete `POST /api/v1/channels/{uid}/events` and `POST /api/v1/channels/{uid}/callback-test`, `CallbackTestOut`, `EventAcceptedOut`, `SeaTalkEventIn`; rename `CallbackInfoOut` → `InboundInfoOut` and `ChannelStatusOut.callback` → `inbound`, matching the contract
- [x] 1.9 `surfaces/cli/channel_cmd.py`: `coffer channel register` for seatalk takes app id and app secret only (drop delivery, signing-secret, public-URL and tunnel-token options); `coffer channel status` prints the websocket state and error and nothing about a listener, port, path, URL or tunnel; drop any `callback-test` command
- [x] 1.10 `application/log_reader.py`: drop the zerolog format and its three-character level tokens; `surfaces/http/daemon_schemas.py` and `infrastructure/daemon/child_process.py`: drop listener/tunnel mentions
- [x] 1.11 `application/binary_deploy.py`: ship three names (`coffer`, `coffer-daemon`, `coffer-mcp-shim`) and remove every `~/.coffer/bin/<name>` symlink into a version directory whose name the build does not ship, leaving anything else at such a path alone
- [x] 1.12 Delete the tests of deleted code: `tests/integration/surfaces/callback/test_listener_app.py`, `tests/integration/infrastructure/channel/test_listener_spawn.py`, `tests/integration/channel/test_tunnel_spawn.py`, `tests/integration/channel/test_runtime_tunnels.py`, `tests/integration/channel/test_callback_probe.py`, `tests/integration/channel/test_service_callback.py`; trim the webhook cases out of `tests/integration/channel/test_runtime.py`, `test_runtime_websockets.py`, `test_seatalk_acceptance.py`, `conftest.py`, `tests/unit/domain/channel/test_config.py`, `tests/unit/application/channel/test_kind.py`, `tests/unit/application/test_log_reader.py`, `tests/unit/application/test_diagnostics.py`, `tests/unit/infrastructure/daemon/test_reap_stale_daemons.py`, `tests/integration/surfaces/cli/test_channel_cmd.py`, `test_cli_parity.py`, `tests/integration/surfaces/http/channel/test_channel_routes.py`, `tests/integration/surfaces/http/test_daemon_log_routes.py`, `tests/contract/test_channel_contract.py`, `tests/contract/test_contract_coverage.py`, `tests/integration/sync/test_machines.py`
- [x] 1.13 Leave migration `0099` and its test as they are (history)

## 2. Frontend (`frontend/src/**`)

- [x] 2.1 Run frontend codegen against the updated `openspec/specs/channels/contracts/api.openapi.yaml`; `lib/api/generated/channels.ts` loses `testChannelCallback`, `ingestChannelEvent`, `CallbackTestOut`, `EventAcceptedOut`, `SeaTalkEventIn`, and `CallbackInfoOut` becomes `InboundInfoOut`
- [x] 2.2 `lib/api/channels.ts`: drop the callback-test call and hook; status type reads `inbound`
- [x] 2.3 Delete `components/channel/ChannelDeliveryField.tsx`; remove the delivery selector and the signing-secret, public-URL and tunnel-token fields from `AddChannelDialog.tsx`, `AddChannelSecretFields.tsx`, `addChannel.ts`, `EditChannelDialog.tsx`, `EditChannelSecretFields.tsx`, `editChannel.ts`, `schema.ts`
- [x] 2.4 Replace `components/channel/ChannelCallbackCard.tsx` with an inbound card showing the websocket state and last error (no port, path, URL, listener, tunnel or probe button); update `ChannelDetailCards.tsx`, `channelHealth.ts`, `pages/ChannelDetailPage.tsx`
- [x] 2.5 i18n: remove the webhook, tunnel, signing-secret, public-URL, delivery and probe strings from `i18n/locales/en.json` and `zh.json` (and `i18n/backend-keys.fixture.json` if it lists a removed backend key); add any new inbound-card strings in both
- [x] 2.6 Tests: delete `components/channel/seatalkDelivery.acceptance.test.ts` and `ChannelCallbackCard.test.tsx` (replace with a test of the inbound card); update `AddChannelDialog.test.tsx`, `EditChannelDialog.test.tsx`, `editChannel.test.ts`, `schema.test.ts`, `pages/ChannelDetailPage.test.tsx` (keeps its `channels` marker "channel status reports runtime, pairing, and callback details", asserting the inbound state)

## 3. Packaging (`backend/coffer-callback.spec`, `scripts/`, `Makefile`, `.github/`, `desktop/`)

- [x] 3.1 Delete `backend/coffer-callback.spec`
- [x] 3.2 `scripts/build_binaries.sh`, `Makefile` (freeze and install loops) and `.github/workflows/release.yml`: build, archive and checksum three binaries
- [x] 3.3 `desktop/tauri.conf.json` `externalBin`, `desktop/src/sidecar.rs` and `desktop/src/lib.rs`: three binaries; `make desktop-test` passes
- [x] 3.4 `scripts/check_pyinstaller_specs.py` passes with three spec files

## 4. Docs (`docs/**`, `docs-site/**`, `README.md`)

- [x] 4.1 `docs/principles.md` Technology constraint "Network defaults": delete the sentence about the one public-reachable surface running as a separate process limited to signed callback paths (principles amendment; the PR description records the owner's decision)
- [x] 4.2 `docs/architecture.md`: remove the callback listener and tunnel rows from the process table, the `surfaces/callback` package, and the webhook ingress flow; update the SeaTalk websocket row's citations; `scripts/check_architecture_doc.py` passes
- [x] 4.3 Amend `docs/decisions/seatalk-websocket-inbound.md` (webhook deleted; the "webhook apparatus stays" and "an install without the SDK is first-class" consequences superseded; related-requirement citations), `docs/decisions/channel-adapter-framework.md`, `docs/decisions/distribution-pyinstaller.md` (three binaries), and the listener mentions in `daemon-detect-or-spawn.md`, `daemon-serves-the-token-in-the-page.md`, `desktop-shell-over-a-shared-frontend.md`
- [x] 4.4 `README.md` and `docs-site/guide/channels.md` (SeaTalk setup is websocket-only: supply the SDK, set the portal to WebSocket, enable in Coffer, then Re-verify), `docs-site/guide/install.md`, `docs-site/guide/activity.md`, `docs-site/guide/sync.md`, and `docs-site/architecture/{distribution,layering,observability,overview,processes,request-lifecycle,security,surfaces}.md`

## 5. Specs, contracts, acceptance markers

- [x] 5.1 Deltas for channels/seatalk, channels, daemon, desktop-app, web-ui, vault-sync; Purpose edits for channels/seatalk, channels, daemon and web-ui
- [x] 5.2 `openspec/specs/channels/contracts/api.openapi.yaml`, `openspec/specs/channels/data-model.md`, `openspec/specs/daemon/data-model.md`
- [x] 5.3 New scenarios, each needing a test with its `acceptance(spec, scenario)` marker:
  - `channels/seatalk` "a webhook-era seatalk channel keeps only its app credentials" (the migration test of 1.6)
  - `channels/seatalk` "status names the websocket connection state" (REST and CLI; replaces the marker on "status reports webhook-only facts as absent rather than as defaults" in `test_channel_cmd.py`)
  - `daemon` "a deploy removes the link of a binary the build no longer ships" (`tests/unit/application/test_binary_deploy.py`)
- [x] 5.4 Removed scenarios whose markers must go (delete the test or drop the marker):
  - `channels/seatalk` "switching a channel to websocket delivery clears its webhook fields" — `frontend/src/components/channel/seatalkDelivery.acceptance.test.ts`
  - `channels/seatalk` "a webhook channel without a signing secret is refused" — `backend/tests/integration/channel/test_seatalk_acceptance.py`
  - `channels/seatalk` "a websocket channel runs without the listener or a tunnel" — `backend/tests/integration/channel/test_runtime.py`
  - `channels/seatalk` "status reports webhook-only facts as absent rather than as defaults" — `backend/tests/integration/surfaces/cli/test_channel_cmd.py`
  - `channels/seatalk` "the callback listener answers the verification handshake" — `backend/tests/integration/infrastructure/channel/test_listener_spawn.py`
  - `channels/seatalk` "a signed seatalk event reaches the channel", "a tampered seatalk event is rejected", "an oversized callback body is refused before it is read" — `backend/tests/integration/surfaces/callback/test_listener_app.py`
  - `channels/seatalk` "the listener runs only while a seatalk channel is enabled" — `backend/tests/integration/channel/test_runtime.py`
- [x] 5.5 Kept scenarios whose steps changed, so their tests must assert the new text: `channels/seatalk` "a websocket channel receives an event with no public url", "the websocket connection backs off when another process takes it over", "a websocket channel without the sdk says what is missing" (`test_seatalk_ws.py`); `channels/seatalk` "a seatalk channel without an app id or secret reference is refused" (`test_seatalk_acceptance.py`); `channels` "channel status reports runtime, pairing, and callback details" (`test_channel_routes.py`, `ChannelDetailPage.test.tsx`); `daemon` "release tag produces the CLI archive and SHA256SUMS" and `desktop-app` "a release tag produces the desktop tier" (`tests/integration/distribution/test_packaging_specs.py`: exactly three binaries); `daemon` "a frozen daemon deploys its sibling binaries on start" (`test_binary_deploy.py`); `web-ui` "the daemon tab reads every writer in the log" (`test_daemon_log_routes.py`: no zerolog line); `vault-sync` "a synced channel carries a credential reference, never a secret" (`tests/integration/sync/test_machines.py`)
- [x] 5.6 `.venv/bin/python scripts/check_spec_citations.py` reports no note for this change; `python scripts/audit_acceptance.py` passes

## 6. Close

- [ ] 6.1 Run `make verify`
- [ ] 6.2 Archive the change (`npx openspec archive remove-seatalk-webhook-delivery --yes`) in the same PR
