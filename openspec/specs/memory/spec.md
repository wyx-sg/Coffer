# Memory

## Purpose

Every agent the developer runs keeps its own memory, and none of them can see any of the others'. Claude Code accrues per-fact notes per project; Codex consolidates its rollouts into a summary of topics. Both work well and neither leaves its own directory, so the developer re-teaches each agent what the other already knows, and re-teaches it again on the next machine. Coffer **syncs those memories into each other**: it reads what every registered agent wrote for itself, keeps one copy of each memory in a **hub** in the vault, and writes the hub back into **each agent's own native memory**, where that agent already looks for it.

```
~/.coffer/vault/memory/
└── projects/<project key>/  ← one folder per repository, the same key on every machine
```

**Only project memories are synced.** A memory an agent learned in a repository is filed under that repository's project; one learned outside any repository (Codex's profile and preferences, a scratch directory, a session with no working directory) stays with its own agent and is not synced, and Coffer's own vault is no project. From Codex, Coffer reads the topics of its consolidated summary; the working notes Codex keeps per task in its older `MEMORY.md` are not memories to carry and are not read.

**The hub is vault content.** Vault sync carries it to the person's other machines, so a memory one agent learned on one machine reaches every agent on every machine. A project is named by its repository's normalised `origin`, and the paths in a memory are stored portably, so a memory written in one checkout reads true in another.

**Each agent reads the copies the way it reads its own memory.** For Claude Code that is text it loads by itself: the memories of a project in a marked block of that project's `MEMORY.md`; Claude Code opens a memory's own file only when its model chooses to, which in practice it does not, so Coffer writes no file per memory there. For Codex it is a memory extension folder, which Codex's consolidation absorbs. Coffer delivers nothing into a session itself: no hook, no index at session start, no retrieval at prompt time.

**Coffer does the mechanical work and nothing else.** It publishes, writes and removes copies; it never merges, rewords or judges a memory, and it never touches a memory an agent wrote. Judgement stays with each agent's own curation (Codex consolidation, Claude Code's Auto Dream), which now sees the other agents' memories beside its own; a copy the agent edited or removed is the agent's, and is not written again. Coffer neither shows nor switches nor starts an agent's curation: that is the agent's own setting, and the person's to change in the agent.

**Memory is about the person; knowledge is about the world.** Memory holds who the person is, how to work with them, and a project's current state. [Knowledge](../knowledge/spec.md) holds how outside systems, teams and processes work: what needs a source, goes stale or is worth sharing. A fixed sequence of steps is a [skill](../skill-manager/spec.md). What an agent learned about an outside system belongs in knowledge; moving it there is the person's and their agent's business.

| | Memory | Knowledge |
| --- | --- | --- |
| Holds | the person, how to work with them, a project's state | outside systems, teams, processes, their pitfalls |
| Where it comes from | agents' native memories | the human uploads it, or writes it with an agent |
| Partitioned by | project | collection |
| Who authors the stored text | the agent that learned it; Coffer copies it as it stands | the human or an agent, directly |
| Reaches an agent by | **push**: text or a copy in the agent's own memory | **pull**: the agent reaches for it |
| Tidied by | each agent's own curation | an agent on request (Tidy) |

The first sync on a machine, and any sync that would change more than 50 copies, waits as a **preview** the person writes or cancels, and **Undo sync** removes every copy Coffer wrote that the agent has not edited. The page and the `coffer memory` commands manage the sync; neither reads or writes a memory's text.

While the `memory` feature is switched off (spec [experimental-features](../experimental-features/spec.md)), the memory routes are closed and the memory sync skips its rounds; the copies already written stay in the agents' own memory.

## Requirements

### Requirement: Read no transcripts or rollouts
A sync MUST NOT read session transcripts, rollouts or raw capture files **as a source of entries**. Both supported agents already distil their own; this layer starts from that output. The single narrow exception is Claude Code's project slug, which encodes a path lossily: the reader MAY scan a project's own session transcripts for the `cwd` they recorded, accepting it only when Claude Code's encoding of that `cwd` is exactly the slug, so that a renamed or deleted project still files under its real repository. Codex's v2 memory files its topics under named scopes and records each one's directory only in the header of the rollout summary the topic points at: the reader MAY read that header's `cwd:` line and nothing below it. Nothing but those recorded paths is taken, and no transcript or rollout summary is ever listed as a source.

