## MODIFIED Requirements

### Requirement: List every hook in the agent's native config
The system MUST list, read only, every command hook the agent will run. That covers the hooks in the agent's own hook-carrying files (the type's child spec names them) and those in each enabled plugin's hook file. Each is listed with its event, matcher, command, timeout, source (`user` or `plugin`, with the plugin's id) and the file that declares it. Project-level settings are not read, because Coffer does not know which repositories the agent is used in.

Coffer's own memory hook — its two entries, on `SessionStart` and `UserPromptSubmit` ([memory](../memory/spec.md) "Install delivery hooks explicitly and removably") — MUST be marked, each entry as Coffer's, and reported as one hook with the set of events its entries sit on. Its health MUST be reported by the same marker-and-command comparison the boot repair uses:
- `current` when the entries sit on exactly the events Coffer would install on and each carries exactly the command Coffer would write now;
- `stale` when Coffer's marker carries another command or sits on another set of events;
- `missing` when it is absent.

The report MUST also say whether the agent will run the hook, as its **trust**: `trusted`, `untrusted`, `modified` (approved for an earlier command), `disabled`, `unknown` (the agent's approval record does not parse), or `not_required` for an agent that runs every hook it finds. It MUST also give the last recorded fire from the audit log.

The listing MUST be served by `GET /api/v1/agents/{uid}/hooks`, and MUST write nothing and record no audit event. When the agent will not run a current hook, the trust reports why, and the Hooks tab and the attention list say what the user does about it. A file that does not parse MUST be reported as a parse error beside the hooks the other files yield.

Each listed hook MUST also carry where it sits in its file — `group_index` and `hook_index`, the positions in `hooks.<event>[group_index].hooks[hook_index]` — so a person can find the entry, and the REST listing reports them.

On the agent's Hooks tab the listing is two parts, Coffer's first. **Coffer's memory hook** is one block of properties, never one row per entry: its state (and how long ago it fired), its command, the events it sits on and the file that declares it, with its one fix at the block's title — **Repair** when it is stale or missing, **Check again** while the agent has not approved it — and, when it has never fired, the likely cause and a link to Activity. The reason a state is a problem is written in the block's own line. **The agent's own hooks** — Coffer's excluded — are one table of Event, Command, Matcher and File, with a search over the command and an **Event** filter that lists each event with its count; the table says how many of how many are shown once either narrows it. A row opens a read-only details dialog with the command in full, the event and when it runs, the matcher, the type, the timeout, the file and the entry's position in it (`hooks.<event>[group].hooks[hook]`), with **Copy command** and **Open in Config files**; nothing in the dialog writes, because a hook is changed in its own file. A file name opens that file in Config files, except a plugin's hooks file, which has no Config files entry.

#### Scenario: list an agent's hooks with Coffer's own marked
- **GIVEN** a registered Claude Code agent whose `settings.json` carries a foreign `PreToolUse` hook and Coffer's memory hook, whose `settings.local.json` carries a `Stop` hook, and which has one enabled and one disabled plugin with a hook file each
- **WHEN** the user lists the agent's hooks
- **THEN** the foreign hooks, the `Stop` hook and the enabled plugin's hook are listed with their sources and files, the disabled plugin's hook is not, and only Coffer's two entries are marked as Coffer's
- **AND** Coffer's hook reads `current` on both events with trust `not_required` and no recorded fire, and nothing is written or audited

#### Scenario: report a stale Coffer hook
- **GIVEN** a registered Codex agent whose `hooks.json` carries Coffer's marked hook on `UserPromptSubmit` alone, with a command other than the one Coffer would write now, and one recorded fire
- **WHEN** the user lists the agent's hooks
- **THEN** Coffer's hook reads `stale` on `UserPromptSubmit`, the installed and expected commands differ, and the last fire is reported

#### Scenario: list the hooks with their position in the file
- **GIVEN** a Claude Code `settings.json` whose `PreToolUse` event holds two groups, the second with two hooks
- **WHEN** the user lists the agent's hooks
- **THEN** the second hook of the second group reports `group_index` 1 and `hook_index` 1, and the first group's hook reports 0 and 0

#### Scenario: coffer's memory hook leads the Hooks tab and the agent's own follow
- **GIVEN** a Claude Code agent whose `settings.json` carries Coffer's two memory-hook entries beside three hooks of its own
- **WHEN** the user opens the agent's Hooks tab
- **THEN** Coffer's hook is one block with its state, command, the two events and its file, and the agent's own hooks are one table of three rows that does not repeat Coffer's
- **AND** choosing a row opens a read-only dialog with the command, event, matcher, type, timeout, file and position, and searching or filtering by event narrows the table and says how many of how many show
