# Sync

Work the same project from a laptop and a desktop and both machines produce vault state — knowledge notes, skills, MCP registrations, agent configuration, credentials. **Sync** keeps them the same vault by converging each of them with a git repository **you own**. A background worker commits what this vault holds, lets git three-way-merge it against what the remote holds, and applies the result back — deletions included.

The remote is a **rendezvous, not a system of record**. Every machine's vault stays complete and authoritative, so you can delete the repository and rebuild it from any single machine without losing anything. The encryption master key is never written into it.

## Point the first machine at a repository

Create an empty repository wherever you like — GitHub, your own server, a bare repo on a NAS, even a `file://` path on a USB drive. Put the push token in the credential store first, so the remote names it by reference and never by value:

```bash
coffer credentials set sync/github-token
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

The remote is probed before it is accepted, so a typo or a token that cannot push fails here rather than an hour later. `coffer sync remote show` prints what is configured; `coffer sync remote clear` forgets it and leaves the vault exactly as it is.

Then run a round by hand rather than waiting for the timer:

```bash
coffer sync now
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

Joining reports **which kind of join this is** before it applies anything, and the two kinds get opposite treatment:

- **A new machine takes the union.** Its id is not in the remote's machine registry, so the round's base is git's empty tree — a diff from nothing can only contain additions. Everything the remote holds is added here, everything this machine already had stays, and the next round publishes both. Deletion is structurally impossible, not merely avoided.
- **A returning machine recovers its base.** Its id *is* in the registry, so it has converged before and merely lost its local pointer — a reinstall, a wiped `~/.coffer`, a disk restored from elsewhere. Its descriptor names the commit it last reached, that commit becomes the base, and the round proceeds as an ordinary stale-machine round: the remote's deletions are applied, this machine's edits are kept, and nothing resurrects.

That distinction is the whole point. A returning machine treated as new would republish everything the others deleted while it was away — every deletion undone at once, with no conflict raised, because a union has no base to disagree with.

If a returning machine's vault is *also* gone, the round stops and asks rather than publishing the loss; see [When a round asks before it deletes](#when-a-round-asks-before-it-deletes). And if its recorded base is no longer in the remote's history, there is no safe default at all, so the round refuses until you choose: `coffer sync adopt --keep-local` publishes this vault's documents as additions, and `coffer sync rebuild` takes the remote's state instead.

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
Skip this and convergence still works, but credentials that arrived are reported as `credentials_locked` and the resources that need them will not start. The Machines tab compares key fingerprints for you and says so in words, so you do not have to notice it yourself.
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

Rounds that changed nothing are listed like any other. They are the majority, and they are what makes a **gap** visible: without them, a vault that stopped converging on Tuesday looks the same as one that has had nothing to do.

A path that fails to apply is reported and rejoins the next round rather than aborting this one. A path that cannot apply on this machine **at all** — an agent whose `config_dir` does not exist here — is recorded as *not applicable here*: it is preserved, not retried, and not counted as an error.

## What a machine keeps to itself

Two things deliberately stay put, and both are the same idea: what a machine *does* with the vault belongs to that machine.

**Reach does not sync.** A resource's on/off switch and its agent scope — the reach button in the web UI, the one labelled with where the resource currently reaches, whose panel offers Disabled, Every agent and Only selected agents; and `coffer resource enable|disable` / `coffer scope set` on the command line — are set on the machine they apply to. Every machine sets its own, and a converge round never reads or writes either one. So "this work MCP server belongs on the desktop, not the laptop" is said at the laptop:

```bash
coffer resource disable mcp_server:work-jira      # on the laptop
coffer scope set mcp_server:work-jira --agents claude-code
```

The server itself still converges to both machines — it is registered and visible everywhere, and a change to its configuration reaches both — it simply does not **activate** on the laptop, and the gateway exposes none of its tools to any session there. The desktop is untouched, and stays untouched, because nothing about reach is ever published.

The cost is worth knowing: a resource arriving on a machine for the first time starts at that machine's default reach, not at the reach it has elsewhere. That is a state you can see on the page and change in one click, and it is the direction that asks rather than assumes.

**Channels do not sync at all.** A channel is an inbound surface bound to one machine — its port, its tunnel, the webhook URL the platform was told to call — so a channel arriving on a second machine would at best do nothing and at worst answer the same conversation twice. Configure channels on each machine that needs one.

