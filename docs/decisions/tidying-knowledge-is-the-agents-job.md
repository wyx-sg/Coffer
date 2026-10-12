# Tidying Knowledge Is the Agent's Job, One Hand-Off Recorded as One Change

**Status**: Accepted
**Date**: 2026-10-12
**Deciders**: Yuxing Wu
**Related**: [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md), [Knowledge Is a Wiki of Pages Compiled From Kept Sources](knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md), [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md), [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), [Coffer Ships Its Own Manual as a Skill Resource](coffer-ships-its-own-skill.md), [Managed Agents Run With Full Permissions; Owner Pairing Is the Gate](managed-agents-run-with-full-permissions.md), [Internal Engine Settings](internal-engine-settings.md), research notes [knowledge curation](../research/knowledge-curation.md) and [knowledge structures](../research/knowledge-structures.md), spec knowledge "Teach writing and tidying in the guide", "Hand a tidy to the agent", "Record a tidy as one change", "Undo a tidy", spec vault-storage "Keep the last valid version when a hand edit is invalid", OpenSpec change `make-a-tidy-one-change`

## Context

Knowledge rots unless something tidies it. Pages repeat each other and
contradict each other, a source waits until someone folds it into the pages,
and a fact an agent wrote down lands beside the page that already covers its
subject. Tidying is judgement: where a fact belongs, which two pages are about
the same subject, which statement is stale. This ADR settles three linked
questions about that judgement: **who** makes it, **how the person asks** for
it, and **what it leaves behind** in the history.

**Who.** Coffer used to make the judgement with its own model. A curation pass
folded new knowledge into a collection's documents, and a two-stage distil pass
merged the agents' memory entries into notes. Both ran on a timer through a
separate model connection the person had to configure. Three facts came out of
running that way:

- **Without a connection nothing was tidied.** Both passes degraded to a
  mechanical path when no connection was set, which is a first-run state. On the
  maintainer's machine 58 items had waited in the knowledge inbox since
  2026-09-28 with nothing curating them.
- **The model was the weaker one.** The person's own coding agent has file
  tools, a stronger model and a person watching it. Coffer's pass had a small
  fenced toolset and a cheaper model, and nobody saw it run.
- **Unattended rewriting of synced content needs its own safety machinery.**
  Two machines curating the same material produce the same knowledge twice at
  different paths, which git merges cleanly. Preventing that took an owner
  machine, a lock shared with the sync round, a per-pass write cap and an undo.

