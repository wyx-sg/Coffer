## REMOVED Requirements

### Requirement: Adopt an unmanaged skill
**Reason**: The requirement carried an exception for adopting from a disabled agent, and a scenario that named it. An agent can no longer be disabled, so the exception and its scenario have nothing to describe; the rule itself is unchanged and returns under the title "Adopt an unmanaged skill into the master store".
**Migration**: See "Adopt an unmanaged skill into the master store". The acceptance marker for "adopting from a disabled agent links the skill in place" is deleted with the scenario.

## MODIFIED Requirements

### Requirement: Deliver a skill only where it is enabled and in scope
A skill MUST be delivered to an agent if and only if the skill resource is enabled AND the skill's scope admits that agent — `skill.enabled AND is_active(skill.scope, agent=<agent>)`, one allow-list, left `null` admitting anything ([ADR per-agent-resource-scope](../../../docs/decisions/per-agent-resource-scope.md)). This is the same shape `mcp_server` uses, where scope alone decides which agents see a server's tools. The scope states:

- `None` — every registered agent receives the skill (the default for a fresh import).
- `{"agents": ["<agent uid>"]}` — only those agents receive it. The scope holds agent uids ([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md)); the web UI lets the user pick agents by name and stores their uids. A uid that matches no agent registered here is legal and simply never matches.
- `{"agents": []}` — nobody receives it, while the skill stays in the library, synced and visible.

Those two together are the skill's REACH, and reach is machine-local: it is set on the machine it applies to, it lives in this machine's reach record, so a sync round neither carries it away nor writes over it (spec vault-sync, "Keep reach machine-local"), and the predicate therefore takes no machine argument and has no machine to take. What travels is the skill — its master folder and its resource file in the vault — unless it is Coffer's own generated one (see "Regenerate Coffer's builtin skill from the build"). A skill can still be delivered here and dormant on another machine — that is two machines each holding their own `enabled` flag and their own scope, not one scope naming machines. The surface that sets reach MUST say that the setting stops at this machine.

No other flag decides which agents a skill is FOR: neither the delivery bookkeeping of "Track delivered copies as internal bookkeeping" nor any field on the agent resource; the agent resource carries no skill-delivery policy at all. `enabled` is a real switch: disabling a skill reclaims every delivered copy (master untouched) and re-enabling redelivers it to every agent its scope still grants. Scope is a hard grant: narrowing it to exclude an agent reclaims that delivery on the next reconcile even if the copy got there some other way, and widening it delivers; no per-agent state can hold a copy against the scope or keep one away from an agent the scope grants. A reconcile that finds a delivered copy the predicate no longer grants MUST reclaim it (remove the link, clear the delivery record) per "Reclaim a delivered copy without touching master", and MUST deliver a copy the predicate now grants but the agent does not hold. This predicate governs **delivery** — writing a skill into an agent's own filesystem — and is the only path by which a skill reaches an agent (see "Expose no skill tools over MCP").

#### Scenario: a skill with no scope reaches every registered agent
- **GIVEN** two registered agents and an enabled skill whose scope is unset (`None`),
- **WHEN** the delivery reconcile runs for each agent,
- **THEN** both agents hold a delivered copy, and registering a third agent delivers the skill there too with no further user action.

#### Scenario: a skill scoped to no agent reaches nobody
- **GIVEN** two registered agents each holding a delivered copy of an enabled skill,
- **WHEN** the user sets the skill's scope to `[]`,
- **THEN** both delivered copies are reclaimed, the skill remains in the library (still listed, still exported), and no agent receives it until its scope grants one again.

#### Scenario: disabling a skill reclaims every delivered copy
- **GIVEN** an enabled skill delivered to two agents,
- **WHEN** the user disables the skill resource,
- **THEN** both symlinks are removed and both delivery records are cleared, while the skill's scope and its master folder are unchanged.

#### Scenario: re-enabling a skill redelivers it
- **GIVEN** a disabled skill with no delivered copies and a scope granting two agents,
- **WHEN** the user re-enables the skill resource,
- **THEN** it is redelivered to both agents — links re-created, delivery records restored — with no per-agent action.

#### Scenario: scoping a skill away from an agent reclaims the delivered copy
- **GIVEN** an enabled skill currently delivered to an agent whose uid its scope includes,
- **WHEN** the user edits the skill's scope to exclude this agent and the next reconcile runs,
- **THEN** the delivered symlink is removed and the delivery record is cleared — scope is a hard grant, and no per-agent state can hold the copy against it.

