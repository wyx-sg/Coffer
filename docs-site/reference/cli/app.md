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

This page matches what `coffer app --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`app update`](#app-update) | Check for, and install, a new version of the desktop app. |
| [`app update status`](#app-update-status) | The app's version, the newest release found and whether it checks daily. |
| [`app update check`](#app-update-check) | Check for a new release against the signed manifest now. |
| [`app update install`](#app-update-install) | Download, verify and install the release found, then restart the app. |
| [`app update auto-check`](#app-update-auto-check) | Switch the app's daily update check on or off. |

## app update

Check for, and install, a new version of the desktop app.

<p class="cli-label">Synopsis</p>

```sh
coffer app update [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `status`, `check`, `install`, `auto-check`.

## app update status

The app's version, the newest release found and whether it checks daily.

<p class="cli-label">Synopsis</p>

```sh
coffer app update status [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## app update check

Check for a new release against the signed manifest now.

<p class="cli-label">Synopsis</p>

```sh
coffer app update check [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## app update install

Download, verify and install the release found, then restart the app.

<p class="cli-label">Synopsis</p>

```sh
coffer app update install [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## app update auto-check

Switch the app's daily update check on or off.

<p class="cli-label">Synopsis</p>

```sh
coffer app update auto-check [OPTIONS] STATE
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `STATE` <span class="cli-chip">argument</span> | text | required | on or off |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
