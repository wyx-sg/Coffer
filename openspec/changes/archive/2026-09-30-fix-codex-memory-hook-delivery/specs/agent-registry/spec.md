## MODIFIED Requirements

### Requirement: List every hook in the agent's native config
The system MUST list, read only, every command hook the agent will run. That covers the hooks in the agent's own hook-carrying files (the type's child spec names them) and those in each enabled plugin's hook file. Each is listed with its event, matcher, command, timeout, source (`user` or `plugin`, with the plugin's id) and the file that declares it. Project-level settings are not read, because Coffer does not know which repositories the agent is used in.

Coffer's own delivery hook MUST be marked, with the event it sits on. Its health MUST be reported by the same marker-and-command comparison the boot repair uses:
- `current` when the installed command is exactly the one Coffer would write now;
- `stale` when Coffer's marker carries another command;
- `missing` when it is absent.

The report MUST also say whether the agent will run the hook, as its **trust**: `trusted`, `untrusted`, `modified` (approved for an earlier command), `disabled`, `unknown` (the agent's approval record does not parse), or `not_required` for an agent that runs every hook it finds. It MUST also give the last recorded fire from the audit log.

The listing MUST be served by `GET /api/v1/agents/{uid}/hooks` and `coffer agent hooks <name> [--json]`, and MUST write nothing and record no audit event. When the agent will not run a current hook, the CLI MUST say what the user does about it. A file that does not parse MUST be reported as a parse error beside the hooks the other files yield.

#### Scenario: list an agent's hooks with Coffer's own marked
- **GIVEN** a registered Claude Code agent whose `settings.json` carries a foreign `PreToolUse` hook and Coffer's delivery hook, whose `settings.local.json` carries a `Stop` hook, and which has one enabled and one disabled plugin with a hook file each
- **WHEN** the user lists the agent's hooks
- **THEN** the foreign hooks, the `Stop` hook and the enabled plugin's hook are listed with their sources and files, the disabled plugin's hook is not, and only Coffer's hook is marked as Coffer's
- **AND** Coffer's hook reads `current` with trust `not_required` and no recorded fire, and nothing is written or audited

#### Scenario: report a stale Coffer hook
- **GIVEN** a registered Codex agent whose `hooks.json` carries Coffer's marked hook on `UserPromptSubmit`, as an older build wrote it, and one recorded fire
- **WHEN** the user lists the agent's hooks
- **THEN** Coffer's hook reads `stale` on `UserPromptSubmit`, the installed and expected commands differ, and the last fire is reported