### Requirement: Reconcile deliveries from state on every pass
The system MUST keep every agent's delivered set equal to the predicate of "Deliver a skill only where it is enabled and in scope" alone, as the skill-link target of the unified reconciler ([resource-framework](../resource-framework/spec.md) "Converge what Coffer writes outside its database with one reconciler"). An agent's wanted set is `{s.uid for s in skills if s.enabled and is_active(s.scope, agent.uid)}` — a free function over the agent alone, with no evaluator object to build and no machine to bind into one. The same skill row can still be wanted here and unwanted on another machine, because the `enabled` flag and the scope this predicate reads are this machine's own, and the round that brought the skill here brought neither. Each wanted delivery is a link at `<agent skill dir>/<skill name>` pointing at the skill's master folder, judged by both paths: a wanted skill the agent does not hold is delivered, a held copy no longer wanted is reclaimed, and a held link whose path no longer matches the agent's skill directory (its `config_dir` moved) is re-delivered at the new path and removed from the old one. Because the reconciler runs on every pass, this holds whatever changed the state — a skill enabled, disabled, rescoped, imported or removed, an agent registered or moved, a sync import, or nothing Coffer heard about — and a user's own write runs the pass for skills at once, so the change is visible when the write answers. An agent whose config does not parse is unknown, not an agent that wants nothing: its delivered links are left alone until the config reads again. Conflicts at target paths follow "Report a foreign target instead of overwriting it" (report, never overwrite). The agent resource carries no skill-delivery policy of any kind — no follow flag, no exclusion list, no per-agent opt-out; the only inputs are the skill's `enabled` flag and its `scope`.

#### Scenario: import delivers a skill only where its scope grants it
- **GIVEN** two registered agents, `claude_code` and `codex`,
- **WHEN** the user imports a skill whose scope names only the `claude_code` agent's uid,
- **THEN** the pass that follows delivers it to `claude_code` only, and `codex` receives nothing.

#### Scenario: an agent whose config cannot be read keeps its deliveries
- **GIVEN** an agent holding a delivered skill
- **WHEN** its config stops parsing and a pass runs
- **THEN** the link is left in place and nothing is reclaimed or reported

#### Scenario: moving an agent's config directory moves its deliveries
- **GIVEN** an agent holding a delivered skill, whose `config_dir` is then changed to another existing directory
- **WHEN** the change is saved
- **THEN** the skill is linked under the new directory's skills folder, the link under the old one is gone, and the move is recorded as a relink in the audit log

### Requirement: Cover skill management on REST and the web
Every management operation of a skill (import, update, remove, enable, disable, scope, verify) MUST be available through (a) the REST API and (b) the Skills page in the web UI; the command line carries no skill command. The REST routes are `GET /api/v1/skills` and `GET /api/v1/skills/{uid}` to read, the imports of "Import a skill from a local path", "Add skills from an archive" and "Add skills from a Git repository" (`POST /api/v1/skills/import` and `/stage/*`), the updates of "Update a Git-imported skill from its source" (`/api/v1/skills/{uid}/source/*`), `DELETE /api/v1/skills/{uid}`, the resource update route for `enabled` and `scope`, and `POST /skills/verify` for the drift report. Three repair operations are the web UI's and REST's alone: adopting or removing an orphan master folder (`/skills/orphans*`), resolving a copy an agent holds (`/skills/copies/{agent}/resolve`) and changing a Git-imported skill's source (`/skills/{name}/source/change`); the drift report names an orphan and what to do about it. `enable` and `disable` switch the skill resource's own `enabled` flag, which with its scope drives delivery ("Deliver a skill only where it is enabled and in scope"); there is no per-(skill, agent) switch on any surface, and the `POST /skills/{name}/enable` and `POST /skills/{name}/disable` routes do not exist. There is no edit operation: a skill's name is fixed, it has no title, and its description is its SKILL.md's, edited in the file.

A skill's master folder is plain files a person edits in their own editor. Its absolute path is shown on the skill's page (**Copy master path**) and in the REST file tree, and it is read and edited on disk; the command line carries no command that lists, prints or writes a file inside it. The REST file tree, file read and conditional file write ("Show a skill's master folder read-only", "Save an existing skill file conditionally") serve the web UI's Files tab and programmatic clients.

