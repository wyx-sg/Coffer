## Why

Coffer's memory hook has never run in Codex. A live test on Codex 0.155.1 found three causes, and each one alone is enough to deliver nothing:

- **Codex never trusted the hook.** Codex runs a non-managed hook only after the user has approved its exact definition in `/hooks`. It records that approval as a hash in `config.toml` and silently skips a hook with no matching hash. Coffer's entry read `modified`: every install, and every change to its arguments, made the stored approval stale.
- **The command was not on the hook's `PATH`.** Codex runs hooks under `/bin/zsh` without the user's rc files, so `~/.coffer/bin` is not on the path and a bare `coffer` is "command not found".
- **The once-per-session guard used the wrong key.** It was keyed on `$PPID`. Every session of one `codex app-server` (Codex Desktop, the IDE hosts) shares that pid, so only the first session per app-server would have fired. Codex now has a `SessionStart` event, and its hook input carries the session's id.

The same test showed the payload is too large for either agent to show whole. Claude Code keeps a hook's output inline only up to about 10,000 characters; past that, the model sees a ~2 KB preview. Codex cuts `additionalContext` past 2,500 tokens, counted as UTF-8 bytes / 4. A real vault's index is 30–45 KB, so a session saw only the newest few `global` lines.

## What Changes

- Codex's hook moves to `SessionStart` (matcher `startup|resume|clear|compact`) with no guard. It prints the event's JSON `hookSpecificOutput.additionalContext` through a new `coffer memory context --hook-event <Event>` option.
- Both agents' hooks call the `coffer` CLI by absolute path. The composition root resolves the path the way the provider's `apiKeyHelper` already does, preferring the stable `~/.coffer/bin/coffer`.
- Coffer computes Codex's trust hash the way Codex does and reads `[hooks.state]` read only. It reports the result as `trust` (`trusted`, `untrusted`, `modified`, `disabled`, `unknown`, or `not_required` for Claude Code) in `GET /api/v1/agents/{uid}/hooks`, `coffer agent hooks` and the agent's Hooks tab.
- The reconciler reports a current but unapproved hook as `hook_untrusted`, with "run /hooks in Codex". That report reaches the attention list. Coffer never writes the approval.
- Every hook delivery is composed under 9,500 UTF-8 bytes, which fits both agents' limits. The trim keeps the current repository's lines ahead of `global`'s, newest first, and says how many were dropped and where they are.
- Existing installs migrate on the next reconcile pass. The target compares the event the hook sits on as well as its command, so an older build's `UserPromptSubmit` entry is rewritten onto `SessionStart`, and every Coffer-marked entry on any event is replaced.

## Capabilities

### New Capabilities

### Modified Capabilities
- `memory`: delivery hooks call the CLI by absolute path, and Codex's hook sits on `SessionStart` with JSON output. Repair judges the event and reports an unapproved hook without writing. The delivery ceiling has concrete byte figures.
- `agent-registry`: the hooks listing reports whether the agent will run Coffer's hook.
- `agent-registry/codex`: Coffer's hook sits on `SessionStart`, and Codex's trust record is read to report that hook's trust.

## Impact

- Backend: `domain/memory/delivery.py`, new kind-agnostic `domain/hook_trust.py`, both adapters in `infrastructure/memory/delivery/`, `application/memory/{delivery,delivery_reconcile,context}.py`, `application/agent/hooks_service.py`, `surfaces/http/{agent_facet_wiring,agent_hooks_routes}.py`, `surfaces/http/memory/delivery_routes.py`, `surfaces/cli/{memory_cmd,agent_hooks_cmd}.py`.
- Contract: agent-registry `CofferHookOut.trust` (`HookTrust`); frontend codegen; the Hooks tab shows a trust chip.
- Docs: `docs-site/architecture/memory.md`, the memory and agents guides, the filesystem reference, the memory data model, and the hook-installation ADR.