#### Scenario: list no transcript or rollout as a source
- **GIVEN** a Claude Code config directory holding a session transcript beside a project's memory directory, and a Codex home holding session rollouts beside its memory files
- **WHEN** each reader lists its sources
- **THEN** no transcript, rollout or raw capture file is among them

### Requirement: Read Claude Code and Codex memory
Coffer MUST support two readers. **Claude Code**: per-fact Markdown files under its per-project memory directories, whose frontmatter carries the entry's name, description and type. **Codex**: the topics of its consolidated summary (see "Read Codex's memory from its v2 summary"). Each reader MUST ignore the agent's own index or roll-up file, which only restates the entries.

#### Scenario: a Claude Code memory file becomes a raw entry
- **GIVEN** a Claude Code per-project memory directory holding one fact file whose frontmatter carries `name`, `description` and `type`
- **WHEN** the Claude Code reader lists its sources and reads that one
- **THEN** exactly one raw entry comes back: its title is the `name`, its description the `description`, its type `feedback`, its body the prose with the frontmatter fence stripped out, its anchor the file's own stem, and its project root the project that memory directory belongs to
- **AND** the agent's own roll-up file (`MEMORY.md`) is not among the sources at all

### Requirement: Fail a broken reader loudly and in isolation
A reader that cannot parse its source — the agent changed its format — MUST fail **loudly and in isolation**: that agent contributes nothing to the hub in that sync, the Memory page says so with the path and the reason, the other agent's memory is still read, and hub entries it published earlier are left standing rather than deleted. A writer that does not recognise the layout it is about to write into (Claude Code's memory directory, or Codex's memory folder without the extension layout Coffer expects) MUST write nothing for that agent and report it the same way.

#### Scenario: an agent whose native memory shape is unreadable degrades loudly
- **GIVEN** one agent holding a memory file whose frontmatter is missing, unterminated, not a mapping, or missing its name field, and a second agent whose memory is fine
- **WHEN** memory syncs
- **THEN** the sync reports one failure naming the agent, the path and the reason
- **AND** the other agent's memories are published as normal, and the first agent's earlier hub entries are left standing

#### Scenario: an unrecognised layout is not written into
- **GIVEN** a Codex memory folder whose layout Coffer does not recognise
- **WHEN** memory syncs
- **THEN** nothing is written under it and the Memory page names the path and the reason

### Requirement: Skip unchanged sources
A sync MUST skip a source file whose content hash is unchanged since the last sync, and MUST record enough per source to make that decision without re-parsing.

#### Scenario: an unchanged source file is skipped on the next sync
- **GIVEN** a source already read by one sync, whose content hash has not changed since
- **WHEN** a second sync runs
- **THEN** the source is counted as skipped and is **not read at all** — a reader rigged to raise if consulted again is never consulted
- **AND** no failure is reported and the hub entries that source produced stay

### Requirement: Show memory events on the vault-wide audit surface
This layer MUST NOT carry an audit surface of its own. Its events are read on the vault-wide audit surface, and every event type this layer records MUST be legible there rather than shown as a raw event code.

#### Scenario: label every memory event type on the audit surface
- **GIVEN** every audit event type the memory layer records
- **WHEN** each is rendered by the vault-wide audit surface's event labelling
- **THEN** each has a human-readable label in both interface languages rather than its raw event code

### Requirement: Confine reads to registered agents' memory paths
Reading and writing MUST be confined to the memory paths of registered agents' config directories and to `vault/memory/`. Every path built from a source's contents or a hub entry MUST pass a traversal guard.

#### Scenario: refuse a path segment built from source contents that escapes
- **GIVEN** a project key, slug or source identity taken from a source's or hub entry's contents that is `..`, contains a path separator, or is hidden
- **WHEN** a path under the hub or an agent's memory directory is built from it
- **THEN** it is refused with `UnsafeMemoryPath` rather than resolved outside it