The Skills page is the library of managed skills beside the open skill: a list with search, an All / On / Off filter and row multi-select for bulk reach and bulk delete, next to the selected skill's detail. It has one **Add skill** action whose dialog offers three sources: **Folder** — a path field that takes a folder chosen with the folder picker or a path typed or pasted into it, trimmed of surrounding whitespace and quotes before it is sent; **Archive** — a `.zip` or `.skill` file uploaded from the browser; and **Git repository** — a URL with an optional ref and subpath; under the source, an **Available to** reach control whose choice every added skill takes (every agent unless narrowed). Each source first shows what it found — the skill or skills, their names and descriptions, any that cannot be added and why, and any whose name is taken, with Replace offered for those — and writes nothing until the user confirms. The dialog offers no way to create a new skill from scratch: a skill is authored in the user's own editor and added from where it lives. It shows each skill by its name, which it offers no way to edit. It lists only the skills Coffer manages: an agent's own (unmanaged) skills, and adopting them, live only on that agent's Skills tab (see "Expose unmanaged-skill operations on REST and the web"), and while no skill is managed the page's empty state may link to the agents' Skills tabs but lists nothing from them. It manages the skill resource itself, not per-agent bindings. A row carries a Built-in mark and an Off mark, and in place of its description the one thing that needs the reader, most urgent first: its master folder is gone ("Say when a skill's master folder is gone"), a folder is in the way of an agent's link ("Resolve a folder in the way of a skill's link"), a command it declares is missing, not logged in or too old, its Git source is unreachable, or an update is waiting ("Update a Git-imported skill from its source"). Folders in the skills store that no skill claims are listed apart, under **Not in your library** ("Act on a folder in the skills store that no skill claims"). A skill's detail (`/skills/<name>`, addressed by its fixed name as [web-ui](../web-ui/spec.md) "Lay out every detail page's tabs alike" says) shows its name, reach, a **⋯** menu — Open in editor, Reveal in Finder, Copy master path, Check agents' copies, Turn off, and Delete… (disabled on a builtin skill) — its description, and its master path or, for a Git skill, its repository, folder and pinned commit; above its tabs, a banner for each thing that needs the reader, with at most one action; and it has four tabs, in this order, each at its own path:

- **Files** (the default, `/skills/<name>`) — the file tree beside the viewer of "Show a skill's master folder read-only", opening with `SKILL.md` selected and rendered; a **Preview / Source** toggle switches a Markdown file between rendered and raw text, and **Edit** edits the file in place and saves it through "Save an existing skill file conditionally" (not offered on a builtin skill, which Coffer rewrites at every start). A text file offers **Open in editor**, a binary file **Open in default app** and **Reveal in Finder**, and a file too large to read whole shows its start read-only. A save refused because the file changed on disk keeps the edited text and offers Reload, Compare and Copy my text. There is no separate SKILL.md tab.
- **Delivery** (`/skills/<name>/delivery`) — every registered agent with the state of its copy: linked, copied where links are not allowed ("Fall back to copying where links are unavailable"), differing from master (the drift kinds of "Report skill drift on request" — a folder in the way offers **Review…**), or not delivered and why (the skill is off or the agent is outside its reach); **Check again** runs the drift report afresh.
- **Requires** (`/skills/<name>/requires`) — the commands the skill declares it needs ("Show the commands a skill declares it needs"), each with its state on this machine and opening that command's page on the CLIs page ([web-ui](../web-ui/spec.md) "Show every CLI a skill requires on the CLIs page"); the tab offers nothing that installs or logs in — those live on the CLIs page.
- **History** (`/skills/<name>/history`) — the master folder's versions from the vault's history ([vault-storage](../vault-storage/spec.md) "Show, compare and restore any version of a vault file"), newest first, each with who wrote it and when; choosing one shows the diff of every file it changed, and **Restore this version** asks first and then restores the whole folder as a new commit, removing files added since, with a refusal shown in its dialog. Coffer's own builtin skill is not in the vault and says it has no history.

A skill added from a Git repository also shows its source — the repository, the folder, the pinned commit and the update status — with **Check now** and **Change source…** ("Change a Git-imported skill's source").

The list's reach mark and the detail carry one reach button labelled with the answer ("All agents", the chosen agents' badges, "Off") that opens a panel whose choices are Off, All agents and Chosen agents — the last over the scope's list of agents, each switch and tick written at once. The list has no reach filter: each row shows its reach, and the list groups by state.

