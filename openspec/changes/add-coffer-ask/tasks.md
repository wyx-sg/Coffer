## 1. Verify the interception

- [ ] 1.1 Fixture test against the bundled Claude Code CLI: a PreToolUse hook on `AskUserQuestion` returning `allow` + `updatedInput.answers` reaches the model as the answer (else switch to the deny-with-answers fallback in design §3)

## 2. Backend

- [ ] 2.1 Domain: question block model, states, answer validation; error code `QUESTION_CLOSED`
- [ ] 2.2 Migration: pending-question index for `needs_you` and the count (block lives in message content)
- [ ] 2.3 Application: raise / answer / cancel with first-answer-wins; cancel on Stop, turn end, shutdown; 24 h expiry
- [ ] 2.4 Turn token: mint per turn, set `COFFER_TURN_TOKEN` in both adapters' env, registry token → turn
- [ ] 2.5 Shim forwards `X-Coffer-Turn`; gateway lists and serves `coffer__ask` only with a live token
- [ ] 2.6 Codex config entry for `coffer`: `env_vars`, `tool_timeout_sec = 86400`
- [ ] 2.7 Claude Code adapter: PreToolUse hook for `AskUserQuestion`
- [ ] 2.8 Turn events `question_asked` / `question_closed`; REST answer route; `ConversationOut.needs_you`; needs-you count route; `make contracts`
- [ ] 2.9 Channels: question cards (single, multi-select + Submit), text-as-answer routing, rewrite on close, ping; delete `needs_you.py` and the sentinel prompt note; channel note mentions `coffer__ask`

## 3. Frontend

- [ ] 3.1 Question card in the reply (single, multi-select, descriptions, context markdown) and its collapsed line
- [ ] 3.2 Reply box answers a pending question; placeholder; "Waiting for you" header
- [ ] 3.3 List "Needs you" status; sidebar Conversations count

## 4. Docs and tests

- [ ] 4.1 Unit + integration tests per scenario with acceptance markers
- [ ] 4.2 docs-site guides chat / channels, reference mcp-tools and channel-commands (en + zh)