### Requirement: Read only registered agents' memory
Coffer MUST read the native memory of each **registered** agent, from a path derived from that agent's own `config_dir` ([agent-registry](../agent-registry/spec.md)). An agent that is not registered MUST NOT be read.

#### Scenario: read nothing from an unregistered agent
- **GIVEN** fixture memory for a registered agent and in a config directory no registered agent names
- **WHEN** memory syncs
- **THEN** hub entries come only from the registered agent's memory
- **AND** nothing is read from the unregistered directory

### Requirement: Keep every agent's memories in a hub in the vault
Coffer MUST keep every memory that a registered agent on any of the person's machines wrote for itself in a repository as one Markdown file in the vault, under `vault/memory/projects/<project>/`. Each file MUST carry frontmatter naming its origin (machine id, agent type and the source's own identity), its `type` (`user`, `feedback`, `project` or `reference`), its `title`, a one-line `description`, `created_at` and `updated_at`, and the memory's text as its body. A memory MUST be filed where its agent filed it, whatever its type: one learned in a repository under that repository's project. A memory learned outside any repository (a scratch directory, a Codex topic whose rollout summary records no repository) MUST NOT be published. The hub is vault content, so vault sync carries it to the person's other machines like any other vault file ([vault-sync](../vault-sync/spec.md)).

#### Scenario: an agent's memory becomes one hub file
- **GIVEN** a registered Claude Code with one `feedback` memory file in the memory directory of a checkout of `github.com/acme/payments`
- **WHEN** memory syncs
- **THEN** exactly one file appears under `vault/memory/projects/github.com-acme-payments/`, whose frontmatter names this machine, `claude_code`, the source file, the type `feedback`, its title and description, and whose body is the memory's text
- **AND** the change is one vault commit naming the memory sync as its writer

#### Scenario: only a memory learned in a repository is published
- **GIVEN** a Claude Code memory typed `user` learned in a directory inside no repository, and a Claude Code memory typed `user` learned in a checkout of `github.com/acme/payments`
- **WHEN** memory syncs
- **THEN** only the memory learned in the checkout is published, under that project

#### Scenario: the hub travels with vault sync
- **GIVEN** two machines syncing one vault, and a hub entry published on the first
- **WHEN** a sync round completes on the second
- **THEN** the second machine holds the same hub file

### Requirement: Identify a project by a key that does not depend on the machine
A project in the hub MUST be named by its repository's `origin` URL, normalised (scheme, credentials and a trailing `.git` dropped, lower-cased host), and by the repository directory's name when it has no `origin`. A main checkout, its worktrees and another clone with the same `origin` MUST resolve to one project, on one machine or across machines. A memory whose agent names several working directories MUST be filed under the first of them inside a repository. A memory learned only in directories that are not inside a repository MUST NOT be published.

#### Scenario: two clones on two machines share one project
- **GIVEN** a checkout of `git@github.com:acme/payments.git` at `/Users/a/src/payments` on one machine and of `https://github.com/acme/payments` at `/home/b/work/pay` on another
- **WHEN** each machine publishes a memory learned in its checkout
- **THEN** both land under one project, `github.com-acme-payments`

#### Scenario: a memory from a scratch directory is not published
- **GIVEN** a `project` memory learned in a directory that is not inside a repository
- **WHEN** memory syncs
- **THEN** no hub file is written for it

### Requirement: Store paths in a memory portably
When a memory is published, every occurrence of its repository's local root in its text MUST be replaced by `<repo>` and every occurrence of the person's home directory by `~`. When a hub entry is written into an agent, `<repo>` MUST be expanded to that project's checkout on the writing machine and `~` to that machine's home directory. Any other path MUST be left as written.

#### Scenario: a path follows the repository to another machine
- **GIVEN** a memory published from a checkout at `/Users/a/src/payments` whose text names `/Users/a/src/payments/ledger/retry.py` and `/Users/a/.config/tool.toml`
- **WHEN** it is written on a machine where the project is checked out at `/home/b/work/pay` and the home directory is `/home/b`
- **THEN** the copy names `/home/b/work/pay/ledger/retry.py` and `/home/b/.config/tool.toml`
- **AND** the hub file names `<repo>/ledger/retry.py` and `~/.config/tool.toml`