#### Scenario: the web UI and REST cover every operation
- **GIVEN** the daemon is running,
- **WHEN** the user performs each operation via the web UI and via the REST routes,
- **THEN** the same effect is achieved in either surface,
- **AND** the skill's page shows the absolute path of the same master folder the Files tab shows, and the command line offers no `skill` command at all.

#### Scenario: switch and scope a skill through the resource update route
- **GIVEN** two registered agents and an enabled skill with no scope, delivered to both
- **WHEN** the user sets the skill's scope to the first agent, then turns the skill off, then turns it on again, through the resource update route (the reach button on the Skills page)
- **THEN** after the scope change only the first agent holds a delivered link, after turning it off neither does, and after turning it on the first agent holds it again
- **AND** each change is recorded in the audit log

#### Scenario: the skills page lists only managed skills
- **GIVEN** one managed skill and an agent whose skills directory holds two hand-placed skill folders
- **WHEN** the user opens the Skills page
- **THEN** it lists the managed skill only, and offers no Adopt action and no row for either hand-placed folder
- **AND** with no managed skill at all, the empty state links to the agents' Skills tabs and lists no skill

#### Scenario: a skill opens on its files with SKILL.md rendered
- **GIVEN** an imported skill whose folder holds `SKILL.md` and a script
- **WHEN** the user opens its detail page
- **THEN** the tabs read Files, Delivery, Requires and History, Files is selected with `SKILL.md` selected and rendered, and there is no SKILL.md tab
- **AND** switching to Source shows the raw text, and Edit then saving writes the file through the conditional save

#### Scenario: the delivery tab shows each agent's copy
- **GIVEN** a skill scoped to one of two registered agents and delivered to it as a link
- **WHEN** the user opens the skill's Delivery tab
- **THEN** the first agent shows its copy as linked with its path, and the second as not delivered because it is outside the skill's reach

#### Scenario: the history tab says versions are not recorded yet
- **GIVEN** a skill whose master folder has no version in the vault's history yet
- **WHEN** the user opens its History tab
- **THEN** the tab says that no versions are recorded yet and what will appear there, and offers no restore

#### Scenario: the add dialog offers three sources and no create
- **GIVEN** the Skills page
- **WHEN** the user chooses Add skill
- **THEN** the dialog offers Folder, Archive and Git repository, and no option to create a new skill

#### Scenario: nothing is added until the user confirms
- **GIVEN** the Add skill dialog showing the skills found in an uploaded archive
- **WHEN** the user closes the dialog without confirming
- **THEN** no skill resource exists for them and nothing is under `~/.coffer/vault/skills/` for them
- **AND** the staging area the archive was read into is removed

#### Scenario: the history tab lists the folder's versions with their writers
- **GIVEN** a skill whose master folder has two versions, the newer written by the user and the older by Claude Code
- **WHEN** the user opens its History tab
- **THEN** the versions are listed newest first, each with its writer and how many files it changed
- **AND** the newest is marked current, shown with its diff, and offers no restore

#### Scenario: restoring a version asks first and restores the whole folder
- **GIVEN** a skill's History tab with an older version chosen
- **WHEN** the user chooses Restore this version and confirms
- **THEN** the dialog first says that files added since are removed
- **AND** once confirmed, the whole folder is restored from that version and the dialog closes

#### Scenario: Coffer's own skill has no history
- **GIVEN** the builtin `coffer-guide` skill
- **WHEN** the user opens its History tab
- **THEN** the tab says Coffer's own skill has no history and reads none

### Requirement: Report per agent whether a reach change was delivered
`PUT /api/v1/resources/{uid}/scope` for a skill MUST answer, beside the resource, `delivery`: one row per registered agent the new reach grants (and per agent a failed or blocked write names), each with `agent_uid`, `agent_name`, `ok` and, when it is not ok, the `reason` the link was not made. The reach is saved whether or not every delivery succeeded, so the page can say which agent was saved and which could not be linked. Kinds that deliver nothing answer `delivery: null`.

#### Scenario: a reach change reports delivery per agent
- **GIVEN** a skill and two agents, one of which already holds a real folder where the skill's link would go
- **WHEN** the skill's reach is set to every agent
- **THEN** the response's `delivery` lists the first agent ok and the second not ok with a reason, and a scope write on an agent answers `delivery: null`

