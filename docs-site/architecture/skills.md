---
title: Skills
description: How Coffer keeps one master copy of each skill, delivers it into agents as a link, takes skills in from a folder, an archive or a Git repository without writing anything until you confirm, and keeps a Git-imported skill pinned to one commit until you take an update.
---

# Skills

A skill is a folder an agent loads when a task calls for it: a `SKILL.md` with instructions, plus whatever scripts and references it needs. Coffer keeps one master copy of each skill and hands it to every agent that should have it. This page explains how that works and why it is built this way. For how to use it, see the [Skills guide](/guides/skills).

## Principles

- **One copy, many readers.** Each skill lives once, in `~/.coffer/vault/skills/<name>/`. Agents receive a link to that folder, never a copy of their own, so an edit reaches every agent at once and nothing can drift apart silently.
- **Nothing is trusted before it is looked at.** A folder, an archive or a repository is read into a staging area first. Coffer says what it found and writes nothing until you confirm.
- **A source is a pin, not a subscription.** A skill taken from a Git repository stays exactly as it was at the commit it came from. A newer commit is an offer you review, never an automatic change.
- **The skill decides who gets it.** Whether an agent holds a skill depends on the skill's own switch and its reach, and on nothing stored on the agent.

## The master folder and delivery

Every managed skill is a `skill` resource, filed as `~/.coffer/vault/resources/skill/<name>.json`, and one folder under `~/.coffer/vault/skills/`. Both are in the vault repository, so every change to either is a commit with a history. The folder's name is the skill's name, taken from its `SKILL.md`, and it is fixed once the skill is registered: it is the directory an agent loads the skill from and the name an agent invokes it by.

Delivery is one rule: a skill reaches an agent if and only if the skill is enabled and the agent is inside its reach. The [reconciler](/architecture/reconciler) keeps every agent's skills directory equal to that rule. For each skill an agent should hold, it places a link at `<config_dir>/skills/<name>` pointing at the master folder — a symlink, a junction on Windows, or — only on Windows, on a filesystem that supports neither — a copy, which the repair pass replaces from master when it no longer matches — and it removes links the rule no longer grants. It never overwrites a folder someone else put where a link belongs; that is reported instead.

Because the delivered path is a link, a person editing a skill from inside an agent's folder is editing the master. Nothing needs to be re-delivered after an edit.

## History

The master folders are inside the vault repository, so a skill has a history: every save through Coffer is a commit written by `user`, and an edit made in an editor or by an agent's own file tools is committed as `disk` once the file has been quiet. A save from the web UI states the fingerprint of what it read, so an edit made on disk in the meantime is refused rather than overwritten. The skill's **History** tab lists the versions with who wrote each, shows each version's changes file by file, and restores a version as a new commit after asking; `coffer vault history skills/<name>/` and `coffer vault restore` do the same from the terminal. See [Editing the vault by hand](/guides/vault-files).

Coffer's own `coffer-guide` is the exception: it is rendered from the running build, so it lives under `~/.coffer/derived/skills/coffer-guide/`, outside the vault, and has no history.

## Where a skill comes from

A skill enters the library from one of three sources. Each goes through the same steps: stage, look, confirm.

```mermaid
flowchart LR
  F["Folder on this machine"] --> S["Staging area"]
  A["Archive (.zip / .skill)"] --> S
  G["Git repository"] --> S
  S --> L{"What was found"}
  L -->|"confirm"| M["Master folder + resource file"]
  L -->|"cancel, or an hour passes"| X["Staging removed"]
  M --> D["Reconciler links it into each agent in reach"]
```

**Staging.** A stage is a directory in the system's temporary space, never inside `~/.coffer`, so vault sync cannot see it and a crash leaves nothing in the vault. The daemon remembers each stage for an hour; confirming or cancelling removes it at once. A stage that is never confirmed is swept on the next call.

**Finding the skill.** One rule for every source: a folder whose top holds `SKILL.md` is a skill. If the top of what you handed over is not one, each folder one level down that is becomes a candidate, and you choose which to add. Two levels down is not searched — a skill buried that deep is usually a repository's example or test fixture. Each candidate is checked like any imported folder (a valid `name` and `description`, no symlink that leaves the folder, at most 50 MB), and one that fails is shown with its reason rather than failing the rest.

**A name that is taken** is refused unless you choose Replace. Replacing swaps the master folder's content in place, so the skill keeps its reach and its delivered links.

### Archives

An archive is refused as a whole, with the offending entries named, before a byte of it is unpacked, when an entry could write outside the staging area (an absolute path, a `..` segment), when an entry is a symlink (its target was chosen by whoever made the archive), or when the sizes it declares already pass 50 MB. Declared sizes are only a promise, so unpacking also counts the bytes it actually writes and stops the moment the total passes the cap. The upload itself is capped the same way.

### Git repositories