## The machines in your vault

```bash
coffer sync machine list
```

```
Name                   Id        System  Last converged  Key  Agents
Laptop  (this machine) a3f21c9e  darwin  2026-09-13      ✓    claude-code, codex
Desktop                b7c40d29  darwin  2026-09-13      ✓    claude-code
```

Rename one whenever you like — nothing in the vault references the label, or the id. Retiring one removes its descriptor and rewrites nothing else:

```bash
coffer sync machine rename "Work desktop"
coffer sync machine remove b7c40d29e1f58a33
```

The machine id is derived from the host — `IOPlatformUUID` on macOS, `/etc/machine-id` on Linux — so it survives reinstalling Coffer and a machine never comes back as a ghost. Where neither is readable a generated id is cached under `~/.coffer` instead; that one does **not** survive deleting the directory, and both `status` and the Machines tab say so.

## When a conflict stops a round

Edit the same lines of the same document on two machines before either has converged and git cannot decide. With an internal model configured, a bounded pass attempts the merge **in the working tree only** and reports every path it touched, so a machine merge of your own notes is never silent. Otherwise the round stops without touching your vault:

```
conflict
  applied here: nothing
  published: nothing
  conflict: knowledge/projects/coffer.md
  resolve them with your own git tools, then run 'coffer sync now'
```

The vault is untouched and the pointer has not moved, so nothing is lost while you decide. The working tree is an ordinary git repository:

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
- **Config resources** — `mcp_server`, `agent`, `skill`, `knowledge`, `memory` and `provider` definitions, serialized to one deterministic YAML each. What a resource **is** travels: its name, its description and its configuration. What it **reaches** does not — see [What a machine keeps to itself](#what-a-machine-keeps-to-itself). `channel` is not serialized at all. Paths under `$HOME` are stored against a `~` sentinel and expanded against each machine's own home.
- **Shared state** — the areas that belong to the vault rather than to one machine: MCP capability preferences, internal engine settings, and the agent plugin inventory.
- **Credentials** — Fernet **ciphertext only**, and only with `--with-credentials`.
- **Machine descriptors** — one document per machine, at `machines/<id>.yaml`. Each machine writes only its own, so they can never conflict; the registry is simply whatever those files currently hold.

The plugin inventory is an **inventory, not an installer**. It records which plugins each agent has on each machine, at `state/agent-plugins/<agent>.yaml`, and writes nothing into any agent's configuration. On a new machine, open the file and install them with the vendor's own CLI.

**Machine-local, never written to the repository:** logs, the rebuildable `coffer.db`, `daemon-config.json`, PID files, port allocations, chat history, conversations, the audit log, MCP invocation records — and the master key, under any setting.

Conversations and the audit log are excluded on purpose: they record what happened *on a machine*, and a merged history of two machines' activity would be a different feature with a different shape. They live at [`/activity`](/guide/web-ui) instead.

## The Sync page and REST

Everything above is also a top-level **Sync** page in the app, at `/sync`, with three tabs:

- **Status** — the remote's configuration, a converge-now button, and the master-key card, which saves the key as a browser download and reads it back through a file picker. A conflict or a held round appears here as a banner, at the top, because both are states you have to act on rather than records to browse.
- **History** — every round this machine has run, as a searchable, filterable table: when it finished, how it ended, what it applied here, what it published to the remote, and the commit it landed on. Applied and published are two columns rather than one, because that is the whole point of bidirectional convergence: a machine that publishes every round and applies nothing is coming from somewhere, and one that applies every round and publishes nothing is going somewhere. Open a row for the paths an agent merged, the ones that could not be applied, any locked credential references, and the error.
- **Machines** — the registry, with this machine marked, each machine's key fingerprint stated as a match or a mismatch in words, and the agents registered there.

Over HTTP the same operations live under `/api/v1/sync/*` — `remote`, `run`, `adopt`, `status`, `runs`, `restore`, `confirm`, `reject`, `rebuild`, `rollback`, the `machines` family and the key family. The key routes carry the key **material**, never a path: the CLI does its own file I/O so the daemon never opens a path a caller named.

[Credentials →](/guide/credentials)