The agents already load the `coffer-guide` skill
([Coffer Ships Its Own Manual as a Skill Resource](coffer-ships-its-own-skill.md)),
so there is a delivery channel for instructions that costs nothing extra.
Memory is outside this decision: Coffer keeps no memory of its own to tidy, and
each agent curates the copies Coffer writes into its own memory with its own
built-in curation
([Sync Memory Into Each Agent's Own Memory](sync-memory-into-each-agents-own-memory.md)).

**How the person asks.** Once the agent did the work, a collection page carried
two hand-offs: **Tidy**, which edits, and **Check with agent**, which read the
collection and reported contradictions, stale statements, duplicated subjects
and missing pages without changing anything. Beside them sat Coffer's own
mechanical check, computed on every read (dead and ambiguous links, orphan and
incomplete pages, pages without sources, waiting sources). Comparing the two
prompts with the guide showed that Tidy's steps — merge duplicates, split mixed
pages, fix contradictions and dead links — already covered almost everything a
check looked for; the check added only "don't touch anything yet". Yet only the
check prompt carried Coffer's mechanical findings, so the hand-off that edited
had the less complete list of problems.

**What it leaves behind.** Every vault write is one commit naming its writer
([Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md)),
and an agent's own file edits are committed by the vault's scanner and the
knowledge sweep as `disk` writes once the file has been quiet. A tidy that ran
for twenty minutes therefore became a run of `disk` commits, interleaved with
whatever else changed, with no boundary saying which belonged to the tidy, no
place for the agent's report, and no way to put the tidy back except file by
file from each file's History.

**How comparable tools answer the same questions** (research notes
[knowledge curation](../research/knowledge-curation.md) and
[knowledge structures](../research/knowledge-structures.md)):

- **Karpathy's LLM Wiki** (April 2026) names three operations — ingest, query
  and **lint** — with lint a separate pass over the wiki.
- Most implementations split lint into a **deterministic layer** that code runs
  and a **judgement layer** an LLM runs, as Coffer does. The judgement layer
  usually only reports: kfchou/wiki-skills' `wiki-lint` writes a report page,
  claude-obsidian only reports.
- **Ar9av/obsidian-wiki** documents why: its maintenance skills (lint, dedup,
  cross-linker, taxonomy) optimise different objectives and undo each other —
  "vault equilibrium" — so it added a report-only mode that checks they all
  propose nothing and detects oscillation.
- **Astro-Han/karpathy-llm-wiki**, after three months of production logs,
  applies the **safe** lint fixes itself and **reports** what needs judgement
  (contradictions, missing pages, orphans): fix what is certain, report what is
  not.
- **kfchou/wiki-skills** makes each operation **one git commit** with a
  `Wiki-Op:` trailer and renders its log from git on demand; it suggests the
  commit and commits only on confirmation.
- **Google Docs and Notion** version history group one person's consecutive
  edits over a stretch of time into one **session**, shown as one entry that
  expands into detail and can be restored as a whole.

All of these are command-line skills or editors the person drives directly: to
change something they tell the agent. Coffer's Tidy is the same — a session in
the person's own terminal that they watch, ending with a report.

## Options Considered

The options fall into three groups, one per question above. Each group's
chosen option is marked.

### Who tidies

#### Option A — The agent tidies on request; the person presses Tidy (chosen)

The `coffer-guide` skill teaches the judgement: how to write a fact straight
into the right page and how to integrate sources and tidy a collection. A
**Tidy** button on each collection, and **Tidy all** on the Knowledge page,
starts the default hand-off agent in the person's preferred terminal with a
prompt Coffer renders as its first message. With no managed agent the button
offers Copy prompt only. Coffer keeps only the mechanical work: material
becomes a source at once, a file dropped into `.inbox/` is adopted by the next
sweep, and the mechanical findings are computed on read.

- **Pros.** The strongest model on the machine does the judgement, with file
  tools, while the person watches. Nothing needs a separate model connection.
  Coffer makes no model call over knowledge, so there is no unattended
  rewriter of synced content and no owner machine to name. The cost sits in
  the person's own agent session, started by the person.
- **Cons.** Pages duplicate until someone presses Tidy. An agent can tidy
  badly; that is bounded by the history, and by the undo below.
- **Why it wins.** The judgement belongs to the actor with the best model and
  the person's attention, and pressing a button is the consent that makes a
  prompt that edits Coffer's own files safe to send without asking again.

#### Option B — Keep Coffer's own model passes

Curation and a model-driven distil run on timers through an internal default
connection.

- **Pros.** Tidying happens without anyone asking.
- **Cons.** A separate connection to configure, and a silent fallback when it is
  missing. A weaker model than the agent the person already pays for. An
  unattended rewriter of the only copy, with the bounds, owner machine and undo
  that implies. A LangChain and LangGraph dependency for one subsystem.
- **Why it lost.** It needed more machinery than the work deserved and, on the
  one real vault that used it, did not run.

#### Option C — Scheduled agent runs

Start a managed agent on a timer to tidy.

- **Pros.** Unattended, with the stronger model.
- **Cons.** It spends the person's agent quota without their knowledge, leaves
  agent sessions nobody started, and has to be kept from looping through
  whatever fires inside every session it starts, such as the person's own
  agent hooks.
- **Why it lost.** Nothing the person did started it.

#### Option D — Tidy only as a prompt the person pastes

- **Pros.** No automatic send.
- **Cons.** An extra step on every tidy, for a prompt that only edits Coffer's
  own recoverable files.
- **Why it lost.** It is the fallback when no managed agent exists, not the
  default.

#### Option E — A tool the agent calls to tidy

Expose a `coffer__tidy` gateway tool that runs a model pass on the agent's
behalf.

- **Pros.** The agent can trigger it mid-task.
- **Cons.** The caller is the stronger reasoner, so delegating to a weaker model
  lowers quality, and a second model hop adds latency and cost. An earlier
  `coffer__ask` tool of the same shape was called four times in thirty days and
  removed.
- **Why it lost.** The agent can already do the work itself with the guide.

### How the person asks

#### Option F — Keep Tidy and Check with agent side by side

Two buttons and two prompts: Tidy edits; Check reports and changes nothing.

- **Pros.** A one-click "look, don't touch". It mirrors the report-only
  judgement layer most LLM-wiki implementations ship, and obsidian-wiki's
  finding that maintenance passes undo each other argues for a pass that
  writes nothing.
- **Cons.** Two hand-offs that overlap almost completely, two guide sections to
  keep consistent, and two equally prominent buttons on the page. The prompt
  that edits lacked the findings list the prompt that reported carried.
  Obsidian-wiki's problem comes from several *unattended* passes with competing
  objectives; a Coffer tidy is one session the person watches, so there is no
  second pass to oscillate against.
- **Why it lost.** In Coffer the person already drives the agent directly, as
  in every CLI-skill implementation: "don't change anything yet, just tell me"
  is one sentence in the session Tidy opened, and the guide tells the agent to
  report and change nothing when asked only for a review. A button for that
  sentence is not worth a second hand-off.

#### Option G — One Tidy that fixes what is certain and reports what is not (chosen)

Remove **Check with agent**, `check_handoff` and the guide's "Checking a
collection" section. The Tidy prompt carries the collection's mechanical
findings (up to 40 lines, then a count) and orders one complete maintenance:
integrate the waiting sources, fix the mechanical findings, merge, split and
correct, and **leave alone anything uncertain** — two pages that disagree with
nothing to tell which is right, a deletion of much text, a change to the
README's page types — listing it in the report as a decision for the person.
Tidy all's prompt carries each collection's finding count and tells the agent
to read the findings with `coffer knowledge check <collection>`. Coffer's own
mechanical check stays on the collection page, computed on every read.

- **Pros.** One button, one prompt, one guide section, and the agent that edits
  has the full list of problems. It is the rule Astro-Han's production skill
  converged on (safe fixes applied, judgement reported). What needs a person's
  decision is still reported, now inside the tidy's own report.
- **Cons.** No one-click report-only run; a person who wants one asks for it in
  words.
- **Why it wins.** It keeps the useful half of a check — the report of what
  needs a decision — and drops the button that duplicated Tidy.

#### Option H — Check only; the person fixes or asks for each fix

The agent only reports; the person approves fixes one by one.

- **Pros.** Nothing changes without an explicit go-ahead.
- **Cons.** Every tidy becomes a review session and waiting sources are never
  integrated without a second request. kfchou's confirm-before-commit gives the
  same safety at a lower cost, and Coffer's undo below gives it after the fact.
- **Why it lost.** It turns the common case — a tidy that is fine — into
  extra work, to protect against the rare one that the history and the undo
  already recover from.

### What a tidy leaves behind

#### Option I — Pause the collection while the tidy runs and commit once at the end (chosen)

The agent runs `coffer knowledge tidy-start <collection>` before it edits and
`coffer knowledge tidy-finish <collection> --set summary="<report>"` when it is
done. Start first commits whatever already changed in the collection as the
`disk` edit it is, then opens a tidy in a registry in the daemon's memory.
While it is open, the vault writer treats the collection's path prefix as
**paused**: the scanner, the knowledge sweep and a sync round's settle leave
its edits in the working tree (a sync round whose incoming changes touch one of
them waits, as it does for any uncommitted edit). Finish closes the tidy and
commits every pending edit in the collection as **one** commit — writer
`agent`, operation `tidy`, the report as its summary, `Coffer-Status:
reported`. A tidy that changed nothing commits nothing. The sweep closes a tidy
whose collection sat unchanged for 30 minutes, committing it with no report and
`Coffer-Status: expired`, so an agent that forgets to finish cannot hold a
collection paused. A daemon restart forgets an open tidy; its edits are then
committed as ordinary `disk` writes, losing only the grouping. Finish with no
tidy open still commits the collection's pending edits as a tidy.

- **Pros.** The history itself holds the boundary: one commit is one tidy, so
  path-limited `git log`, the changes feed, a file's History and sync all see
  the same unit with no extra state. The report lives in the commit that holds
  the work. Undo is the inverse of one commit. Nothing new is stored or synced:
  the registry is bookkeeping about a session in progress, not about the
  corpus.
- **Cons.** The agent must run two commands; one that does not gets the
  previous behaviour (separate `disk` commits). Edits sit uncommitted for up
  to the tidy's length — at most 30 idle minutes after its last change — during
  which a sync round touching those files waits. The vault writer gains a
  second kind of "leave this path alone" beside a held path.
- **Why it wins.** It is the only option where the tidy is one change in the
  same history every other surface reads, with the report attached, so
  showing, syncing and undoing it need nothing new.

#### Option J — Tag each disk commit with a tidy trailer and group at read time

Commit the agent's edits as they are found, as now, but add `Coffer-Op: tidy
<id>` to each commit made while a tidy is open; the change log groups commits
with the same id into one entry; `tidy-finish` records the report. This is
kfchou's `Wiki-Op:` trailer applied to a run of commits.

- **Pros.** No paused paths: edits are committed as soon as they are quiet,
  exactly as before, and sync never waits on them.
- **Cons.** The report needs a home: an empty commit of its own, which a
  path-limited `git log -- knowledge/<collection>` does not show because it
  touches no path, or a trailer on the last commit, which does not exist yet
  when the agent finishes. Every reader — the feed, the file History, sync's
  review — has to learn the grouping, and anything that reads git directly
  shows N commits. Other writers' commits interleave with the tidy's, so
  undoing "the tidy" means reverting N commits in order around them.
- **Why it lost.** It moves the boundary out of the history into a
  convention every reader must apply, and still has nowhere natural for the
  report.

#### Option K — Group consecutive disk edits by time in the UI only

Show consecutive `disk` commits within a time window as one entry, as Google
Docs and Notion group a person's edits into a session.

- **Pros.** No backend change and no command for the agent to remember.
- **Cons.** Time is not a boundary: a tidy's commits interleave with a person's
  own saves and another agent's, and a long pause splits one tidy in two. There
  is nowhere for the agent's report. An undo over a guessed group could revert
  edits that were not the tidy's.
- **Why it lost.** It cannot tell a tidy from anything else on disk, so it
  cannot carry the report or make undo safe. It is kept for what it is good
  at: the change log groups **ordinary** disk edits within 10 minutes into one
  entry for reading, with no undo offered on the group.

#### Option L — A separate store of tidy runs outside git

Record each run — start, end, files, report — in `runs.db` or a file in the
vault, and join it with the history at read time.

- **Pros.** Rich metadata (duration, agent, per-file notes) without touching
  commit messages.
- **Cons.** It is stored state about the corpus, which the knowledge layer's
  standing constraints rule out ([Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md)).
  In `runs.db` it is machine-local, so another Mac sees the commits without
  the runs; in the vault it is a second record that can disagree with git.
- **Why it lost.** The history already records who changed what; a second
  record of the same thing is what this layer refuses everywhere else.

### Undo

A tidy that is one commit has a natural inverse.
`POST /api/v1/knowledge/changes/{version}/undo` puts every file the change
touched back as it was just before it — re-adding what it removed, removing
what it added — as one new commit by the user, operation `restore`, carrying
`Coffer-Undoes`. It never rewrites history: the tidy stays in it, followed by
its undo. If a file was edited after the change, the undo is refused with
`KNOWLEDGE_UNDO_CONFLICT` naming the files and writes nothing until the person
confirms with `force`; the discarded edits remain in the history. The
alternatives were a `git revert` of the commit (which fails as a merge
conflict exactly when a later edit exists, and so cannot offer "undo anyway")
and per-file Restore from each file's History (which is what the person had
before and is what made a bad tidy expensive).

## Decision

Tidying knowledge is the agent's job, started by the person with **Tidy** or
**Tidy all**, and nothing tidies unattended; Coffer runs no model of its own
over knowledge. **Tidy is the only hand-off**: its prompt carries Coffer's
mechanical findings and tells the agent to integrate waiting sources, fix the
findings, merge, split and correct, and to leave anything uncertain alone and
report it. Coffer's mechanical check stays on the collection page. **A tidy is
one change**: the agent opens it with `tidy-start`, the collection is paused in
the vault writer while it works, and `tidy-finish` commits everything as one
`agent` `tidy` commit carrying the report; the sweep closes an abandoned tidy
after 30 idle minutes. **A tidy can be undone as a whole**, as one new commit,
after asking when later edits would be lost.

Rules a future change must respect:

- Coffer's mechanical passes (the knowledge sweep, the memory sync) merge or
  rewrite no content by meaning. Anything that needs to decide where a fact
  belongs or which statements agree is written into the guide, not into a pass.
- A tidy runs only when the person asks for it.
- The prompt is rendered by the backend like every hand-off; the web UI only
  sends it.
- A tidy's boundary lives in the history as one commit, not in a side store or
  a read-time convention. The open-tidy registry stays in memory; it is never
  persisted or synced.
- A paused path is the pauser's to commit, and every pause must end on its own
  (finish, idle expiry or restart).
- Undo adds a commit; it never rewrites or drops history, and it never discards
  a later edit without the person's confirmation.

## Consequences

- No Coffer-run model call remains except speech-to-text, which keeps its own
  connection and model ([Internal Engine Settings](internal-engine-settings.md)).
- The collection page has one hand-off button. Its change log shows a tidy as
  one entry with the agent's report and **Undo this tidy…**, and its **To do**
  section lists the same findings the prompt carries.
- A person who wants a review only asks the agent for one in words; the guide
  tells the agent to change nothing then.
- An agent that skips `tidy-start` loses only the grouping; its edits are still
  committed and restorable file by file.
- A sync round may wait on a collection while a tidy is open, at most until the
  tidy finishes or sits idle for 30 minutes.
- Enforced by spec knowledge "Hand a tidy to the agent", "Record a tidy as one
  change" and "Undo a tidy", and spec vault-storage "Keep the last valid version
  when a hand edit is invalid"; the guide text is
  `backend/coffer/application/knowledge/skill_assets/coffer-guide.md`, the
  pause is `VaultWriter.set_paused` and the tidy lifecycle is
  `application/knowledge/tidy_service.py`.
