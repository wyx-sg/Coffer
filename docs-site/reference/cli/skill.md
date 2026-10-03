---
title: coffer skill
description: "Manage skills (AgentSkills standard)"
pageClass: cli-ref
---

# coffer skill

Manage skills (AgentSkills standard)

```sh
coffer skill [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer skill --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`skill list`](#skill-list) | List managed skills. |
| [`skill show`](#skill-show) | Show one skill, by name or uid. |
| [`skill add`](#skill-add) | Add a skill from a folder, an archive or a Git repository; its name comes from SKILL.md. |
| [`skill update`](#skill-update) | Check a Git-imported skill for updates, preview one and apply it. |
| [`skill rm`](#skill-rm) | Remove a skill and tear down all its agent deliveries. |
| [`skill enable`](#skill-enable) | Enable a skill: it is delivered to every agent in its scope. |
| [`skill disable`](#skill-disable) | Disable a skill: its delivered links are withdrawn. |
| [`skill scope`](#skill-scope) | Show or set which agents a skill reaches (this machine only). |
| [`skill verify`](#skill-verify) | Report drift between bindings and on-disk symlinks. |

## skill list

List managed skills.

<p class="cli-label">Synopsis</p>

```sh
coffer skill list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## skill show

Show one skill, by name or uid.

<p class="cli-label">Synopsis</p>

```sh
coffer skill show [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## skill add

Add a skill from a folder, an archive or a Git repository; its name comes from SKILL.md.

A folder is imported at once. An archive or a repository is staged first: the command prints what it found and asks before adding anything.

<p class="cli-label">Synopsis</p>

```sh
coffer skill add [OPTIONS] SOURCE
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `SOURCE` <span class="cli-chip">argument</span> | text | required | A skill folder, a .zip / .skill archive, or a Git URL |
| `--force, -f` <span class="cli-chip">option</span> | flag |  | Replace an existing skill of the same name |
| `--ref` <span class="cli-chip">option</span> | text |  | Git: branch, tag or commit |
| `--path` <span class="cli-chip">option</span> | text |  | Git: folder inside the repository |
| `--skill` <span class="cli-chip">option</span> | text (repeatable) |  | Which skill to add when there are several (repeatable) |
| `--all` <span class="cli-chip">option</span> | flag |  | Add every valid skill found |
| `--yes, -y` <span class="cli-chip">option</span> | flag |  | Add without asking |

## skill update

Check a Git-imported skill for updates, preview one and apply it.

<p class="cli-label">Synopsis</p>

```sh
coffer skill update [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--check` <span class="cli-chip">option</span> | flag |  | Only check the source for newer commits |
| `--yes, -y` <span class="cli-chip">option</span> | flag |  | Apply without asking |
| `--take-theirs` <span class="cli-chip">option</span> | flag |  | Apply over local edits, discarding them |
| `--keep-mine` <span class="cli-chip">option</span> | flag |  | Keep local edits and stop offering this update |
| `--prompt` <span class="cli-chip">option</span> | flag |  | Print the prompt that hands merging the update into your edits to an agent |
| `--merged` <span class="cli-chip">option</span> | text |  | Record that your edits were merged with the update at COMMIT: the pin moves there and the files stay as they are |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## skill rm

Remove a skill and tear down all its agent deliveries. A skill Coffer generates itself is refused (exit 5).

<p class="cli-label">Synopsis</p>

```sh
coffer skill rm [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--force, --yes, -f, -y` <span class="cli-chip">option</span> | flag |  | Do not ask |

## skill enable

Enable a skill: it is delivered to every agent in its scope.

<p class="cli-label">Synopsis</p>

```sh
coffer skill enable [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |

## skill disable

Disable a skill: its delivered links are withdrawn.

<p class="cli-label">Synopsis</p>

```sh
coffer skill disable [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |

## skill scope

Show or set which agents a skill reaches (this machine only).

<p class="cli-label">Synopsis</p>

```sh
coffer skill scope [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--agents` <span class="cli-chip">option</span> | text |  | Only these agents (a,b) |
| `--all` <span class="cli-chip">option</span> | flag |  | Every agent |
| `--none` <span class="cli-chip">option</span> | flag |  | No agent (dormant) |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## skill verify

Report drift between bindings and on-disk symlinks.

<p class="cli-label">Synopsis</p>

```sh
coffer skill verify [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |
| `--fix` <span class="cli-chip">option</span> | flag |  | Re-deliver repairable drift (missing/tampered links) from master; leaves foreign content untouched. |
| `--prompt` <span class="cli-chip">option</span> | flag |  | Print the prompt that hands each finding no repair settles to an agent |
