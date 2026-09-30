---
title: coffer skill
description: "Manage skills (AgentSkills standard)"
---

# coffer skill

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer skill [OPTIONS] COMMAND [ARGS]...
```

Manage skills (AgentSkills standard)

## skill list

```sh
coffer skill list [OPTIONS]
```

List managed skills.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output for scripts |

## skill show

```sh
coffer skill show [OPTIONS] NAME
```

Show one skill, by name or uid.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--json` | option | flag |  | JSON output for scripts |

## skill add

```sh
coffer skill add [OPTIONS] SOURCE
```

Add a skill from a folder, an archive or a Git repository; its name comes from SKILL.md.

A folder is imported at once. An archive or a repository is staged first: the command prints what it found and asks before adding anything.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `SOURCE` | argument | text | required | A skill folder, a .zip / .skill archive, or a Git URL |
| `--force, -f` | option | flag |  | Replace an existing skill of the same name |
| `--ref` | option | text |  | Git: branch, tag or commit |
| `--path` | option | text |  | Git: folder inside the repository |
| `--skill` | option | text (repeatable) |  | Which skill to add when there are several (repeatable) |
| `--all` | option | flag |  | Add every valid skill found |
| `--yes, -y` | option | flag |  | Add without asking |

## skill update

```sh
coffer skill update [OPTIONS] NAME
```

Check a Git-imported skill for updates, preview one and apply it.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--check` | option | flag |  | Only check the source for newer commits |
| `--yes, -y` | option | flag |  | Apply without asking |
| `--take-theirs` | option | flag |  | Apply over local edits, discarding them |
| `--keep-mine` | option | flag |  | Keep local edits and stop offering this update |
| `--prompt` | option | flag |  | Print the prompt that hands merging the update into your edits to an agent |
| `--merged` | option | text |  | Record that your edits were merged with the update at COMMIT: the pin moves there and the files stay as they are |
| `--json` | option | flag |  | JSON output for scripts |

## skill rm

```sh
coffer skill rm [OPTIONS] NAME
```

Remove a skill and tear down all its agent deliveries. A skill Coffer generates itself is refused (exit 5).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--force, --yes, -f, -y` | option | flag |  | Do not ask |

## skill enable

```sh
coffer skill enable [OPTIONS] NAME
```

Enable a skill: it is delivered to every agent in its scope.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |

## skill disable

```sh
coffer skill disable [OPTIONS] NAME
```

Disable a skill: its delivered links are withdrawn.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |

## skill scope

```sh
coffer skill scope [OPTIONS] NAME
```

Show or set which agents a skill reaches (this machine only).

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--agents` | option | text |  | Only these agents (a,b) |
| `--all` | option | flag |  | Every agent |
| `--none` | option | flag |  | No agent (dormant) |
| `--json` | option | flag |  | JSON output for scripts |

## skill verify

```sh
coffer skill verify [OPTIONS]
```

Report drift between bindings and on-disk symlinks.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output for scripts |
| `--fix` | option | flag |  | Re-deliver repairable drift (missing/tampered links) from master; leaves foreign content untouched. |
| `--prompt` | option | flag |  | Print the prompt that hands each finding no repair settles to an agent |
