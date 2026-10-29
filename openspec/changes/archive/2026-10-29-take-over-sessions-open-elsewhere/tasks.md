## 1. Decision and specs

- [x] 1.1 ADR `a-coffer-turn-takes-over-a-session-open-elsewhere`; README index
- [x] 1.2 Edit `openspec/specs/chat/spec.md` and the `channels` citation directly (`skip_specs: true`)

## 2. Backend

- [x] 2.1 `ProcessSessionTakeover` ends terminals naming the session before a turn
- [x] 2.2 `CodexThreadRelease`: background app-server path and terminal lock-holder path
- [x] 2.3 Codex adapter retries `thread/resume` once after a release
- [x] 2.4 New refusal text (backend and web i18n)
- [x] 2.5 Acceptance, unit and integration tests

## 3. Docs

- [x] 3.1 docs-site guide, architecture and error-code reference, en and zh
