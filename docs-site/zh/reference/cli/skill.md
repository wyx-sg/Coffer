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

本页与 `coffer skill --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
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

<p class="cli-label">概要</p>

```sh
coffer skill list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## skill show

Show one skill, by name or uid.

<p class="cli-label">概要</p>

```sh
coffer skill show [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## skill add

Add a skill from a folder, an archive or a Git repository; its name comes from SKILL.md.

A folder is imported at once. An archive or a repository is staged first: the command prints what it found and asks before adding anything.

<p class="cli-label">概要</p>

```sh
coffer skill add [OPTIONS] SOURCE
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `SOURCE` <span class="cli-chip">参数</span> | text | 必填 | A skill folder, a .zip / .skill archive, or a Git URL |
| `--force, -f` <span class="cli-chip">选项</span> | 开关 |  | Replace an existing skill of the same name |
| `--ref` <span class="cli-chip">选项</span> | text |  | Git: branch, tag or commit |
| `--path` <span class="cli-chip">选项</span> | text |  | Git: folder inside the repository |
| `--skill` <span class="cli-chip">选项</span> | text（可重复） |  | Which skill to add when there are several (repeatable) |
| `--all` <span class="cli-chip">选项</span> | 开关 |  | Add every valid skill found |
| `--yes, -y` <span class="cli-chip">选项</span> | 开关 |  | Add without asking |

## skill update

Check a Git-imported skill for updates, preview one and apply it.

<p class="cli-label">概要</p>

```sh
coffer skill update [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |
| `--check` <span class="cli-chip">选项</span> | 开关 |  | Only check the source for newer commits |
| `--yes, -y` <span class="cli-chip">选项</span> | 开关 |  | Apply without asking |
| `--take-theirs` <span class="cli-chip">选项</span> | 开关 |  | Apply over local edits, discarding them |
| `--keep-mine` <span class="cli-chip">选项</span> | 开关 |  | Keep local edits and stop offering this update |
| `--prompt` <span class="cli-chip">选项</span> | 开关 |  | Print the prompt that hands merging the update into your edits to an agent |
| `--merged` <span class="cli-chip">选项</span> | text |  | Record that your edits were merged with the update at COMMIT: the pin moves there and the files stay as they are |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## skill rm

Remove a skill and tear down all its agent deliveries. A skill Coffer generates itself is refused (exit 5).

<p class="cli-label">概要</p>

```sh
coffer skill rm [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` <span class="cli-chip">选项</span> | 开关 |  | Do not ask |

## skill enable

Enable a skill: it is delivered to every agent in its scope.

<p class="cli-label">概要</p>

```sh
coffer skill enable [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |

## skill disable

Disable a skill: its delivered links are withdrawn.

<p class="cli-label">概要</p>

```sh
coffer skill disable [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |

## skill scope

Show or set which agents a skill reaches (this machine only).

<p class="cli-label">概要</p>

```sh
coffer skill scope [OPTIONS] NAME
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">参数</span> | text | 必填 | Name or uid |
| `--agents` <span class="cli-chip">选项</span> | text |  | Only these agents (a,b) |
| `--all` <span class="cli-chip">选项</span> | 开关 |  | Every agent |
| `--none` <span class="cli-chip">选项</span> | 开关 |  | No agent (dormant) |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## skill verify

Report drift between bindings and on-disk symlinks.

<p class="cli-label">概要</p>

```sh
coffer skill verify [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |
| `--fix` <span class="cli-chip">选项</span> | 开关 |  | Re-deliver repairable drift (missing/tampered links) from master; leaves foreign content untouched. |
| `--prompt` <span class="cli-chip">选项</span> | 开关 |  | Print the prompt that hands each finding no repair settles to an agent |
