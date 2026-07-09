# ADR-042: Context injection is a facet with three mechanisms, not one

> 中文: [ADR-042-context-injection-mechanisms.zh.md](ADR-042-context-injection-mechanisms.zh.md)

**Status**: Accepted
**Date**: 2026-07-09
**Deciders**: Yuxing Wu
**Related**: supersedes the capability matrix of [ADR-040](ADR-040-re-widen-agent-registry.md); spec `004-agent-registry` (FR-003a, FR-043/044); builds on [ADR-037](ADR-037-rules-runtime-injection.md) (SessionStart injection)

## Context

[ADR-040](ADR-040-re-widen-agent-registry.md) re-added `opencode`, `hermes`, and
`cursor` as managed agents and recorded a capability matrix (spec 004, FR-003a)
declaring which facets each product supports. Four of its cells were wrong. A
first-principles re-check against upstream docs and source found:

1. **Cursor has a documented `sessionStart` hook.** ADR-040 deferred it because
   "headless firing of SessionStart/End is undocumented upstream." In fact
   `~/.cursor/hooks.json` documents `sessionStart`, and its output schema carries
   an `additional_context` field — precisely Coffer's injection point. (Its
   sibling `beforeSubmitPrompt` *cannot* inject; its output is only
   `{continue, user_message}`.)
2. **opencode's plugins can inject, not merely observe.** ADR-040 recorded "only
   in-process JS plugin callbacks." The `@opencode-ai/plugin` `Hooks` interface
   exposes `chat.message`, whose `output.parts` is mutable, and
   `experimental.chat.system.transform`, which pushes onto the system prompt.
