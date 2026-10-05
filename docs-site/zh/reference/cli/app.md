---
title: coffer app
description: "The Coffer desktop app."
pageClass: cli-ref
---

# coffer app

The Coffer desktop app.

```sh
coffer app [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer app --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`app update`](#app-update) | Check for, and install, a new version of the desktop app. |
| [`app update status`](#app-update-status) | The app's version, the newest release found and whether it checks daily. |
| [`app update check`](#app-update-check) | Check for a new release against the signed manifest now. |
| [`app update install`](#app-update-install) | Download, verify and install the release found, then restart the app. |
| [`app update auto-check`](#app-update-auto-check) | Switch the app's daily update check on or off. |

## app update

Check for, and install, a new version of the desktop app.

<p class="cli-label">概要</p>

```sh
coffer app update [OPTIONS] COMMAND [ARGS]...
```

子命令：`status`, `check`, `install`, `auto-check`。

## app update status

The app's version, the newest release found and whether it checks daily.

<p class="cli-label">概要</p>

```sh
coffer app update status [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## app update check

Check for a new release against the signed manifest now.

<p class="cli-label">概要</p>

```sh
coffer app update check [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## app update install

Download, verify and install the release found, then restart the app.

<p class="cli-label">概要</p>

```sh
coffer app update install [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## app update auto-check

Switch the app's daily update check on or off.

<p class="cli-label">概要</p>

```sh
coffer app update auto-check [OPTIONS] STATE
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `STATE` <span class="cli-chip">参数</span> | text | 必填 | on or off |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
