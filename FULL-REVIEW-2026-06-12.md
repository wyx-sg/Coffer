# Coffer — Final Project Review Report

**Date:** 2026-06-12 · **Scope:** 16 dimensions, full repo (`main`-equivalent working tree) · **Reviewers' findings adversarially verified where marked**

---

## 1. Executive Summary

Coffer is in genuinely strong shape for a solo, spec-first project, and well within reach of its polished v0.4–v0.5 portfolio target. The disciplines the project claims are real, not aspirational: all 16 import-linter contracts pass over 386 files; the layering, ADRs, and code agree to an unusual degree; the backend test suite (1,199 integration / 618 unit / 123 contract tests) covers all 216 acceptance scenarios across nine specs with real SQLite, real subprocesses, and fakes only at genuine boundaries; the credential subsystem matches ADR-015 precisely; and the bilingual docs rule has been followed in the same commit for 64 of 70 doc pairs. The chat turn machinery, MCP transport hardening, and channel reconciler show careful async engineering that most teams never achieve. Security posture is above the bar for a local-first tool: loopback-bound with held sockets, token-gated routers, SSRF-guarded egress, allowlisted child environments, ciphertext-only secrets.

The defects that matter cluster in two places. First, the newest substrate has two **confirmed data-integrity bugs**: ingesting the same file into two knowledge bases silently corrupts the first KB's search index (chunk PK collision), and the memory write path still uses the legacy per-store embedding config, so with the standard global-embedding setup **no new fact ever gets a vector** — fresh memories are permanently invisible to vector recall. Second, the seams between processes and tiers are weaker than the cores: the desktop app spawns the daemon with the macOS GUI PATH (breaking `npx`/`uvx` upstreams — the flagship flow), deploys only the shim so post-reboot auto-spawn fails, and cannot recover from its own "Restart daemon" button because the UI keeps a revoked token. On the flagship chat surface, the user's just-sent message is invisible while the reply streams, and archived conversations cannot be opened at all. All seven confirmed bugs are fixable in days, not weeks.

The residual debt is mostly drift, and it is the kind the project's own constitution exists to prevent: the README describes a third of the product, spec 008 shipped with no Chinese companions and cites tools that don't exist, the only backup story predates the files-as-truth redesign (and there is no restore), the Python lock story is incoherent (a dead documented lockfile next to a live undocumented one), and the docs portal still sells Linux builds that CI stopped producing. None of this breaks the product; all of it undercuts the portfolio narrative, and nearly all of it is mechanical to fix.

**Overall: B+ — strong fundamentals, two real data bugs, seam-level polish needed for the portfolio bar.**

---

## 2. Scorecard

