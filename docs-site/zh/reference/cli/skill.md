---
title: coffer skill
description: "Manage skills (AgentSkills standard)"
---

# coffer skill

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer skill [OPTIONS] COMMAND [ARGS]...
```

Manage skills (AgentSkills standard)

## skill list

```sh
coffer skill list [OPTIONS]
```

List managed skills.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## skill show

```sh
coffer skill show [OPTIONS] NAME
```

Show one skill, by name or uid.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## skill add

```sh
coffer skill add [OPTIONS] SOURCE
```

Add a skill from a folder, an archive or a Git repository; its name comes from SKILL.md.

A folder is imported at once. An archive or a repository is staged first: the command prints what it found and asks before adding anything.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `SOURCE` | 参数 | text | 必填 | A skill folder, a .zip / .skill archive, or a Git URL |
| `--force, -f` | 选项 | 开关 |  | Replace an existing skill of the same name |
| `--ref` | 选项 | text |  | Git: branch, tag or commit |
| `--path` | 选项 | text |  | Git: folder inside the repository |
| `--skill` | 选项 | text（可重复） |  | Which skill to add when there are several (repeatable) |
| `--all` | 选项 | 开关 |  | Add every valid skill found |
| `--yes, -y` | 选项 | 开关 |  | Add without asking |

## skill update

```sh
coffer skill update [OPTIONS] NAME
```

Check a Git-imported skill for updates, preview one and apply it.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--check` | 选项 | 开关 |  | Only check the source for newer commits |
| `--yes, -y` | 选项 | 开关 |  | Apply without asking |
| `--take-theirs` | 选项 | 开关 |  | Apply over local edits, discarding them |
| `--keep-mine` | 选项 | 开关 |  | Keep local edits and stop offering this update |
| `--prompt` | 选项 | 开关 |  | Print the prompt that hands merging the update into your edits to an agent |
| `--merged` | 选项 | text |  | Record that your edits were merged with the update at COMMIT: the pin moves there and the files stay as they are |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## skill rm

```sh
coffer skill rm [OPTIONS] NAME
```

Remove a skill and tear down all its agent deliveries. A skill Coffer generates itself is refused (exit 5).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

## skill enable

```sh
coffer skill enable [OPTIONS] NAME
```

Enable a skill: it is delivered to every agent in its scope.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

## skill disable

```sh
coffer skill disable [OPTIONS] NAME
```

Disable a skill: its delivered links are withdrawn.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |

## skill scope

```sh
coffer skill scope [OPTIONS] NAME
```

Show or set which agents a skill reaches (this machine only).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--agents` | 选项 | text |  | Only these agents (a,b) |
| `--all` | 选项 | 开关 |  | Every agent |
| `--none` | 选项 | 开关 |  | No agent (dormant) |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## skill verify

```sh
coffer skill verify [OPTIONS]
```

Report drift between bindings and on-disk symlinks.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |
| `--fix` | 选项 | 开关 |  | Re-deliver repairable drift (missing/tampered links) from master; leaves foreign content untouched. |
| `--prompt` | 选项 | 开关 |  | Print the prompt that hands each finding no repair settles to an agent |
