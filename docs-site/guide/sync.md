# Sync

Work the same project from a laptop and a desktop and both machines produce vault state — knowledge notes, skills, MCP registrations, agent configuration, credentials. **Sync** keeps them the same vault by converging each of them with a git repository **you own**. A background worker commits what this vault holds, lets git three-way-merge it against what the remote holds, and applies the result back — deletions included.

The remote is a **rendezvous, not a system of record**. Every machine's vault stays complete and authoritative, so you can delete the repository and rebuild it from any single machine without losing anything. The encryption master key is never written into it.

## Point the first machine at a repository

Create an empty repository wherever you like — GitHub, your own server, a bare repo on a NAS, even a `file://` path on a USB drive. Put the push token in the credential store first, so the remote names it by reference and never by value:

```bash
printf '%s' "$GITHUB_TOKEN" | coffer credentials set sync/github-token
coffer sync remote set https://github.com/you/coffer-vault.git \
  --credential-ref sync/github-token \
  --interval 3600 \
  --with-credentials
```

| Flag | Meaning |
| --- | --- |
| `--branch` | Branch to converge on. Default `main`. |
| `--interval` | **Seconds** between automatic rounds. Default `3600`. |
| `--with-credentials` | Carry credential **ciphertext**. Off by default. |
| `--credential-ref` | Name of the push credential in the credential store. |

`coffer credentials set` reads the secret from stdin, so the token never lands in your shell history. `--value` exists for scripts and says in its own help that it is the unsafe way.

The remote is probed before it is accepted, so a typo or a token that cannot push fails here rather than an hour later. `coffer sync remote show` prints what is configured; `coffer sync remote clear` forgets it and leaves the vault exactly as it is.

Then join the remote. Joining is always explicit — the timer and `coffer sync now` never join on their own — so even the first machine adopts the repository it just named:

```bash
coffer sync adopt --yes
```

```
ok
  applied here: nothing
  published: added 214
  commit: 9f1c2ab4c0d1
```

The first round against an empty remote has nothing to apply and everything to publish. What you just published is plain text in a repository you own — read it:

```bash
git -C ~/.coffer/sync log --stat -1
```

## Join from the second machine

Install Coffer there, then point it at the same repository:

```bash
coffer sync adopt https://github.com/you/coffer-vault.git
```

`adopt` takes an optional URL: with one, it configures the remote with the defaults above when none is set yet. A remote that needs a push credential, a different branch or a different interval is configured with `coffer sync remote set` first, exactly as on the first machine, and then joined with a bare `coffer sync adopt`.

Before it applies anything, `adopt` states the join and asks you to go ahead:

```text
Joining this remote as a returning machine: its id is in the registry, so it resumes from the base it last converged on.
  last converged here: 2026-09-01
  documents the remote changed since: 7
  documents this vault holds: 42
Join this remote? [y/N]:
```

It names **which kind of join this is**, the day this machine last converged with the remote, how many documents the remote has changed since then (everything it holds, for a new machine), and how many this vault holds. Answer `n` and nothing has changed. In a script, pass `--yes` once you have decided; without a terminal to answer the question and without `--yes`, `adopt` refuses rather than joining. On the web, the Sync page's Setup card offers **Join this remote** while this machine has not joined; it asks the same question in a dialog and joins only when you confirm. The preview is also `GET /api/v1/sync/join`.

The two kinds get opposite treatment:

- **A new machine takes the union.** Its id is not in the remote's machine registry, so the round's base is git's empty tree — a diff from nothing can only contain additions. Everything the remote holds is added here, everything this machine already had stays, and the next round publishes both. Deletion is structurally impossible, not merely avoided.
- **A returning machine recovers its base.** Its id *is* in the registry, so it has converged before and merely lost its local pointer — a reinstall, a wiped `~/.coffer`, a disk restored from elsewhere. Its descriptor names the commit it last reached, that commit becomes the base, and the round proceeds as an ordinary stale-machine round: the remote's deletions are applied, this machine's edits are kept, and nothing resurrects.

That distinction is the whole point. A returning machine treated as new would republish everything the others deleted while it was away — every deletion undone at once, with no conflict raised, because a union has no base to disagree with.

If a returning machine's vault is *also* gone, the round stops and asks rather than publishing the loss; see [When a round asks before it deletes](#when-a-round-asks-before-it-deletes). And if its recorded base is no longer in the remote's history, there is no safe default at all, so `adopt` says so and stops until you choose: `coffer sync adopt --keep-local` publishes this vault's documents as additions, and `coffer sync rebuild` takes the remote's state instead. On the web, the join dialog names this case and offers only the keep-local answer, under a button that says so.

## Bring the master key over

Only needed when the remote carries credentials. On the first machine:

