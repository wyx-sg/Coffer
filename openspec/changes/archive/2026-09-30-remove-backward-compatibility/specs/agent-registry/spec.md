## MODIFIED Requirements

### Requirement: List every hook in the agent's native config
The system MUST list, read only, every command hook the agent will run. That covers the hooks in the agent's own hook-carrying files (the type's child spec names them) and those in each enabled plugin's hook file. Each is listed with its event, matcher, command, timeout, source (`user` or `plugin`, with the plugin's id) and the file that declares it. Project-level settings are not read, because Coffer does not know which repositories the agent is used in.

Coffer's own memory hook — its entries on `SessionStart`, `UserPromptSubmit`, `PreToolUse` and `PostToolUse` ([memory](../memory/spec.md) "Install delivery hooks explicitly and removably") — MUST be marked, each entry as Coffer's, and reported as one hook with the set of events its entries sit on. Its health MUST be reported by the same marker-and-command comparison the boot repair uses:
- `current` when the entries sit on exactly the events Coffer would install on and each carries exactly the command Coffer would write now;
- `stale` when Coffer's marker carries another command or sits on another set of events;
- `missing` when it is absent.

The report MUST also say whether the agent will run the hook, as its **trust**: `trusted`, `untrusted`, `modified` (approved for an earlier command), `disabled`, `unknown` (the agent's approval record does not parse), or `not_required` for an agent that runs every hook it finds. It MUST also give the last recorded fire from the audit log.

The listing MUST be served by `GET /api/v1/agents/{uid}/hooks` and `coffer agent hooks <name> [--json]`, and MUST write nothing and record no audit event. When the agent will not run a current hook, the CLI MUST say what the user does about it. A file that does not parse MUST be reported as a parse error beside the hooks the other files yield.

On the agent's Hooks tab, Coffer's memory hook MUST be **one row** per file that declares it — including the row of a missing hook — whose event cell reads "Memory hook · N events" followed by one chip per event it sits on. Its entries MUST NOT be shown as one row each, and its events MUST NOT be shown joined into one string. The tab's summary counts it as one hook.

#### Scenario: list an agent's hooks with Coffer's own marked
- **GIVEN** a registered Claude Code agent whose `settings.json` carries a foreign `PreToolUse` hook and Coffer's memory hook, whose `settings.local.json` carries a `Stop` hook, and which has one enabled and one disabled plugin with a hook file each
- **WHEN** the user lists the agent's hooks
- **THEN** the foreign hooks, the `Stop` hook and the enabled plugin's hook are listed with their sources and files, the disabled plugin's hook is not, and only Coffer's four entries are marked as Coffer's
- **AND** Coffer's hook reads `current` on all four events with trust `not_required` and no recorded fire, and nothing is written or audited

#### Scenario: report a stale Coffer hook
- **GIVEN** a registered Codex agent whose `hooks.json` carries Coffer's marked hook on `UserPromptSubmit` alone, with a command other than the one Coffer would write now, and one recorded fire
- **WHEN** the user lists the agent's hooks
- **THEN** Coffer's hook reads `stale` on `UserPromptSubmit`, the installed and expected commands differ, and the last fire is reported

#### Scenario: coffer's memory hook is one row with a chip per event
- **GIVEN** a Claude Code agent whose `settings.json` carries Coffer's four memory-hook entries beside three hooks of its own
- **WHEN** the user opens the agent's Hooks tab
- **THEN** Coffer's hook is one row whose event cell reads "Memory hook · 4 events" with a chip each for `PostToolUse`, `PreToolUse`, `SessionStart` and `UserPromptSubmit`
- **AND** no cell shows the events joined into one string, and the summary reads four hooks, one of them Coffer's