| Dimension | Grade | Verdict |
|---|---|---|
| Product design (specs 001–009) | B+ | Coherent nine-spec arc with explicit seams; debt is cross-spec contract drift (008 tool names, Draft headers) and a backup/restore story stale since ADR-012. |
| Architecture & ADRs | A- | Docs and code in unusually tight agreement, contracts enforced in CI; daemon spawn-race mitigation documented in ADR-006 does not exist in code. |
| Backend: agent/chat/channel | A- | Careful async engineering throughout; defects confined to edges (Telegram non-JSON responses, mid-turn unbind losing replies, blocking FS work on the loop). |
| Backend: knowledge/memory/MCP | B | Strong substrate discipline, but two **confirmed high bugs**: cross-KB index corruption and memory facts never embedded. |
| Backend: infra & surfaces | B+ | Auth, error envelope, path handling, secrets all sound; daemon lifecycle (stale daemon.json, unverified PID kill, SSE session disposal) is the weak corner. |
| Security | A- | Well-hardened for the threat model; webhook edge issues (empty signing secret, no replay protection, pairing griefing) on the one public-tunnel surface. |
| Frontend: core (API/state/stream) | B- | SSE client and abort discipline excellent, but two **confirmed high bugs** (restart token lockout, invisible sent message) plus a vestigial kinds registry and fragmented API layer. |
| Frontend: pages & components | B | Consistent scaffolds and real error routing; archived chat broken (**confirmed**), silent mutation failures, keyboard access gaps. |
| UX flows | B | Strong IA, first-run, and chat polish; archive flow broken, channels UI lags its backend (no edit, hardcoded agent binding), older kinds below the newer bar. |
| Tests: backend | A | Integration-heavy, all acceptance scenarios mapped, excellent negative-path coverage; only isolated weak assertions. |
| Tests: FE unit & e2e | B+ | Disciplined unit tests, zero skips, real-daemon web e2e; the newest features (channels, chat streaming, adopt) have no browser e2e. |
| Docs: accuracy vs code | B | Quickstarts remarkably faithful; README omits five shipped features, ADR-015 migration left inverted security claims, release runbook drifted. |
| Docs: bilingual rule | B | 64/70 pairs perfect with same-commit updates; spec 008 shipped with zero `.zh.md` companions. |
| Desktop & distribution | C+ | Solid Rust shell, honest release scoping; two **confirmed high bugs** at the app↔daemon seam, Linux docs advertise builds that 404, no update story, sqlite-vec likely missing from frozen builds. |
| Deps, build & CI | B | SHA-pinned actions, locked JS/Rust, real local/CI parity; Python side resolves latest-from-PyPI every run with two competing lockfiles, and one push runs verify three times. |
| Cross-stack consistency | B | One error envelope, exact i18n key parity, checked wire types; audit actor/event vocabularies fragmented and FE contract tier silently absent. |

---

## 3. Top Issues

### P0 — Must fix (all adversarially confirmed)

**P0-1. Cross-KB chunk-id collision corrupts the first KB's search index** — *critical (data loss)*
`backend/coffer/infrastructure/knowledge/sqlite_index.py:60`, migrations 0006/0010
KB doc ids are content-addressed (`sha256[:16]`), and `documents` has a composite PK to allow the same file in multiple KBs — but `chunks.id` is `"<doc-id>:<position>"` with a single-column PK, and `upsert_chunks`/`delete_chunks` filter by `document_id` only. Ingesting the same file into a second KB steals/re-tags the first KB's chunk+FTS rows; deleting the doc from either KB wipes the other's. Searches in the first KB silently return nothing until a manual reindex. This is an ordinary user action triggering invisible index corruption.
**Fix:** scope chunk identity and all chunk/FTS writes by `(kind, resource_name)`; add a two-KB same-file regression test. **Effort: M**

**P0-2. New memory facts never get vectors — write path uses the legacy per-store embedding config** — *high*
`backend/coffer/application/memory/writes.py:135`
`write_and_index` computes `embedding = config.to_embedding_config()` from fields the config itself documents as "accepted but ignored," while recall/admin/KB all use the global resolver. With the default setup (global embedding configured, per-store fields unset), every `remember` indexes keyword-only with the real content sha; the reconcile sha gate then prevents the fact from ever being embedded. Vector recall permanently misses fresh facts. Converse misconfiguration yields a vec-table width mismatch (zero KNN hits).
**Fix:** thread the global `EmbeddingResolver` into `WriteDeps`; delete `to_embedding_config()`; test: global embedding on → remember → assert vec row exists. **Effort: S**

**P0-3. Archived conversations cannot be opened — click lands on a blank new-chat draft** — *high*
`frontend/src/lib/hooks/useChatController.ts:50`
Archived rows navigate to `/chat/:id`, but `activeConv` is resolved only from the active (non-archived) list, so ChatPage falls through to `DraftThread`. Archived threads are unreadable without restoring (nothing says so), typing silently creates a new conversation, and stale deep-links get the same silent fallthrough.
**Fix:** resolve against both lists (or fetch by id via the existing `useConversation`), render archived threads read-only with a Restore CTA, and add a not-found state for unknown ids. **Effort: M**