```bash
coffer sync key export ~/coffer-master.key
```

Move that file over a channel you trust — password manager, secure copy, USB — **not** through the sync repository. On the second machine:

```bash
coffer sync key import ~/coffer-master.key
coffer sync key fingerprint        # compare two machines by eye if you like
```

::: warning Credentials without the key stay locked
Skip this and convergence still works, but credentials that arrived are reported as `credentials_locked` and the resources that need them will not start. The machine registry on the Sync page's **Setup** tab compares key fingerprints for you and says so in words, so you do not have to notice it yourself.
:::

## What a round does

One round is: serialize this vault into the working tree and commit it, fetch and merge the remote into that commit, apply the difference the merge brought in, push. Committing local state **before** the merge is what gives git the three inputs it needs, so different hunks of one file merge cleanly and the difference applied back is exactly what the remote contributed.

Two properties follow, and they are the ones worth internalising:

- **A deletion means someone deleted something.** A deletion is applied only when it appears in the diff as a deletion, which can only happen because some machine actually removed that document relative to a shared base. A machine that merely *lacks* a document asserts nothing — which is why a laptop that was off for a week comes back and absorbs what happened rather than undoing it.
- **An unchanged vault makes no commit.** Serialization is deterministic, so a round with nothing to say produces nothing at all. The repository's history records changes, not heartbeats.

Watch where things stand:

```bash
coffer sync status
```

```
remote: https://github.com/you/coffer-vault.git  branch main
  every 3600s · credentials included · enabled
  push credential: sync/github-token
  working tree: /Users/you/.coffer/sync
this machine: a3f21c9e4b7d2610
ok
  applied here: added 3
  published: nothing
  commit: c04b8e1f2a33
```

`status` answers what the vault is doing; `history` answers what it has been doing, one line per round, newest first:

```bash
coffer sync history --limit 20
```

```
2026-09-13T15:02:11  ok  applied: added 3  published: nothing  c04b8e1f2a33
2026-09-13T14:02:09  no_change  applied: nothing  published: nothing  —
```

`status` exits non-zero when the last round needs you — held for confirmation, conflicted, or failed to push or run — so a script or a cron job can notice without parsing the output.

Rounds that changed nothing are listed like any other. They are the majority, and they are what makes a **gap** visible: without them, a vault that stopped converging on Tuesday looks the same as one that has had nothing to do.

A path that fails to apply is reported and rejoins the next round rather than aborting this one. A path that cannot apply on this machine **at all** — an agent whose `config_dir` does not exist here — is recorded as *not applicable here*: it is preserved, not retried, and not counted as an error. The round that meets it lists it under `not applicable here` rather than `could not apply`, `coffer sync status` lists every path this machine holds that way, and on the Sync page the round's row in **Runs** shows them under *Not applicable on this machine*. Each round re-checks only the cheap precondition — does that agent's config directory exist here now? — so installing the agent later brings its document in on the next round, with no error in between.

Until a machine has joined, a round — the timer's or `coffer sync now` — still **detects** the join: it reads the remote's registry and works out whether this machine is new or returning, recovering a returning machine's base from its own descriptor, so a machine that forgot its pointer cannot skip the question. But it **applies** nothing and publishes nothing: it ends as `awaiting_join` and reports the join it found — the case, the day this machine last converged, how many documents the remote changed since and how many this vault holds. `coffer sync now` and `coffer sync status` print that report and point at `coffer sync adopt` (`status` exits non-zero, like any state that waits on you); the Sync page shows it on the Setup card and offers **Join this remote**, which confirms before it joins. The waiting round is recorded once, not once per interval. A pointer that no longer resolves — the working tree was deleted or moved — also waits for `adopt`, and the daemon log says so once.

## What a machine keeps to itself

Two things deliberately stay put, and both are the same idea: what a machine *does* with the vault belongs to that machine.

**Reach does not sync.** A resource's on/off switch and its agent scope — the reach button in the web UI, the one labelled with where the resource currently reaches, whose panel offers Disabled, Every agent and Only selected agents; and `coffer resource enable|disable` / `coffer scope set` on the command line — are set on the machine they apply to. Every machine sets its own, and a converge round never reads or writes either one. So "this work MCP server belongs on the desktop, not the laptop" is said at the laptop:

```bash
coffer resource disable mcp_server work-jira      # on the laptop
coffer scope set mcp_server work-jira --agents claude-code
```

The server itself still converges to both machines — it is registered and visible everywhere, and a change to its configuration reaches both — it simply does not **activate** on the laptop, and the gateway exposes none of its tools to any session there. The desktop is untouched, and stays untouched, because nothing about reach is ever published.