3. **Hermes' session hooks are worse than deferred — they are dead.** ADR-040
   deferred them as "a new mechanism." Upstream issue
   [NousResearch/hermes-agent#2817](https://github.com/NousResearch/hermes-agent/issues/2817)
   confirms `on_session_start`, `on_session_end`, `pre_llm_call`, and
   `post_llm_call` "are documented but never invoked" — they exist only in
   `VALID_HOOKS`. Closed as not planned. Only the tool hooks fire.
4. **Cursor's provider projection really is impossible** — the one cell that
   held. `cursor-agent --help` (v2026.02.27) exposes no base-URL flag;
   `cli-config.json` has no endpoint key; custom base URL is IDE-only.

The root cause of the misjudgements is structural, not clerical.
`HookInjectionSpec` modelled exactly one delivery mechanism — *write a shell
command into a JSON config file* — and so any product that injects context some
other way fell through as an "absent facet." The abstraction was named after its
implementation (a hook) rather than its purpose (getting Coffer's rules and
memory in front of the model).

## Decision

**Replace `HookInjectionSpec` with `ContextInjectionSpec`, discriminated by an
`InjectionMode` with three values**, one per mechanism that exists upstream:

- `SHELL_COMMAND` — the agent execs `coffer-hook` and reads its stdout.
  Claude Code, Codex, **and Cursor**.
- `PLUGIN_DROP` — the agent offers only in-process JS/TS callbacks. Coffer drops
  a thin plugin file that spawns the same `coffer-hook` binary. opencode,
  openclaw.
- `INSTRUCTIONS_BLOCK` — the agent has no working hook at all. Coffer renders
  the payload into a marker block in the agent's instructions file. Hermes.

**All three share one payload source**: the daemon's
`GET /api/v1/agents/{agent}/session-context` endpoint. Only the last mile —
who fetches it and in what envelope it reaches the model — varies. This is what
keeps the mechanisms from becoming three parallel implementations.

**`SHELL_COMMAND` alone is implemented in this slice.** *(Since implemented: `INSTRUCTIONS_BLOCK` — FR-047, `PLUGIN_DROP` — FR-048.)* `PLUGIN_DROP` and
`INSTRUCTIONS_BLOCK` are recognized extension points with no descriptor using
them yet — exactly as `SkillDeliveryMode` already reserves `RULES_MDC` and
`EXTERNAL_DIR`. A service that meets an unimplemented mode treats it as an absent
facet (`HookInstallUnsupported` → 422; `status` reports `installed=False`).

**A second discriminator, `HookFlavor`, carries the on-disk shape.** Shell-command
hooks are not one shape. Claude Code and Codex key their hooks file by PascalCase
event names holding matcher groups; Cursor keys it by camelCase names holding
flat command entries, under a top-level `version`. `HookFlavor` also selects the
stdout envelope `coffer-hook` prints — `hookSpecificOutput.additionalContext` for
Claude, a top-level `additional_context` for Cursor.

**Cursor's installed command carries `--dialect` and `--event`.** Cursor keys
`hooks.json` by event but does not contractually name the event on the hook's
stdin. Rather than depend on an unverified payload field, the event is baked into
the command's args at install time. Two consequences follow:

- **When `--event` names a SessionStart, `coffer-hook` never reads stdin.**
  `sys.stdin.read()` blocks until EOF and nothing bounds it (the 5s timeout covers
  only HTTP), so an agent that spawns the hook with stdin left open would stall on
  its own startup — precisely what the failure-is-silent contract exists to
  prevent. The payload is only read when it is actually needed.
- **`cwd` is omitted, never sent empty, when unknown.** The daemon scopes memory
  and rules by the nearest git root of `cwd`; an empty string resolves against the
  *daemon's* own working directory, a long-lived process that may sit in an
  unrelated repo. Absent `cwd` is the only value that means global scope. The hook
  process inherits the agent's working directory, so that is the correct source
  when the payload omits it; if it cannot be read (a deleted directory), the
  parameter is dropped and the bundle still arrives, globally scoped.

**Cursor's provider projection stays an absent facet, but is surfaced, not
hidden.** The UI states the reason (cursor-agent is locked to Cursor's backend)
rather than silently omitting the control.

## Consequences

- Cursor gains session-context injection — rules and memory reach `cursor-agent`
  exactly as they reach Claude Code. It was never an upstream gap.
- The facet is now named for its purpose, so the two remaining agents can be
  closed out by *adding a mode implementation*, not by widening a hook model:
  opencode and openclaw via `PLUGIN_DROP`, hermes via `INSTRUCTIONS_BLOCK`.
- `hook_install`'s transforms take a `commands: Mapping[HookEvent, str]` rather
  than one command, because Cursor needs a distinct command per event.
- Coffer's entry-recognition parses user-authored commands with `shlex.split`,
  which raises on unbalanced quotes. A command Coffer cannot parse is by
  definition not Coffer's (it quotes everything it writes), so a parse failure
  reads as "not ours" rather than 500-ing the daemon.
- Uninstall is a true inverse of install: the top-level `version` Coffer writes
  into a Cursor `hooks.json` that had none is removed again when nothing else
  remains in the document. A `version` beside other content is the file's, and
  survives.
- Cursor's config-file allowlist gains a `hooks` key (`~/.cursor/hooks.json`).
- Every capability gap now carries evidence. A cell reading "N/A" must cite the
  upstream doc, flag, or issue that makes it so; three of ADR-040's four did not,
  and all three were wrong.
- **Headless firing of Cursor's `sessionStart` is not empirically confirmed.**
  The mechanism is documented and a marker test was blocked by `cursor-agent`
  requiring authentication. Strong indirect evidence exists (Cursor's docs state
  cloud agents "run only command-based hooks"; Skynet installs CLI-targeting
  hooks into the same file). This is the one claim in this ADR resting on docs
  rather than a live probe. **Update (2026-07-10): confirmed by an authenticated
  live probe** — with Coffer's exact `hooks.json` shape installed,
  `cursor-agent -p` executed the hook command and the `additional_context`
  envelope reached the model.

## Alternatives considered

- **Keep `HookInjectionSpec`, add a parallel `PluginDropSpec`.** Rejected: two
  facets answering the same question ("how does context reach the model?") means
  every consumer checks both, and hermes — which needs neither — stays
  permanently gapped.
- **Drop hooks entirely; inject via instructions files for every agent.** Simple
  and uniform, but it trades away the dynamic path: a static block cannot fetch
  the latest memory per turn, and SessionEnd distillation disappears. Rejected.
- **Leave Cursor deferred until headless firing is empirically proven.**
  Rejected: the mechanism is documented and the install is reversible
  (`.bak` + uninstall). Shipping it behind a documented uncertainty beats
  withholding a capability the product advertises.