### Requirement: Publish only what the origin agent wrote, and only from its machine
Each sync MUST read the registered agents' native memory, create or update the hub entry for each memory the agent wrote itself, and delete the hub entry of a memory the agent no longer holds. A memory the agent still holds whose repository is no longer on this machine MUST keep its hub entry: another machine may still have the project. Only the machine and agent a hub entry came from MUST change or delete it; a machine MUST NOT delete another machine's entry because its own agents lack that memory.

#### Scenario: a memory the agent changed updates its hub entry
- **GIVEN** a published Claude Code memory whose file the agent rewrote
- **WHEN** memory syncs on the same machine
- **THEN** the hub entry's body and `updated_at` change and no new hub entry is created

#### Scenario: a memory the agent dropped leaves the hub
- **GIVEN** a published Claude Code memory whose file the person deleted
- **WHEN** memory syncs on the same machine
- **THEN** its hub entry is deleted

#### Scenario: a memory whose repository is gone from this machine stays in the hub
- **GIVEN** a published Claude Code memory whose repository was since deleted from this machine, and whose file the agent then changed
- **WHEN** memory syncs on the same machine
- **THEN** its hub entry is still there, unchanged

#### Scenario: another machine's entry is left alone
- **GIVEN** a hub entry published by another machine, and no agent on this machine holding that memory
- **WHEN** memory syncs on this machine
- **THEN** the hub entry is unchanged

### Requirement: Withhold a memory that looks like a secret
A memory whose text holds something shaped like a secret (an API key, a token, a private key or a password assignment, by the same shapes the secret boundary detects) MUST NOT be published to the hub. The sync report MUST name the agent and source it withheld, never the matched text.

#### Scenario: a memory holding a token is withheld
- **GIVEN** a Claude Code memory whose body contains an `sk-` API key
- **WHEN** memory syncs
- **THEN** no hub entry is written for it, and the sync's Activity entry lists it as withheld by agent and source path only

### Requirement: Write the hub into Claude Code as text it loads
Coffer MUST write each hub entry that did not come from this machine's Claude Code into Claude Code as text Claude Code loads by itself, and MUST NOT write a file per memory. A project's entries MUST go, for each project checked out on this machine, into a marked block at the end of that project's `MEMORY.md` (in `<config_dir>/projects/<project>/memory/`, created when missing, named the way Claude Code names it for the repository's root), between `<!-- coffer:memory-sync:begin -->` and `<!-- coffer:memory-sync:end -->`, so they load only in sessions in that project. Each memory MUST be one line holding its text (its title in front when the text does not open with it, at most 800 characters) and the agent it came from, the newest memory first. The block MUST stay within 4 KB; memories that do not fit MUST be counted in a last line naming the `coffer memory entries` command that lists them. Coffer MUST back `MEMORY.md` up before changing it and MUST NOT change anything in it outside the marked block.

#### Scenario: a project's memories reach only that project
- **GIVEN** a hub entry from Codex for `github.com-acme-payments`, that repository checked out with Claude Code registered, and another checked-out project
- **WHEN** memory syncs
- **THEN** the marked block of the payments project's `MEMORY.md` holds the memory's text, the other project's `MEMORY.md` does not
- **AND** every line of `MEMORY.md` outside the block is byte-identical to before, a backup of the previous `MEMORY.md` exists, and no file per memory is written

#### Scenario: the marked block is bounded
- **GIVEN** 45 memories of 250 characters for one project
- **WHEN** the marked block is rendered
- **THEN** it holds the newest of them within 4 KB, then one line counting the rest and naming `coffer memory entries --project github.com/acme/payments`

### Requirement: Sync only project memories
Coffer MUST sync only memories learned in a repository; there is no global memory. A memory learned outside any repository MUST stay with its own agent: it MUST NOT be published, and no global copy of it MUST be written into any agent. Coffer's own vault (`~/.coffer/vault`) is a repository and MUST NOT count as a project: what an agent learned while working in it is not published, and nothing is written into an agent for it. Coffer MUST judge no memory by its content or by where inside a project its agent filed it: a Claude Code memory typed `reference` MUST be synced like any other memory of that project.