### Requirement: Act on an unmanaged skill from its detail page
The agent's Skills tab MUST open an unmanaged skill's detail page when its row is clicked. The page's header carries the skill's name with an Unmanaged badge, a line naming whose skill it is, where it lives and how many files it has, **Adopt** as its one button ("Adopt an unmanaged skill into the master store"; left out for an invalid folder or a foreign link, whose reason shows first), and a ⋯ menu whose only item is **Delete…** ("Delete an unmanaged skill on explicit request", confirmed first). Below it are two tabs, **Overview** — the properties: description, folder, where it was found, its files — and **Files**, the folder's tree beside a read-only viewer in the shared file tree and viewer toolbar. There is no Open folder action beside the header, because the files are shown here; opening a file in an editor or revealing it is on the viewer. A successful delete MUST return to the agent's Skills tab.

#### Scenario: open an unmanaged skill's detail page from the agent's Skills tab
- **GIVEN** an agent's Skills tab listing unmanaged skills
- **WHEN** the user clicks one row
- **THEN** that skill's detail page opens, and its Files tab shows the folder's tree and a read-only preview of the chosen file
- **AND** no row in the list carries an Open folder button

#### Scenario: adopt or delete an unmanaged skill from its detail page
- **GIVEN** an unmanaged skill's detail page
- **WHEN** the user chooses Adopt
- **THEN** the Adopt form for that folder opens
- **AND** when the user instead deletes it from the ⋯ menu and confirms, the folder is deleted and the page returns to the agent's Skills tab

## ADDED Requirements

### Requirement: Adopt an unmanaged skill into the master store
Users MUST be able to adopt a valid unmanaged skill. Adoption validates the folder per "Validate imported skill folders against AgentSkills", moves it to `~/.coffer/vault/skills/<name>/`, registers the `skill` resource, delivers the managed link (see "Deliver a skill as a directory link"), and records an enabled binding for that agent — in that order, with any failure before registration leaving the original folder unmoved and unchanged (after registration the master copy is authoritative; a delivery failure is surfaced and retried via the binding, never rolled back). The managed link is always delivered to the agent's canonical delivery location `<config_dir>/skills/<name>`: adopting from `<config_dir>/skills` replaces the original path in place, while adopting from `~/.agents/skills` consolidates — the original folder there is removed and the link lands in `<config_dir>/skills` (Codex reads both locations, so the agent keeps seeing the skill). Name collisions MUST be rejected with `conflict` (409); invalid folders and symlinks pointing outside the master store MUST be rejected with `unprocessable_entity` (422). Adoption is audited as an adoption event.

The adoption MAY name the skill and its reach. A `name` registers the skill under that name instead of the one its SKILL.md front matter carries: the master copy's `name:` line is rewritten, no other line is, and the original folder is untouched until the adoption has succeeded. A `reach` is one of every agent (the default), only the listed agents, or off — the skill is adopted switched off — which becomes the skill's `enabled` flag and `scope` ([resource-framework](../resource-framework/spec.md) "Carry a per-agent reach on every resource"); a request that names neither behaves as before. On the web, Adopt opens a form with exactly these two — **Name in Coffer**, checked against the library as it is typed, and **Reach** — and shows an error inside the form.

#### Scenario: adopt an unmanaged skill into the master store
- **GIVEN** an unmanaged skill folder with a valid SKILL.md whose name collides with no master skill,
- **WHEN** the user adopts it,
- **THEN** Coffer validates it per "Validate imported skill folders against AgentSkills", moves the folder to `~/.coffer/vault/skills/<name>/`, registers the `skill` resource, replaces the original path with the managed link, records a binding for that agent, and audits the adoption — and on any failure the original folder is left exactly where and as it was.

#### Scenario: adopt an unmanaged skill under another name and a narrower reach
- **GIVEN** an unmanaged skill `loose` that Claude Code holds
- **WHEN** the user adopts it as `notes` reaching only Codex
- **THEN** the managed skill is named `notes`, its master SKILL.md carries `name: notes` with every other line unchanged, and its scope names Codex alone
- **AND** adopting it switched off leaves the skill registered and disabled

#### Scenario: reject adopting an invalid or conflicting unmanaged skill
- **GIVEN** an unmanaged entry that lacks a valid SKILL.md, collides with an existing master skill's name, or is a symlink pointing outside the master store,
- **WHEN** the user attempts to adopt it,
- **THEN** the request is rejected with a reason-specific error (invalid: `unprocessable_entity` 422; name conflict: `conflict` 409; foreign link: `unprocessable_entity` 422), and nothing is moved, registered, or linked.
