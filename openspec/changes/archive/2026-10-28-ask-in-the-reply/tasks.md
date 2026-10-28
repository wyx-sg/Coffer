## 1. Decision and specs

- [x] 1.1 ADR `ask-in-the-reply-not-in-a-card` (rewrites `a-question-outlives-the-turn-that-asked-it`); README index
- [x] 1.2 Edit specs `chat`, `channels`, `mcp-gateway`, `agent-registry` directly (`skip_specs: true`)

## 2. Backend

- [x] 2.1 Remove `coffer__ask`, the question service, `AskUserQuestion` interception and the question events
- [x] 2.2 Keep the turn token for turn-scoped built-ins (`turn_scope`, `turn_tokens`)
- [x] 2.3 Claude Code: `disallowed_tools=["AskUserQuestion"]`
- [x] 2.4 Channel note and default reply style: ask in the reply, all at once
- [x] 2.5 Remove `needs_you` from session listings; ignore old card taps
- [x] 2.6 Acceptance and unit tests

## 3. Frontend, docs and design

- [x] 3.1 Session rows and busy dialog without Needs you
- [x] 3.2 docs-site, en and zh
- [x] 3.3 Run design canvas