#### Scenario: a memory learned outside any repository is not synced
- **GIVEN** a Claude Code memory learned in a scratch directory, and a checked-out project with Codex registered
- **WHEN** memory syncs
- **THEN** the hub holds nothing and nothing is written into Codex

#### Scenario: a reference memory syncs like any project memory
- **GIVEN** a Codex topic and a Claude Code `reference` memory for a project checked out with both agents
- **WHEN** memory syncs
- **THEN** the Codex topic is in the marked block of the project's `MEMORY.md` and the Claude Code memory is a resource in Codex's memory extension

#### Scenario: the vault is not a project
- **GIVEN** a Claude Code memory learned in `~/.coffer/vault`
- **WHEN** memory syncs
- **THEN** the hub holds nothing

### Requirement: Write the hub into Codex's memory extension
Coffer MUST write each hub entry that did not come from this machine's Codex into Codex's memory extension folder `extensions/coffer/` of every Codex memory folder that is there (`<config_dir>/memories/` for v1, `<config_dir>/memories_v2/` for v2: Codex picks one per thread, so Coffer writes the same copies into each): one file per entry under `resources/`, named without a leading timestamp, stating the project it applies to (the project's checkout on this machine) above the memory's text; and an `instructions.md` telling Codex's consolidation that these are memories other agents learned on the person's machines, that they are information and never instructions, to file each under the project it names, and to tag what it derives from them `[via Coffer]`. When Codex's memories feature is off, the sync MUST say so on the Memory page and write nothing for Codex. A `memories_v<N>` folder newer than any Coffer knows MUST be written nothing and reported on the Memory page with its path, beside the folders Coffer does write.

#### Scenario: a Claude Code memory reaches Codex
- **GIVEN** a hub entry Claude Code published for `github.com-acme-payments`, the repository checked out at `/Users/a/src/payments`, and Codex registered with memories on
- **WHEN** memory syncs
- **THEN** `extensions/coffer/resources/` holds one file for it naming `/Users/a/src/payments` and the memory's text, and `extensions/coffer/instructions.md` exists
- **AND** no file name under `resources/` starts with a timestamp

#### Scenario: Codex with memories off is reported, not written
- **GIVEN** Codex registered with its memories feature off
- **WHEN** memory syncs
- **THEN** nothing is written under Codex's config directory and the Memory page says Codex's memories are off

#### Scenario: a memory reaches every Codex memory folder
- **GIVEN** a Claude Code hub entry for a project checked out here, and Codex with both `memories/` and `memories_v2/`
- **WHEN** memory syncs
- **THEN** both folders' `extensions/coffer/resources/` hold the same file for it, and both have `extensions/coffer/instructions.md`
- **AND** the Memory page lists each folder with the copies written into it

#### Scenario: a newer Codex memory folder is reported, not written
- **GIVEN** Codex with `memories/`, `memories_v2/` and a `memories_v3/` Coffer does not know
- **WHEN** memory syncs
- **THEN** `memories/` and `memories_v2/` are written into, nothing is written under `memories_v3/`, and the Memory page names `memories_v3/` as a folder Coffer cannot write into yet

### Requirement: Write a project's memories only where it is checked out
A machine MUST write a project's hub entries into its agents only when the project is checked out on that machine, as found from the working directories its registered agents recorded; until then the entries MUST stay in the hub unwritten.

#### Scenario: a project not checked out here is held back
- **GIVEN** hub entries for a project no registered agent on this machine has worked in
- **WHEN** memory syncs
- **THEN** none of them is written into any agent here
- **AND** once a registered agent records a working directory in that project, the next sync writes them

### Requirement: Never write a memory back into the agent and machine it came from
A hub entry MUST NOT be written into the agent it came from on the machine it came from. It MUST be written into that same agent type on the person's other machines.

#### Scenario: a memory returns to its own agent on another machine only
- **GIVEN** a hub entry published by Claude Code on machine A
- **WHEN** memory syncs on machine A and on machine B
- **THEN** machine A writes it into Codex only, and machine B writes it into both Claude Code (the project's marked block) and Codex

### Requirement: Never republish Coffer's own copies
What Coffer wrote MUST NOT become a hub entry when its agent's memory is read back: on Claude Code the marked block sits in `MEMORY.md`, which is never read as a memory; on Codex the extension folder is never listed, and a topic Codex derived from it and tagged `[via Coffer]` is skipped. When an agent's own memory changes only by text already covered by what Coffer delivered to that agent, Coffer MUST record the new text against the hub entry without publishing a change, so an agent's rewording of what it absorbed does not circulate.

#### Scenario: a copy read back is not published
- **GIVEN** Coffer's marked block in a Claude Code project's `MEMORY.md`, and a Codex topic tagged `[via Coffer]`
- **WHEN** memory syncs
- **THEN** neither produces a hub entry

#### Scenario: an absorbed copy does not circulate
- **GIVEN** Claude Code's own memory gained, in one of its own files, only a sentence Coffer had written into its project's block from a Codex hub entry
- **WHEN** memory syncs
- **THEN** no hub entry is created or changed for that addition

### Requirement: Leave every memory an agent wrote untouched
Coffer MUST NOT create, change, move or delete any file in an agent's memory other than its own copies, the marked block in Claude Code's `MEMORY.md` and its Codex extension folder, and MUST NOT change an agent's memory settings. Merging, correcting and forgetting are the agent's own curation.

#### Scenario: an agent's own files are byte-identical after a sync
- **GIVEN** both agents' memory directories snapshotted with their modification times, and hub entries to write into each
- **WHEN** memory syncs
- **THEN** every file the agent wrote itself is byte-identical with an unchanged modification time, and the only differences are Coffer's own copies, the marked block and the extension folder

### Requirement: Hand an edited or removed copy to the agent
A copy whose content no longer matches what Coffer last wrote MUST NOT be overwritten, and a copy the agent removed MUST NOT be recreated, for as long as its hub entry is unchanged. When the hub entry changes, Coffer MUST write the new version as a new copy rather than over the agent's edit. Removing a copy MUST NOT delete its hub entry.

#### Scenario: a copy Auto Dream merged away is not brought back
- **GIVEN** a copy in Codex's extension folder that Codex's own curation absorbed and deleted
- **WHEN** memory syncs and the hub entry has not changed
- **THEN** the copy is not recreated and the hub entry stays

#### Scenario: a copy the agent edited is not overwritten
- **GIVEN** a copy in Codex's extension folder whose body the agent edited
- **WHEN** memory syncs
- **THEN** the file keeps the agent's edit

### Requirement: Defer to Codex's own import from Claude Code
When Codex's own import from Claude Code is on with automatic updates on this machine, Coffer MUST NOT write Claude Code's memories into Codex on that machine, and Codex's Memory tab MUST say that Codex imports them itself. The other direction MUST continue.

#### Scenario: Codex's own import turns the Claude Code to Codex direction off
- **GIVEN** Codex's import from Claude Code on with automatic updates, and a hub entry from Claude Code
- **WHEN** memory syncs
- **THEN** no resource is written for it in Codex's extension folder, and Codex's Memory tab says Codex imports Claude Code's memories itself

### Requirement: Preview a first or large sync
The first sync on a machine, and any sync that would write more copies than a threshold (50 by default), MUST NOT write into any agent until the person confirms it on the Memory page, which lists per agent and project how many copies would be written, updated and removed, folded to those counts until opened (a group that removes anything starts open), and opened lists each memory with what the sync would do to its copy; a memory it would write or update opens in the memory drawer. Publishing to the hub MUST proceed without waiting.

#### Scenario: the first sync waits for the person
- **GIVEN** a machine that has never synced memory, with memories to write into both agents
- **WHEN** memory syncs
- **THEN** the hub is updated, nothing is written into either agent, and the Memory page counts the preview among what needs the person; its drawer lists each agent and project with its counts and, opened, each memory, with **Write** and **Cancel**
- **AND** choosing **Write** writes exactly what the preview listed

### Requirement: Sync on an interval and on demand
Memory sync MUST run on a background worker at daemon start and then on an interval (one hour by default), and MUST be runnable by hand with **Sync now** on the Memory page. Its switch and interval MUST be settable and read per pass ([internal-engine](../internal-engine/spec.md) "Apply a changed switch or interval without a restart"). Only one sync MUST run at a time; a request while one runs MUST be answered as already running. A sync MUST skip a source whose content hash is unchanged (see "Skip unchanged sources").

#### Scenario: a sync runs at start and on demand
- **GIVEN** the memory sync worker configured with an interval
- **WHEN** the daemon starts, and later the person chooses **Sync now** while no sync runs
- **THEN** one sync runs at start under the worker's actor and one under the person's
- **AND** choosing **Sync now** again while it runs reports that a sync is already running

### Requirement: Record every sync in Activity
Every sync that changed anything MUST record one `memory_synced` audit event with its actor, listing the hub entries published, updated and deleted, the copies written, updated and removed per agent and file path, the memories withheld, and every source it could not read. A sync that changed nothing MUST NOT record an event.

#### Scenario: a sync lists what it wrote
- **GIVEN** a sync that publishes one memory and writes two copies
- **WHEN** it finishes
- **THEN** one `memory_synced` event lists the hub entry and both copy paths, and Activity renders it

### Requirement: Undo sync
**Undo sync…** on the Memory page MUST, after a confirmation naming what it removes, delete every copy Coffer wrote on this machine that the agent has not changed, the marked block from each `MEMORY.md` and the Codex extension folder, turn automatic sync off, and record a `memory_sync_undone` event. It MUST NOT delete hub entries or anything an agent wrote itself.

#### Scenario: undo removes Coffer's copies and nothing else
- **GIVEN** two copies written into Codex, one of which Codex edited, and a block written into a Claude Code project's `MEMORY.md`
- **WHEN** the person confirms **Undo sync…**
- **THEN** the unedited copy and the marked block are gone, the edited copy remains, the agent's own files and the hub are unchanged and automatic sync is off

### Requirement: Show on each agent what Coffer wrote into it
Each registered agent's Memory tab MUST show, while the memory feature is on, the copies Coffer wrote into it on this machine (and how many the agent has since edited or removed), or why Coffer cannot write into it; for Codex, one line per memory folder. The Memory page MUST NOT list the agents; it MUST count an agent Coffer cannot write into among what needs the person, linking to that agent's Memory tab. Coffer MUST NOT show, change or start an agent's own curation (Claude Code's Auto Dream, Codex's consolidation): it reads no setting or cache of the agent for it and writes none.

#### Scenario: an agent's tab shows what Coffer wrote into it
- **GIVEN** Codex with memories on holding two copies Coffer wrote, and Claude Code holding Coffer's block
- **WHEN** the person opens each agent's Memory tab
- **THEN** Codex's says two copies were written, and Claude Code's says its memories arrive as text
- **AND** neither offers to curate or to turn curation on, and the Memory page shows no row or chip per agent

### Requirement: Deliver no memory into a session
Coffer MUST NOT put memory into an agent's session itself: no session-start context, no notes added to a prompt, and nothing added to a channel turn's system prompt or message. An agent reaches memory only through its own native memory.

#### Scenario: a channel turn carries no memory from Coffer
- **GIVEN** hub entries for the conversation's project and a channel turn about it
- **WHEN** the turn is composed
- **THEN** its system prompt and the message the agent receives carry nothing from the memory layer

### Requirement: Manage memory sync in the web UI and on the command line
The Memory page MUST show the sync switch and interval, **Sync now**, when memory last synced and the next sync, **Undo sync…**, and one banner counting what needs the person — a pending preview, each source the last sync could not read, each memory it withheld, each agent Coffer cannot write into — whose drawer lists them. Below, it MUST list the hub's projects by short name with how many memories each holds, the ones not checked out on this machine grouped apart — beside the open project's memories (`/memory?scope=`), each with its title and description, type, origin agent and machine and last change, filterable by text and origin agent (`?source=`). A memory's copy state MUST show on its row only when it waits for the next sync, the agent's curation edited or removed it, or it did not fit in Claude Code's block (the state `over_limit`). Opening a memory (`&memory=<id>`) MUST show, in the shared drawer, first one line per local agent with its copy's state, the file that holds it and Open / Reveal, then the memory's text, read only. The page MUST NOT offer to edit a memory's text: the person edits memory in the agent's own memory directory. The old address `/memory/projects/<folder>` MUST open that project, and `/memory/global` the page. Every operation of the page MUST also be a `coffer memory` command.

#### Scenario: a project's memories show where each was written
- **GIVEN** a project with two hub entries, one written into Claude Code and one whose copy Claude Code's curation removed
- **WHEN** the person opens the project on the Memory page
- **THEN** each memory shows its origin agent and machine, the first says nothing about its copy and the second reads removed by Claude Code

#### Scenario: a memory left out of a full block says so
- **GIVEN** a project with more Codex memories than fit in Claude Code's 4 KB block
- **WHEN** the project's memories are listed
- **THEN** the newest read `block` for Claude Code and the ones left out read `over_limit`

#### Scenario: a memory opens with its text and where each agent holds it
- **GIVEN** a Claude Code memory written into Codex
- **WHEN** the person opens it
- **THEN** the drawer lists Claude Code with its own file and Codex as written with the copy's file, each with Open and Reveal, above the memory's text
- **AND** an id the hub does not hold answers not found

#### Scenario: memory sync is managed on the command line
- **GIVEN** the `coffer memory` command group
- **WHEN** its commands are listed
- **THEN** they are `state`, `sync`, `preview-write`, `preview-cancel`, `undo`, `codex-import`, `entries` and `show`, one per operation of the pages, `show` reads one memory's text and none writes it

### Requirement: Audit every sync and undo
Every sync that changed something and every undo MUST record an audit event with its actor. An agent's own change to its memory is not a Coffer act and is not audited.

#### Scenario: audit a requested sync with its actor
- **GIVEN** a registered agent with native memory to publish
- **WHEN** a user chooses **Sync now**
- **THEN** exactly one `memory_synced` event names that user as its actor, beside any the daemon's own worker recorded under its own actor

### Requirement: Add no table or resource kind
This layer MUST add **no table of its own** and no resource kind. The hub is files in the vault; what a machine wrote into its agents is recorded in one machine-local file, `local/memory-sync.json`.

#### Scenario: keep the hub and the ledger as files only
- **GIVEN** a history database upgraded to head
- **WHEN** its tables are listed after a sync that published and wrote memories
- **THEN** no table is named for memory, no resource of kind `memory` exists, and the ledger is `local/memory-sync.json`

### Requirement: Reintroduce no retired memory mechanism
This layer MUST NOT reintroduce transcript distillation, a Coffer-run model over memory, native-memory projection (taking over an agent's memory directory or switching its own memory off), Coffer's own notes, or any delivery of memory into a session. The two readers and two writers are written as two each; a third agent earns an abstraction, not before.

#### Scenario: register exactly the two readers and two writers
- **GIVEN** the memory layer's reader and writer registries
- **WHEN** they are listed
- **THEN** there is exactly one reader and one writer for Claude Code and one each for Codex

### Requirement: Read Codex's memory from its v2 summary
The Codex reader MUST read one file, `<config_dir>/memories_v2/memory_summary.md`, and take from it each topic of `What's in Memory`, which Codex groups under a named project scope. A topic MUST be filed under the `cwd:` recorded in the header of the rollout summary it points at, and not published when it points at none or the header records none. A topic's identity MUST be its scope and its text, so the topics around it can move without changing it and a topic Codex rewrote is a new memory. The reader MUST NOT read the rest of the summary (the User Profile, the preferences, the General Tips), which is about the person rather than a project, and MUST NOT read Codex's v1 folder `memories/` (`MEMORY.md` and its summary): its task-group bullets are working notes of single tasks.

#### Scenario: a Codex v2 topic reaches Claude Code
- **GIVEN** Codex whose v2 summary lists a topic pointing at a rollout summary recorded in a project checked out here, plus a preference and a General Tips paragraph
- **WHEN** memory syncs
- **THEN** the topic is written with its details into the marked block of that project's `MEMORY.md`
- **AND** the preference and the tip are written nowhere

#### Scenario: Codex's v1 task groups are not read
- **GIVEN** Codex with a v1 `MEMORY.md` holding a task group for a project checked out here, and no v2 summary
- **WHEN** memory syncs
- **THEN** the hub holds nothing and the v1 files are not among the sources