Coffer runs this machine's own `git` to clone the repository into the staging area, resolves the ref you gave — a branch, then a tag, then a commit, or the default branch when you gave none — to one commit, and checks out only the folder you named. A GitHub folder address (`…/tree/<ref>/<path>`) is read as all three at once.

Git runs without a prompt and without a credential from Coffer. It can reach any public repository, and a private one when this machine's git already holds a credential for it — a credential helper, or SSH keys — because Coffer leaves the user's own git configuration in place. Coffer stores no Git secret of its own. Only the `https`, `http`, `ssh`, `git` and `file` transports are allowed, submodules are not fetched, hooks do not run, and a clone that takes too long is stopped. Any message git prints has secrets in a URL removed before it is shown. A URL typed with a user name or password is refused outright, because the source URL is stored in the vault, in the skill's own metadata and in API answers.

The repository address is not passed through the [SSRF guard](/architecture/security#outbound-requests): it is an endpoint you name yourself, fetched by a `git` subprocess the same way the vault sync remote is, and a company's own Git host usually sits on a private address the guard would refuse.

## Pinned to a commit

A skill added from a repository records where it came from: the URL, the ref you asked for, the folder inside the repository, the full commit it was copied from, and a **content hash** of that folder at that commit. The hash covers every file's path and bytes, and leaves out Coffer's own bookkeeping file. Comparing the master folder's hash with the pinned one is how Coffer knows you edited the skill since the pin, without keeping a checkout of the old commit around.

The pin travels with the skill to your other machines through vault sync; the skill's files travel with it, so every machine holds the same pinned content.

## Checking for updates

Coffer checks each Git-imported skill for newer commits when you ask, and on its own every six hours. A check clones into staging again, resolves the ref, and counts the commits since the pin that change the skill's folder. A ref that moved without touching the folder is up to date. The result — when it ran, whether git reached the repository and git's message if not, what the ref points at, how many commits and files that is — is kept in `~/.coffer/local/skill-source-status.json`, on this machine only. It is an observation, not part of the vault, so sync never carries it. The six-hourly check skips a skill checked within the last six hours, so a daemon that restarts often does not fetch every repository on every start.

An unreachable repository changes nothing: the skill keeps working from its pinned copy, and its page shows git's message and when the last check succeeded.

## Taking an update

Reviewing an update stages the pinned folder and the new commit's folder side by side and compares them file by file: what is added, removed and changed, with a diff for text files. Nothing is applied until you confirm.

Applying validates the new folder — its `SKILL.md` must still name the same skill, because a skill's name is fixed — swaps it into the master folder in one step, moves the pin to the new commit, and records the update in the audit log with both commits. The folder's name does not change, so the skill's reach and every delivered link stay exactly as they were, and agents see the new files at once.

If the master folder was edited since the pin, the update is a **conflict**. You choose: keep your edits (the pin stays, and Coffer does not offer that commit again — only a newer one), take the update (your edits are discarded), or compare one file at a time across your folder, the pinned commit and the new commit.

## Resolving what repair will not touch

Automatic repair only puts back a missing or repointed link; it never overwrites a folder Coffer did not make and never picks between two versions. Those cases wait for a person, and each has a confirmed answer:

- **A folder in the way.** The drift report lists a real folder at an agent's link path, whether the delivery was made before or is only wanted now. Comparing it diffs the folder against the master; keeping master moves the folder under `~/.coffer/content/backup/skills/<agent>/` and links master again, and keeping the agent's version swaps its files into the master first. Only that one agent's copy changes.
- **A delete over a foreign copy.** Deleting a skill is refused, with nothing changed, while any agent's path holds a folder Coffer did not make — deleting would either leave it behind or remove someone else's files.
- **A folder no skill claims.** A folder in the skills store with no record can be registered in place or moved to `~/.coffer/content/backup/skills/orphans/`; it is never hard-deleted.
- **A missing master.** Every read of a skill says whether its master folder is on disk, so a skill that is off still shows that its folder is gone.

A Git skill's source can also be changed: the new repository, ref and folder are staged like an update, measured against the current folder, and recorded only when the preview is applied.

## What a skill says it needs

A `SKILL.md` may list the commands it relies on under `requires` — `jq`, `gh>=2.40`, or a mapping with a command and a version. Coffer reads that list from the master folder each time it shows the skill, so an edit is visible at once, and it links each command to its page on the CLIs page. Declaring a requirement changes nothing about delivery: a skill whose command is missing is still delivered, and the agent that follows it will fail at the step that needs the command.

## Related

- [Skills guide](/guides/skills) — adding, updating and delivering skills.
- [Reconciler](/architecture/reconciler) — the loop that keeps delivered links true.
- [Resource framework](/architecture/resource-framework) — identity, reach and audit every kind shares.
- [Security model](/architecture/security) — outbound requests and what the guard covers.
- Spec: [skill-manager](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/skill-manager/spec.md)
