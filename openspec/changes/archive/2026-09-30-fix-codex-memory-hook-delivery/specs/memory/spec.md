## MODIFIED Requirements

### Requirement: Bound delivery and prefer the current repository
Delivery MUST be bounded by a ceiling, and the ceiling MUST be sized for **an index** rather than for a handful of lines. A delivery that an installed hook prints MUST also stay within **9,500 UTF-8 bytes** of text. Both agents that run the hook cut anything longer, and both cuts lose the lines that matter. Claude Code keeps a hook's output inline only up to about 10,000 characters; past that, the model sees a ~2 KB preview holding the newest few `global` lines. Codex keeps `additionalContext` only up to 2,500 tokens, counted as UTF-8 bytes / 4, and cuts the middle. A byte count bounds both, because a text is never more characters than bytes.

When the index does not fit, the trim MUST drop the oldest lines, MUST state how many were dropped, and MUST name the directory holding them. A trimmed delivery still leaves every note reachable as a file, which is why a trim here is a much smaller loss than it was under the previous design. When the two partitions compete for the ceiling, **the current repository's lines MUST be preferred over `global`'s**. The previous design spent the budget the other way round: on a live vault of 189 entries it delivered 8 lines, and **none** were about the project the session was open in.

#### Scenario: an index too large for the ceiling is trimmed and says so
- **GIVEN** a partition whose index exceeds the delivery ceiling
- **WHEN** the session context is composed
- **THEN** the payload stays at or under the ceiling, the trim drops the oldest lines rather than an arbitrary set, and the text names how many were dropped **and the directory they are in**
- **AND** the current project's lines are preferred over `global`'s when the two compete, which is the reverse of what this layer did before and the reason it delivered nothing about the project it was open in (see "Bound delivery and prefer the current repository")

#### Scenario: a hook delivery fits both agents' hook output limits
- **GIVEN** a repository partition and a `global` partition of 300 notes each, written in English or in Chinese
- **WHEN** the context is composed for a hook
- **THEN** the text is at most 9,500 UTF-8 bytes, fewer than 10,000 characters, and at most 2,500 tokens by Codex's bytes / 4 count
- **AND** only repository lines are included, and one line names how many `global` lines were dropped and the `global` notes directory, and another does the same for the repository

### Requirement: Install delivery hooks explicitly and removably
For an agent the developer drives themselves, delivery MUST go through that agent's own hook mechanism, invoking Coffer's existing CLI **by absolute path**. An agent runs its hooks under a shell that need not have `~/.coffer/bin` on its `PATH`: Codex runs them under `/bin/zsh` without the user's rc files, and Claude Code started from the Dock does not inherit the login shell's `PATH`. The bare name is used only when the build cannot locate its own CLI.

Where the agent has a session-start event, delivery MUST use it. Both supported agents do: Claude Code's hook prints the text plain, and Codex's prints the event's JSON `hookSpecificOutput.additionalContext` through `coffer memory context --hook-event SessionStart`. The command MUST NOT carry a once-per-session guard keyed on a process id. Every session of one Codex app-server shares a parent pid, so such a guard lets only the first session fire.

Installation MUST be an **explicit act** on Coffer's surface: connecting the agent to Coffer, of which the hook is one part (spec agent-registry "Connect an agent to Coffer in one action"), or switching `memory` on while the agent is connected. It MUST be marker-scoped, idempotent, and removable without disturbing entries Coffer did not write. An install or a remove MUST take out Coffer's marked entry on **every** event, so an older build's entry on another event is never left behind beside the new one. Coffer MUST NOT install the hook silently, and MUST NOT write into any file that is an agent's *memory*: a hook lives in the agent's settings, which is a different thing.

#### Scenario: hook installation is marker-scoped and removable
- **GIVEN** an agent whose settings file already carries a foreign hook on the same lifecycle event, other events' hooks, and unrelated top-level keys
- **WHEN** delivery is installed, installed a second time, and then removed
- **THEN** install adds exactly **one** entry carrying Coffer's marker, a second install leaves one entry, and every foreign hook, every other event and every unrelated key is untouched
- **AND** remove takes out only the marked entry — dropping the event array and the top-level hooks key once they are empty — and with nothing installed it is a clean no-op that writes no file and records no audit event (see "Install delivery hooks explicitly and removably")

