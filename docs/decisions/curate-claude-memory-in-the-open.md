# Curate Claude Code's Memory in the Open, and Turn Auto Dream On Only When Asked

**Status**: Accepted
**Date**: 2026-10-16
**Deciders**: Yuxing Wu
**Related**: [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), spec memory "Show each agent's own curation and ask it to curate now"

## Context

Coffer leaves merging and forgetting memories to each agent's own curation.
Two gaps showed on the owner's Mac.

**Auto Dream's state.** Claude Code's Auto Dream is an undocumented preview.
It runs in a project after about a day and a few sessions, and leaves a
`.consolidate-lock` in that project's memory folder. Whether it runs is
decided by `autoDreamEnabled` in `~/.claude/settings.json` when present, and
otherwise by an account flag Claude Code caches in `~/.claude.json`. The flag
was off for the owner's account, and the Memory tab said only "unknown", so
nothing had been curated. The owner asked whether installing Coffer should
just turn it on.

**Curate now.** The button started `claude -p` headless in the home folder.
Headless, Claude Code may not edit files without permission, and from `~` it
sees only the home project's memory, so the run changed nothing and the
person saw nothing. The owner asked for curation to open the agent in a
terminal so they watch the whole run.

How comparable tools handle this: Claude Code itself exposes Auto Dream only
as a toggle in `/memory` and never turns it on for the person. Codex runs
its consolidation by itself whenever memories changed and offers no manual
trigger. Package managers and dotfile tools that touch an editor's settings
(VS Code extensions, Homebrew casks) ask first and keep a backup. Cursor and
Windsurf rewrite their own memories in the open, in the chat the person is
in.

## Options Considered

### Auto Dream

#### Option A — Turn it on during install

- **Pros.** Curation works with no step from the person.
- **Cons.** Coffer would change another tool's preview setting unasked, and
  the person would not know why Claude Code started rewriting memory files.

#### Option B — Show the real state and a Turn on button (chosen)

Read the setting, fall back to the cached account default, say which one
decided and when Auto Dream last ran; while it is off, **Turn on** adds only
`"autoDreamEnabled": true` after the person confirms, with a backup.

- **Pros.** The person sees why curation is not happening and fixes it in
  one click; nothing changes unasked; undoable from the backup.
- **Cons.** Reads a cached, undocumented flag that Claude Code may rename;
  then the state shows as unknown again, never wrong.

#### Option C — Show the state only

- **Pros.** Coffer writes nothing into Claude Code's settings.
- **Cons.** The person must find and edit `settings.json` by hand.

### Curate now

#### Option 1 — Keep the headless run, with edit permission

- **Pros.** One click, no window.
- **Cons.** The person cannot see or stop what is rewritten; granting edit
  permission headless bypasses Claude Code's own prompts.

#### Option 2 — Open Claude Code in the terminal with a prompt (chosen)

A hand-off like Coffer's others: the prompt names the memory folders Coffer
wrote into and asks Claude Code to plan, then consolidate one folder at a
time and leave Coffer's markers and rules file alone.

- **Pros.** Every change is visible and goes through Claude Code's own
  permissions; the folders are named, so the run reaches every project.
- **Cons.** The person stays at the terminal while it runs.

#### Option 3 — Remove Curate now

- **Pros.** Nothing to maintain.
- **Cons.** A rarely used project keeps duplicates until Auto Dream reaches it.

## Decision

Option B and Option 2, chosen by the owner on 2026-10-16. Codex gets no
**Curate now**, since its consolidation already runs on its own.

## Consequences

- `memory_curation_enabled` is recorded when **Turn on** changes the setting;
  `memory_curation_requested` when **Curate now** hands curation off.
- If Claude Code renames its flag, Auto Dream shows as unknown until Coffer
  follows; **Turn on** still writes the documented-in-practice setting.
