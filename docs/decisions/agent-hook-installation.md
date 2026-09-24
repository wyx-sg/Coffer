# Coffer's Agent Hooks Are Marker-Scoped, Explicit, Audited and Repaired When Stale

**Status**: Accepted
**Date**: 2026-09-23
**Deciders**: Yuxing Wu
**Related**: spec memory; [Aggregate the Agents' Memory; Never Write It](aggregate-agent-memory-never-write-it.md); [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md); [Experimental Features Instead of a Release Branch](experimental-features-instead-of-a-release-branch.md); [Resource Identity Is an Immutable uid](resource-identity-is-an-immutable-uid.md); research note [agent plugins](../research/agent-plugins.md); PR #413

## Context

Memory delivery hands a session Coffer's memory index at its start
([Aggregate the Agents' Memory](aggregate-agent-memory-never-write-it.md)). For
an agent the developer drives themselves, the only way in is the agent's own
lifecycle hook: an entry in its settings file that runs a command when a
session begins, whose stdout the agent adds to the context. Coffer's command is
`coffer memory context --agent-uid <uid> --cwd "$PWD"`.

The two agents differ:

- **Claude Code** has a `SessionStart` event. Coffer installs on it in
  `~/.claude/settings.json` with the matcher `startup|resume|clear|compact`,
  so the context lands however the session began
  (`backend/coffer/infrastructure/memory/delivery/claude_code.py`).
- **Codex** has no session-start event; the hook events in its binary are
  `PreToolUse`, `PostToolUse`, `PreCompact`, `Stop` and `UserPromptSubmit`.
  Coffer installs on `UserPromptSubmit` in `~/.codex/hooks.json`, wrapped in a
  once-per-session guard — a lock file under `$TMPDIR` keyed by `$PPID`
  (`infrastructure/memory/delivery/codex.py`).

These files are not Coffer's. They carry the developer's own `env`,
`permissions` and hooks other tools wired in (on the maintainer's machine,
another CLI's `UserPromptSubmit`, `PreToolUse` and `Stop` entries). Two
incidents shaped the rules:

- **An injection hook shipped and never ran.** The session-context injection
  layer removed in 2026-09 had never once been installed on the maintainer's
  machine, and for two months nothing said so. "Installed" and "has ever fired"
  were one unexamined assumption.
- **A hook went stale and nothing noticed (PR #413).** When `coffer memory
  context` stopped taking `--agent` and started taking `--agent-uid`, every
  hook already on disk kept passing an option that no longer existed. The agent
  printed a usage error at the start of every session and memory never reached
  it — for months — while the status page reported `installed: True` beside the
  broken command. Detection matched the marker only and never read the
  arguments, which is exactly what let a reinstall replace an entry in place,
  and exactly why a stale entry looked installed.

## Options Considered

### Option A — Marker-scoped entries, installed explicitly, audited, and repaired by comparing the command (chosen)

Coffer's command starts with a no-op `: coffer-memory;`, so an entry is
recognised as Coffer's by that prefix regardless of what follows. Install
inserts or replaces only Coffer's entry on its event; remove takes out only
that entry and drops an event array or `hooks` object it leaves empty. Install
and remove are explicit acts, each audited. Every fire is audited. At boot, and
on every `memory` feature switch, Coffer compares the command installed with
the command this build would write, and reinstalls where they differ.

- **Pros.** Foreign entries on the same event, other events and unrelated keys
  are never touched. Installed state and firing are two separately answerable
  facts — the status says "installed", the audit log says "fired". A CLI change
  that alters the command heals itself at the next boot without a person
  noticing anything.
- **Cons.** Coffer still edits a file it does not own, so it must parse it
  faithfully and refuse (`MEMORY_DELIVERY_CONFIG_INVALID`) rather than clobber
  JSON it cannot read. Repair re-writes the file on every command change.
- **Why it wins.** It keeps the one property the marker was chosen for —
  in-place replacement — and closes the hole that property opened.

### Option B — Marker-only detection (the design PR #413 replaced)

Recognise Coffer's entry by the marker and treat its presence as "installed".

- **Pros.** Simple; a reinstall naturally replaces an old entry whatever its
  arguments.
- **Cons.** A command whose arguments went stale reads as installed. The
  `--agent` → `--agent-uid` rename broke delivery on every machine silently.
- **Why it lost.** It measured the wrong thing: presence, not correctness.

### Option C — Own the whole file

Write the agent's hooks file from a template Coffer owns, or keep a separate
file Coffer fully controls.

- **Pros.** No parsing of foreign content; drift is a byte comparison.
- **Cons.** Both agents read hooks from the same settings file the developer and
  other tools use; there is no include mechanism to point at a Coffer-owned file.
  Rewriting the whole file would destroy other tools' entries and the
  developer's own settings.
- **Why it lost.** Not available without destroying content Coffer does not
  own.

### Option D — Package the hook as an agent plugin

Ship the hook inside an agent-native plugin the developer installs with the
agent's own tooling.

- **Pros.** The agent owns installation, removal and update; Coffer edits no
  settings file.
- **Cons.** The two agents share no plugin format, so this is two packages to
  build and publish, and an agent without hook-carrying plugins would still need
  Option A. A plugin's copy of the command is pinned
  to the plugin's version, so a CLI change still needs the plugin re-published
  and re-installed, and Coffer could neither see nor repair a stale one.
- **Why it lost.** Two mechanisms instead of one, and the staleness problem
  moves somewhere Coffer cannot repair it.

### Option E — No hooks; delivery is pull-only

Install nothing; the agent reaches memory only through `coffer__recall` or the
files.

- **Pros.** Coffer never edits an agent's settings.
- **Cons.** Measured on the live vault: `coffer__recall` was called 5 times in
  its lifetime and 0 times in the three weeks before the redesign. An agent
  that must reach for memory does not.
- **Why it lost.** Session-start delivery is the whole point of memory. It stays
  consent-based — nothing is installed unless a person asks.

## Decision

**Coffer's delivery hooks are marker-scoped entries in the agent's own settings
file, installed and removed only by an explicit act, audited on install, remove
and every fire, and repaired whenever the installed command differs from the
one this build would write.**

- **Marker-scoped.** An entry is Coffer's if and only if its command starts with
  `: coffer-memory` (`backend/coffer/domain/memory/delivery.py`). Coffer
  touches no other entry.
- **Explicit and removable.** Nothing installs a hook as a side effect of
  registering an agent, aggregating memory or serving a turn. Install is
  idempotent; remove with nothing installed writes no file and records no event.
  Files are read and written through the agent's allowlisted config-file specs,
  atomically, leaving a `.bak`.
- **Audited.** `memory_delivery_installed`, `memory_delivery_removed` and one
  `memory_delivery_fired` per fire. The per-agent status reports installation
  only, never a last-fired time.
- **Repaired when stale.** `DeliveryService.heal_drift`
  (`backend/coffer/application/memory/delivery.py`) runs at boot and on every
  `memory` switch: for each agent with a hook installed whose command differs
  from `command_for(uid)`, it reinstalls in place. It is best-effort per agent,
  and it never installs a hook for an agent that has none — that would be a
  silent install.
- **Follows the `memory` feature.** Switching `memory` off removes every
  Coffer hook and remembers, on this machine, which agents it removed them from;
  switching it on puts them back into exactly those agents, then repairs
  (`application/memory/delivery_switch.py`).
- **Named by uid.** The command names the agent by its immutable uid, not its
  editable name — a string that sits in someone else's file for months must not
  reference a label.

## Consequences

- **A hook cannot silently rot again.** A CLI or packaging change that alters
  the command is rolled out to every installed hook at the next boot.
- **Whether delivery happens is answerable.** The audit log shows fires; a hook
  that is installed and never fires is visible as exactly that.
- **Every command change is a settings-file write** on every machine with a
  hook installed, recorded as an install event with its actor.
- **Obligation.** A new agent adapter must implement the full
  `DeliveryAdapter` (install, remove, `find_command`, `command_for`) so the same
  heal covers it. Any future hook Coffer installs into another tool's file
  follows these same rules.
- **Enforcement.** Spec memory "Install delivery hooks explicitly and
  removably", spec memory "Repair stale delivery hooks", spec memory "Audit
  every delivery fire".