The cost is worth knowing: a resource arriving on a machine for the first time starts at that machine's default reach, not at the reach it has elsewhere. That is a state you can see on the page and change in one click, and it is the direction that asks rather than assumes.

**Coffer's own skill does not sync.** `coffer-guide` — the manual Coffer writes for itself, carrying the catalogue of your knowledge — is regenerated on each machine at every start and whenever the catalogue moves. Part of what goes into it is which collections are *enabled*, and that is reach, which stays on the machine it was set on. So the laptop and the desktop legitimately hold different copies, and publishing either would only have them overwriting each other on every round. Neither its folder nor its registration is ever pushed; each machine writes its own. Your own imported skills converge exactly as before.

**A channel's adapter stays on one machine.** A channel is an inbound surface — a port, a tunnel, the webhook URL the platform was told to call — and two machines answering it would reply to the same conversation twice. So the channel's document travels, carrying its configuration, its credential references, its pairings and the one machine whose daemon runs its adapter, and every other machine holds it without starting anything. Moving a bot to another machine is a rebind, not a re-registration. See [Channels](/guide/channels).

## The machines in your vault

```bash
coffer sync machine list
```

```
Name                   Id        System  Last converged  Key  Agents
Laptop  (this machine) a3f21c9e  darwin  2026-09-13      ✓    claude-code, codex
Desktop                b7c40d29  darwin  2026-09-13      ✓    claude-code
```

The `Key` column is the comparison already made for you: `✓` means that machine's credentials decrypt here, `✗ different` means they do not, and `—` means one of the two machines has published no fingerprint yet.

Rename one whenever you like — nothing in the vault references the label, or the id. Retiring one removes its descriptor and rewrites nothing else:

```bash
coffer sync machine rename "Work desktop"
coffer sync machine remove b7c40d29e1f58a33
```

The machine id is derived from the host — `IOPlatformUUID` on macOS, `/etc/machine-id` on Linux — so it survives reinstalling Coffer and a machine never comes back as a ghost. Where neither is readable a generated id is cached under `~/.coffer` instead; that one does **not** survive deleting the directory, and both `status` and the machine registry say so.

## When a conflict stops a round

Edit the same lines of the same document on two machines before either has converged and git cannot decide. With an internal model configured, a bounded pass attempts the merge **in the working tree only** and reports every path it touched, so a machine merge of your own notes is never silent. Otherwise the round stops without touching your vault:

```
conflict
  applied here: nothing
  published: nothing
  conflict: knowledge/projects/coffer.md
  resolve them with your own git tools, then run 'coffer sync now'
```

The vault is untouched and the pointer has not moved, so nothing is lost while you decide. That holds for a join too: a join that stops on a conflict has still joined — the machine has its base — so after resolving, the next step is the same `coffer sync now` (running `coffer sync adopt` again does the same thing on a machine that has joined). The working tree is an ordinary git repository:

```bash
cd ~/.coffer/sync
git status
$EDITOR knowledge/projects/coffer.md   # resolve the markers
git add -A && git commit
coffer sync now
```

A conflict blocks convergence on both machines until it is resolved. That is deliberate: two machines quietly disagreeing about one document is worse than two machines waiting.

Credential blobs never reach a text merge at all. A Fernet token carries its encryption time in cleartext, so two ciphertexts for one reference can be ordered without the key, and the fresher one wins.

## When a round asks before it deletes

A round whose diff would delete an unusual share of documents — more than 20% of an area, or 20 documents outright — does not proceed. It records what it would do and waits:

```
awaiting_confirmation
  held: this round would delete the following from the remote.
  If this vault was just reinstalled or restored, do NOT confirm.
    knowledge: 186 of 186
    - knowledge/global/notes/coffer.md
    …
```

Both directions are guarded. The **apply** side protects this vault from a remote that went wrong; the **publish** side protects the other machines from *this* one — a reinstall, a failed restore or a stray `rm -rf` would otherwise publish the loss as an ordinary deletion and take the fleet down with it.

**Moving documents is not deleting them.** What the guard counts is what a round would *lose*: a document whose content turns up at another path in the same round has moved, and a move is published without asking, however much of an area it touches. Reorganising a collection into subdirectories is the ordinary case. A document whose content goes nowhere is a deletion and is held exactly as before — and if a round both moves documents and deletes others, only the deletions are held and listed.

**One question is asked once.** A confirmation that nobody has answered stays one row in the Runs table and one line in the log, not one per tick: the round is re-derived on every pass, but re-reporting it would say nothing new. Re-deriving it also means a hold can let go by itself — if the documents come back, or the reason the guard objected is gone by the next pass, the vault converges again without anyone pressing anything.

```bash
coffer sync confirm    # yes, let it finish
coffer sync reject     # no — discard the round, the vault was never touched
coffer sync rebuild    # this machine is the damaged one: take the remote's state
```

