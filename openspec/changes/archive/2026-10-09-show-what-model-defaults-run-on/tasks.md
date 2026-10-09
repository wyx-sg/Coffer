## 1. Defaults name their model

- [x] 1.1 Codex discovery flags the `model/list` default; catalogue `builtin_default` / `resolved_default`; tests
- [x] 1.2 agent-providers route carries `builtin_default` and `resolved_default`; contracts regenerated
- [x] 1.3 Channel `/model`, `/model default`, `/status`, `/new` name the resolved default; tests
- [x] 1.4 Agents list, Overview › Model, Change model dialog, channel Overview name the default; en/zh copy; tests

## 2. Routing diagnostics

- [x] 2.1 Proxy logs an upstream error status without its body; test
- [x] 2.2 Change model dialog says a Claude Code switch leaves the desktop app alone; en/zh copy
- [x] 2.3 Root-cause the DeepSeek 404 (an OpenAI-protocol connection has no Messages API at its root); the switch test speaks the agent's wire; test
- [x] 2.4 DeepSeek preset offers its Anthropic endpoint as a second connection (agreed: separate connections); test
- [x] 2.5 ADR one-connection-is-one-endpoint

## 3. Context windows

- [x] 3.1 Windows resolve You set → endpoint → bundled list; `/windows` route; Models tab Window column and dialog; tests
- [x] 3.3 ADR context-windows-for-provider-models
- [x] 3.2 `CLAUDE_CODE_MAX_CONTEXT_TOKENS` for any connection whose chosen non-Claude model has a window; tests

## 4. Docs and canvas

- [x] 4.1 Providers guide and agents docs (en/zh); ADR index rows
- [x] 4.2 Agents and Run canvases