**P0-4. User's just-sent message is invisible during streaming; turn_error leaves the thread desynced** — *high*
`frontend/src/lib/hooks/useChatTurn.ts:120`, `frontend/src/components/chat/MessageThread.tsx`
There is no optimistic user echo and `messagesKey` is invalidated only on stream success — so on every message after the first, the assistant visibly streams a reply to an invisible prompt; on `turn_error` the persisted user message and failed row stay hidden. The e2e tier explicitly skips live streaming, which is how this escaped.
**Fix:** optimistic user bubble (or invalidate messages on turn accept/turn_start), and invalidate messages in the catch path. **Effort: M**

**P0-5. Desktop "Restart daemon" leaves the UI on a revoked token with no in-app recovery** — *high*
`frontend/src/components/DaemonOfflineBanner.tsx:33`, `frontend/src/main.tsx`, `frontend/src/lib/api/client.ts`
`__COFFER_BASE_URL__`/`__COFFER_TOKEN__` are injected once pre-render and the client is memoized; the daemon regenerates the token on every start; the Tauri restart never reloads the webview or re-fetches daemon info. After a successful restart, every authenticated request 401s until the user quits the app — the recovery affordance breaks the app.
**Fix:** on restart success, re-invoke `get_daemon_info`, rewrite the window globals, call the (currently never-called) `resetApiClient()`, invalidate all queries — or reload the webview, mirroring the web path. **Effort: S**

**P0-6. Desktop-spawned daemon inherits the macOS GUI PATH — `npx`/`uvx` MCP upstreams fail** — *high*
`desktop/src/daemon.rs:222`, `backend/coffer/infrastructure/mcp/subprocess.py:100`
The .app spawns the daemon with no env adjustment (`PATH=/usr/bin:/bin:...`), and upstream stdio envs are built from the SDK allowlist of that environment; nothing anywhere augments PATH. The flagship flow — registering the exact `npx` server the install guide demonstrates — works from a terminal-started daemon and fails ENOENT from a desktop-started one.
**Fix:** capture a login-shell PATH before spawning (`$SHELL -lc 'echo $PATH'` / fix-path-env approach) or have the daemon augment PATH with well-known user bin dirs; add a bundled-app test that spawns an npx upstream. **Effort: M**

**P0-7. Only the shim is deployed to `~/.coffer/bin` — frozen auto-spawn can never find `coffer-daemon`** — *high*
`desktop/src/shim.rs:223`, `backend/coffer/infrastructure/daemon/spawn.py`
The frozen shim's detect-or-spawn probes a sibling `coffer-daemon` and PATH; for a desktop-only install neither exists (the daemon lives inside the .app bundle, autostart is opt-in). After a reboot, MCP clients spawning the shim exit with exactly the "daemon not running" failure `docs-site/guide/install.md` promises can never happen.
**Fix:** deploy `coffer-daemon` alongside the shim (same atomic-replace logic) or teach the shim a third probe for the installed .app path; e2e: kill daemon, run deployed shim standalone, assert ready. **Effort: M**

### P1 — Should fix