`rebuild` is the third answer, and the only right one when the vault here is what broke: confirming would spread the loss to every other machine, and rejecting would refuse the same round forever. It replaces this vault with the remote's, discarding documents only this machine holds, and pushes nothing. It prompts before doing so; `--yes` skips the prompt.

If a round did apply something you did not want, it is reversible. Every round tags the state of the vault immediately before it applied, and the ten most recent snapshots are kept:

```bash
coffer sync rollback
```

## Bring back something deleted last week

The remote's history is also your backup. Restore moves the working tree to a revision and applies the difference from where you are now, so nothing the vault has gained since is discarded:

```bash
coffer sync restore --at 2026-09-05
coffer sync restore --at 4a71e0c
```

`--at` takes a sha, a ref, or a `YYYY-MM-DD` date, which resolves to the last commit at or before it. Restore is always explicit — a round never reaches back into history on its own.

## What travels

The working tree is a readable directory of text, one area per concern:

```
manifest.json  knowledge/  skills/  resources/  state/  credentials/  machines/
```

- **Knowledge** — the Markdown files under `~/.coffer/knowledge/`.
- **Skills** — the master skill store under `~/.coffer/skills/`.
- **Config resources** — `mcp_server`, `agent`, `skill`, `knowledge`, `provider` and `channel` definitions, serialized to one deterministic YAML each. What a resource **is** travels: its name, its description and its configuration. What it **reaches** does not — see [What a machine keeps to itself](#what-a-machine-keeps-to-itself). A channel travels too, carrying the id of the one machine whose daemon starts its adapter, so the document moves without the adapter moving with it. `memory` is the one kind that does **not** travel: a partition is derived from the agents installed on one machine, so each machine derives its own — see [Memory](/guide/memory). Paths under `$HOME` are stored against a `~` sentinel and expanded against each machine's own home.
- **Shared state** — the areas that belong to the vault rather than to one machine: MCP capability preferences, internal engine settings, and the agent plugin inventory.
- **Credentials** — Fernet **ciphertext only**, and only with `--with-credentials`.
- **Machine descriptors** — one document per machine, at `machines/<id>.yaml`. Each machine writes only its own, so they can never conflict; the registry is simply whatever those files currently hold.

The plugin inventory is an **inventory, not an installer**. It records which plugins each agent has on each machine, at `state/agent-plugins/<agent>.yaml`, and writes nothing into any agent's configuration. On a new machine, open the file and install them with the vendor's own CLI.

**Machine-local, never written to the repository:** logs, the rebuildable `coffer.db`, `daemon-config.json`, PID files, port allocations, chat history, conversations, the audit log, MCP invocation records — and the master key, under any setting.

Conversations and the audit log are excluded on purpose: they record what happened *on a machine*, and a merged history of two machines' activity would be a different feature with a different shape. They live at [`/activity`](/guide/web-ui) instead.

## The Sync page and REST

Everything above is also a top-level **Sync** page in the app, at `/sync`, with two tabs:

- **Runs**, where the page opens — every round this machine has run, as a searchable, filterable table: when it finished, how it ended, what it applied here, what it published to the remote, and the commit it landed on. Applied and published are two columns rather than one, because that is the whole point of bidirectional convergence: a machine that publishes every round and applies nothing is coming from somewhere, and one that applies every round and publishes nothing is going somewhere. Consecutive rounds that changed nothing fold into one row giving the span and the count. Open a row for the paths an agent merged, the ones that could not be applied, any locked credential references, and the error.
- **Setup** — the remote's configuration and a converge-now button, the master-key card, which saves the key as a browser download and reads it back through a file picker, and the machine registry, with this machine marked, each machine's key fingerprint stated as a match or a mismatch in words, and the agents registered there.

A held round carries its answers **on its own row** — confirm, naming the direction, the areas and the paths before it runs; reject; and, when this machine is the one that would publish the loss, rebuild from the remote. A conflict is a banner above the table instead, because its paths are resolved with your own git in the working tree. The newest round carries an **Undo** naming the paths it would take back — but only when it applied something here; after a quiet round there is nothing to undo, and the button does not move down to an older round, because a rollback always reverses the newest snapshot. Restoring to a point in time stays on the command line: the page has no view of the remote's history to preview it against.

Over HTTP the same operations live under `/api/v1/sync/*` — `remote`, `run`, `adopt`, `status`, `runs`, `restore`, `confirm`, `reject`, `rebuild`, `rollback`, the `machines` family and the key family. The key routes carry the key **material**, never a path: the CLI does its own file I/O so the daemon never opens a path a caller named.

[Credentials →](/guide/credentials)