#### Scenario: a Codex hook fire prints the session-start JSON Codex reads
- **GIVEN** a partition with notes and a registered agent
- **WHEN** `coffer memory context --agent-uid <uid> --cwd <repository> --hook-event SessionStart` runs, as Codex's installed hook runs it
- **THEN** stdout is one JSON object whose `hookSpecificOutput` names `SessionStart` as its `hookEventName` and carries the composed index as `additionalContext`
- **AND** the fire is recorded, exactly as a plain-text fire is

### Requirement: Repair stale delivery hooks
An installed hook MUST be repaired when what Coffer would write is no longer what is installed, without waiting for a user to notice. This is the delivery-hook target of the unified reconciler ([resource-framework](../resource-framework/spec.md) "Converge what Coffer writes outside its database with one reconciler"), and it runs on every pass, not only at daemon start.

A hook is a string left in somebody else's settings file, and the CLI it invokes ships in a binary that keeps moving. When `coffer memory context` stopped taking `--agent` and started taking `--agent-uid`, every hook already on disk kept passing an option that no longer existed. The agent printed a usage error at the start of every session, and this layer never reached it again. Nothing reported the failure, because detection is marker-scoped and never reads the arguments. That same marker scoping is what lets a reinstall replace an entry in place, and it is why a stale entry reads as installed.

The target therefore judges a hook by the **event it sits on** and its **whole command**, both against what would be installed now. An older build's Codex hook on `UserPromptSubmit` is thereby moved onto `SessionStart` by an ordinary pass. One unreadable settings file MUST be reported as blocked without stranding the others.

For an agent that runs a hook only after the user has approved it (Codex), the target MUST also read whether the agent will run the installed hook. A current hook the agent will not run MUST be **reported, never written**, with the reason and the remedy (approve it with `/hooks` in Codex). Coffer MUST NOT write the agent's approval record: approving a hook is the user's act in the agent (spec agent-registry/codex "Leave Codex's internal-state tables untouched").

With `memory` on, the hooks wanted are those of every connected agent and of every agent that already carries one. A pass MUST NOT install a hook for an agent that has none, unless it runs because `memory` was just switched on or because a person applied that item. Otherwise the missing hook is reported and the agent's connection reads partial. A repair that added the hook would be an install Coffer made silently, which "Install delivery hooks explicitly and removably" forbids.

#### Scenario: a hook whose command went stale is repaired without being asked
- **GIVEN** an agent with Coffer's hook installed, and a Coffer build whose delivery command is no longer the one in that agent's settings file,
- **WHEN** a reconcile pass runs — at daemon start or on its period,
- **THEN** the entry is rewritten in place to the command this build would install, so the next session is served rather than shown a usage error,
- **AND** an agent whose hook is already current is left untouched, and an agent with no hook is not given one.

#### Scenario: an older build's Codex hook is moved to SessionStart
- **GIVEN** a connected Codex agent whose `hooks.json` carries an older build's Coffer entry on `UserPromptSubmit` (bare `coffer`, a `$PPID` guard) beside a foreign hook on that event
- **WHEN** a reconcile pass runs on its period
- **THEN** the difference is a modification of `command` and `event` and is repaired: Coffer's entry now sits on `SessionStart` and calls the CLI by absolute path
- **AND** the foreign `UserPromptSubmit` hook is untouched and no Coffer entry is left on that event

#### Scenario: a current Codex hook Codex has not approved is reported, not written
- **GIVEN** a connected Codex agent carrying the current hook, and no approval for it in Codex's `config.toml`
- **WHEN** a reconcile pass runs on its period, and again when a person applies it
- **THEN** the only difference is `trust`, and it is reported as `hook_untrusted` with the remedy "run /hooks in Codex"; nothing is written, and Coffer records no approval
- **AND** once `config.toml` records Codex's approval of that exact hook, the next pass finds nothing to do