**P1-1. Daemon spawn race + unconditional `daemon.json` unlink (reported by 3 dimensions; ADR-006 claims a flock that doesn't exist)** — *medium, structural*
`backend/coffer/infrastructure/daemon/bootstrap.py:94`, `entry.py:36-56`, `surfaces/cli/daemon_cmd.py`
Check-then-act duplicate guard lets two near-simultaneous auto-spawns both bind; last `os.replace` wins, orphaning a daemon that runs migrations/retention/Telegram polling against the same DB forever. `release()` unlinks `daemon.json` without a pid check, so the orphan's exit deletes the live daemon's discovery file. Companion defects: `coffer daemon start` treats a stale file as "running"; `daemon stop` SIGTERMs an unverified PID; the Tauri side probes liveness with bare TCP (the exact false positive `bootstrap.live_daemon()` documents and avoids), so a port-squatter bricks both the fast path and the restart recovery.
**Fix:** flock around probe+bind+write (implement what ADR-006 already documents), pid-checked `release()`, `live_daemon()` in `daemon start`, cmdline-verified `daemon stop`, HTTP-status probe in `daemon.rs`. **Effort: M**

**P1-2. Backup is stale since ADR-012: only SQLite copied, no restore exists, files-as-truth and master.key excluded** — *high (design)*
`specs/001-mcp-gateway/spec.md:246`
The only specced backup copies `coffer.db` — the rebuildable *index* — while the system of record for KB/memory/skills is markdown trees under `~/.coffer/`, and the "safe to copy off-machine" claim ignores that credentials are unreadable without `master.key`. There is no restore operation anywhere. For a local-first vault, this is the missing safety net.
**Fix:** amend spec 001 (or a small dedicated spec): vault-level backup of db + knowledge/memory/skills trees, explicit master.key policy, a restore/verify operation. **Effort: M**

**P1-3. SeaTalk webhook accepts an empty signing secret — MAC collapses to `sha256(body)`** — *medium (security, public-tunnel surface)*
`backend/coffer/domain/channel/signing.py:19`, `surfaces/http/schemas.py:214`
`CredentialSetIn.value` has no `min_length`; an empty stored secret passes the listener's `is None` gate and verification proceeds with `secret=""` — any remote peer can forge events and present as the paired owner. Related hardening: no replay/nonce/timestamp protection on SeaTalk events; pairing attempt counter is per-channel, letting a stranger burn the owner's pending code.
**Fix:** reject empty secrets/signatures in `verify_seatalk_signature`, `min_length=1` on credential values, dedup/freshness-window SeaTalk events, per-sender pairing attempts. **Effort: S–M**

**P1-4. Spec 008 shipped with zero Chinese companions (5 docs, ~1,265 lines)** — *high (docs, rule violation)*
`specs/008-agent-chat/` — spec/plan/research/data-model/quickstart all lack `.zh.md`, never existed in any branch, and spec.md has no cross-link. Sole violation of an otherwise perfectly followed rule (64/70 pairs same-commit clean); directly breaks AGENTS.md §7 rule 3.
**Fix:** translate all five in one commit with bidirectional links. **Effort: L (mechanical)**

**P1-5. Installer and docs portal advertise Linux builds that 404** — *high (first-contact UX)*
`docs-site/public/install.sh:74`, `docs-site/guide/install.md`, `desktop.md`
`install.sh` has a Linux x86_64 leg and the guides list AppImage/deb rows, but release.yml builds macos-14/aarch64 only (per the honest 2026-06-05 ADR-008 revision). Any Linux user following the official guide hits a curl 404. Also: README's DMG filename omits the `-unsigned` suffix the workflow appends; the notarization runbook instructs flipping a workflow step that no longer exists and never wires `entitlements.plist` (PyInstaller sidecars would crash under hardened runtime).
**Fix:** friendly-reject Linux in install.sh, remove the rows (+ .zh pairs), fix filenames, rewrite runbook steps 3–4. **Effort: S**

**P1-6. PyInstaller spec doesn't bundle sqlite-vec's `vec0` extension — frozen builds silently lose vector retrieval** — *medium*
`backend/coffer-daemon.spec`, `infrastructure/knowledge/vec_index.py:81-96`
`sqlite_vec.load()` needs a loadable dylib shipped as package data; the spec collects alembic/mcp only, and `available()` swallows the failure, so shipped daemons degrade to no-vector while dev installs work. The release smoke test (status + one initialize) cannot see it. The hiddenimports list generally predates specs 006/007.
**Fix:** `collect_data_files("sqlite_vec")`, audit the KB/memory dep set in the frozen build, extend the smoke test with a vec-availability probe. **Effort: M**

**P1-7. Python lock story incoherent; CI/release resolve latest-from-PyPI every run** — *medium (reproducibility)*
`backend/requirements-dev.lock`, `backend/uv.lock`, `.github/workflows/*`
The documented lockfile is frozen at the day-one scaffold (50 packages, no sqlalchemy/mcp/langchain, pins below current floors) and `make lock`'s pointer to CONTRIBUTING.md goes nowhere; the real lock (`uv.lock`, current) is referenced by nothing. All CI and — worse — `release.yml` install from `>=` floors, so tagged artifacts are not reproducible and upstream releases can break or silently change builds.
**Fix:** pick one mechanism (uv recommended), install frozen in CI/release, keep a scheduled latest-deps canary, write the missing CONTRIBUTING section. **Effort: M**

**P1-8. Mixed async/sync SQLite access guarded only by docstring convention** — *medium (structural)*
`backend/coffer/infrastructure/credentials/encrypted_store.py`, `wiring.py:283`, `credential_routes.py:79`
Four independent paths open the same DB; a sync write on the event loop deadlocks against aiosqlite's write lock — the in-progress fix in `encrypted_store.py` proves the hazard is live, and reads (`store.get` in routes and the chat credential resolver) still run on the loop today.
**Fix:** async facade over the store that internally `to_thread`s every call (make the convention impossible to violate), or a lint guard. **Effort: M**

**P1-9. Newest features have no real e2e: channels (zero browser specs), chat streaming (composer-enabled only), adopt flow (never clicked)** — *medium (test gap)*
`e2e/web/specs/` — spec 009's FE acceptance markers are satisfied by fully-mocked jsdom tests; the SSE wire contract is pinned independently on each side but never proven to match; the adopt flow — site of the active deadlock fix — has no cross-process coverage. Wire drift on the flagship surfaces would pass every CI tier.
**Fix:** `shell_channels.spec.ts` mirroring `shell_agents`; a deterministic fake LLM provider so chat.spec sends a message and asserts streamed text; extend `agent_workspace.spec.ts` past rendering into Adopt. **Effort: M–L**

**P1-10. Channel edge cases lose owner-visible output; Telegram adapter crashes its own error contract** — *medium*
`backend/coffer/application/channel/inbound.py:120-133`, `infrastructure/channel/telegram.py:231`
A config edit/disable/shutdown mid-turn cancels the renderer but lets the turn complete undelivered (bot goes silent; reply exists only in the web UI); `/stop` after `/new` interrupts the wrong conversation while claiming "Stopping…"; `TelegramAdapter._call` does unguarded `response.json()`, so a 502 HTML page escapes `ChannelSendFailed` as a raw `JSONDecodeError` (SeaTalk `_post` has the same hole — `JSONDecodeError` is not an `httpx.HTTPError`).
**Fix:** interrupt the active turn in `unbind`; `/stop` falls back to the draining turn; wrap `response.json()` in both adapters. **Effort: S–M**

### P2 — Nice to have

| Item | Files | Note | Effort |
|---|---|---|---|
| Credential deletion has no in-use check across mcp_server/model/channel refs | `surfaces/http/credential_routes.py:108` | Cleanup silently breaks a channel/model; refs live in config JSON, the scan is cheap (409 + citing list) | S |
| kinds/ registry vestigial + dead component chain (KindResourcePage→ResourceListView→Cards, all tested) | `frontend/src/lib/components/kindRegistry.ts` | Channel kind skipped it; either commit (route KB/memory through it, register channel) or delete; extract the duplicated six-page list scaffold | M |
| Silent mutation failures + `window.confirm` + one-click model delete | `useChannels.ts`, `MemoryStoreDetailPage.tsx`, `useConversations.ts`, `ModelsPage.tsx:106` | Add the standard `onError → toast` (the doc says it's "not optional"); migrate 5 native confirms to ConfirmDialog; confirm model delete | S–M |
| i18n/vocab backfill: 42/66 error codes, 38/62 audit events untranslated; audit actor fragmented (`user`/`agent`/`channel` vs spec enum) | locales, `domain/audit.py`, `kinds/memory/api.ts:32` | zh users see raw English/snake_case on all post-001 surfaces; add parity tests diffing locales against backend maps | M |
| Gateway invoke evicts a healthy upstream on any `McpError` | `application/mcp/gateway_handlers.py:206` | Protocol-level JSON-RPC errors kill+respawn the server; mirror `_request_self_heal`'s classification | M |
| Detail trees capped at first 100 items while showing the true total | `MemoryStoreDetailPage.tsx:46`, `useKnowledgeBaseDetail.ts:51` | Memory grows automatically via MCP; load-more or "showing 100 of N" | M |
| enable/disable undefined for skill/KB/memory kinds (disabled KB still serves search) | `specs/006 FR-001`, `resource_service.set_enabled` | Spec per-kind disabled semantics + an `on_enable/on_disable` hook (or remove the toggle, as 004 did) | M |
| No desktop update story; daemon version hardcoded "0.1.0" so skew is undetectable | `daemon.rs:279`, `daemon_routes.py:125` | New app silently reuses the old detached daemon; version-compare on startup + manual-upgrade doc | M |
| One push runs verify three times, no concurrency cancellation | `.github/workflows/ci.yml:3` | Drop ci.yml's `pull_request:` trigger, add `concurrency:` groups, remove unused e2e npm install | S |
| Channels: no edit flow (token rotation = delete+re-pair), agent binding hardcoded, notify has no UI | `kinds/channel/schema.ts:12`, `lib/api/channels.ts:92` | An EditChannelDialog + a "Send test message" button would also be the natural live-verification path spec 009 still owes | M |
| SSE disconnect disposes the MCP session in ~5s, defeating the shim's own reconnect design | `surfaces/http/mcp/protocol_routes.py:300` | Release the stream only; let the idle reaper own disposal | M |
| README omits five shipped feature areas; architecture.md layout/wiring prose covers 3 of 6 kinds | `README.md:15`, `.specify/memory/architecture.md:63` | The portfolio front door understates more than half the product | S |

---

## 4. Quick Wins (~30 min each)

1. **Memory write embedding fix (P0-2)** — small diff, biggest value-per-line in the report.
2. **Restart-token fix (P0-5)** — wire `resetApiClient()` + re-fetch daemon info (or reload the webview).
3. Flip six spec Status headers Draft→Accepted; fix roadmap 003 "in review (PR #28)" → merged.
4. Fix the two "ADR-015" link labels in architecture.md that point at ADR-014 (+ .zh pair).
5. Correct spec 008 + its quickstart's phantom tool names to `coffer__recall` / `coffer__search_knowledge`; reconcile FR-016a/b with the out-of-scope bullet.
6. Reword the 004 quickstart's inverted "secrets go into the OS keychain, never the database" claim (+ CLI `--secret` help text).
7. `min_length=1` on `CredentialSetIn.value` + empty-secret/signature rejection in `verify_seatalk_signature` (the core of P1-3).
8. `coffer daemon start`: use `live_daemon()` instead of file presence; pid-check `bootstrap.release()`.
9. Guard `configure_logging`'s file handler against stacking; fix the `/mcp` JSON-array 500 → `-32600`.
10. Add `focus-visible:opacity-100 group-focus-within:opacity-100` to ConversationListItem's four hover-only action buttons; fix the double empty-state in archived view.
11. Reject Linux in `install.sh` with a friendly message; document the `-unsigned` DMG filename in README.
12. Delete the dead `asgi-lifespan` dep, the unused `engine` pytest marker (or wire it), and the `MasterStore.rename`/`skill_md_sha256` dead methods; fix `agents/sdd.md`'s wrong audit-script path and `stack.md`'s nonexistent `make test`.

---

## 5. Strategic Recommendations

1. **Ship a real backup/restore story before v0.4.** It is the single safety net a local-first vault owes its user, and the current spec backs up the rebuildable index while missing the truth (files) and the key. One small spec: vault-level backup (db + knowledge/memory/skills + explicit master.key policy) and a verified restore command. This is also the strongest possible portfolio talking point for "local-first done seriously."

2. **Make the daemon lifecycle boring.** The single largest cluster of findings (3 review dimensions + 2 confirmed desktop bugs) is the process seam: spawn races, stale discovery files, GUI PATH, shim-without-daemon, TCP false positives, version-blind reuse. Treat "exactly one discoverable, correct-PATH, version-known daemon" as one engineering unit — flock'd acquire, ownership-checked release, HTTP-status probes everywhere, login-shell PATH, daemon deployed beside the shim, version handshake on app start — and add one e2e that reboots the world (kill daemon → run deployed shim → assert ready).

3. **Turn doc-truth into a gate, not a habit.** The constitution says spec-as-truth, and the drift found (README, spec 008 zh, tool names, Linux docs, lockfile pointer, Status headers) is all post-hoc. Cheap mechanical gates close most of it: a CI diff of locale `errors.*`/`audit.activity.*` keys against the backend maps, a frontend contract tier (the Makefile hook already exists and silently skips), the acceptance-style audit extended to spec Status headers and `.zh.md` presence, and a README refresh as part of every spec's completion checklist.

4. **Decide the frontend extension-seam direction.** The kinds registry and the generated API client were both built as the scaling story, and both have been abandoned in practice (channel skipped the registry; six specs of wire types are hand-written; five `call<T>` clones have already drifted on 204/details/actor semantics). Either re-commit — regenerate types from the merged specs 003–009 contracts, route all detail pages through the registry, register channel — or delete the dead halves and codify the direct-wiring pattern. Keeping both costs maintenance and reads poorly in a portfolio code review.

5. **Make the headline promises user-reachable.** Two flagship claims currently have no path for a real user: "approve tool calls from your IM" (the only shipped agent never requests approval) and live channel operation (verification still pending, and the UI lacks the test-message button that would prove it). An opt-in "require approval for tool calls" mode on the built-in agent makes both the 008 approval UI and the 009 IM prompts real with minimal new surface; a notify-backed "Send test message" on the channel detail page gives users (and you) one-click end-to-end verification. Demo-ability is the portfolio currency — spend effort where a viewer can see it work.

---

## Appendix: Completeness Critique

- **Dynamic verification never performed** — all dimensions are static reads; nobody ran `make verify`, `backend` pytest (275 test files), frontend vitest (~102 test files), or `e2e/` Playwright + MCP suites to confirm they actually pass on `feature/channels`.
- **specs/001–009 (86 tracked files)** — spec/plan/tasks/quickstart vs shipped-code drift and acceptance-checklist closure isn't owned by any dimension (docs-accuracy targets `docs/`, product-design targets behavior, not spec artifacts).
- **e2e/mcp/specs/** — protocol-level MCP round-trip tests (stdio, crash recovery, concurrent clients) likely missed: `tests-fe-e2e` reads as web/FE e2e only.
- **scripts/ repo guards** — `scripts/audit_acceptance.py`, `check_file_sizes.py`, `check_response_models.py`, `check_unit_purity.py`, `build_binaries.sh`, `smoke_test_bundle.sh` are custom quality gates no dimension reviews for correctness/coverage.
- **docs-site/ VitePress infrastructure** — `.vitepress/` config, `scripts/sync-reference.mjs` (+ its test), `zh/` parity, `public/` assets, and link integrity; docs dimensions cover prose in `docs/`, not the portal build.
- **License/legal audit** — only root `LICENSE`; no third-party license scan of `frontend/pnpm-lock.yaml`, `backend/uv.lock`, `desktop/Cargo.lock`; no NOTICE file.
- **Git hygiene** — e.g. duplicate lockfiles both tracked in `frontend/` (`package-lock.json` AND `pnpm-lock.yaml` with `pnpm-workspace.yaml`), `.gitleaksignore` entry validity, commit-history/branch state vs `main`; no dimension audits repo hygiene.
- **agents/ + .specify/ contributor-process docs** — `agents/{stack,workflow,testing,frontend,sdd}.md`, `agents/ui-shell/`, `.specify/memory/*` accuracy against actual practice; bilingual dimension checks `.zh.md` parity but not whether these conventions match reality.
