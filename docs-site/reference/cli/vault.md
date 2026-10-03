---
title: coffer vault
description: "The vault's history: versions, diffs, restore, and hand edits that were refused."
pageClass: cli-ref
---

# coffer vault

The vault's history: versions, diffs, restore, and hand edits that were refused.

```sh
coffer vault [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer vault --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`vault history`](#vault-history) | List a file's or folder's versions, newest first, with who wrote each. |
| [`vault diff`](#vault-diff) | Print what one version did to a file, as a unified diff. |
| [`vault show`](#vault-show) | Print a file's content as one version left it. |
| [`vault restore`](#vault-restore) | Put one version back, as a new version. |
| [`vault problems`](#vault-problems) | List hand edits that were refused: still on disk, not in effect until fixed. |

## vault history

List a file's or folder's versions, newest first, with who wrote each.

<p class="cli-label">Synopsis</p>

```sh
coffer vault history [OPTIONS] PATH
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">argument</span> | text | required | A vault file, or a folder ending in / |
| `--limit` <span class="cli-chip">option</span> | integer | `20` | How many versions |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## vault diff

Print what one version did to a file, as a unified diff.

<p class="cli-label">Synopsis</p>

```sh
coffer vault diff [OPTIONS] PATH VERSION
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">argument</span> | text | required | A vault file |
| `VERSION` <span class="cli-chip">argument</span> | text | required | The version (from `history`) |

## vault show

Print a file's content as one version left it.

<p class="cli-label">Synopsis</p>

```sh
coffer vault show [OPTIONS] PATH VERSION
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">argument</span> | text | required | A vault file |
| `VERSION` <span class="cli-chip">argument</span> | text | required | The version (from `history`) |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## vault restore

Put one version back, as a new version. A folder is restored whole: files the version did not have are removed.

<p class="cli-label">Synopsis</p>

```sh
coffer vault restore [OPTIONS] PATH VERSION
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `PATH` <span class="cli-chip">argument</span> | text | required | A vault file, or a folder ending in / |
| `VERSION` <span class="cli-chip">argument</span> | text | required | The version to put back (from `history`) |
| `--yes, -y` <span class="cli-chip">option</span> | flag |  | Do not ask |

## vault problems

List hand edits that were refused: still on disk, not in effect until fixed.

<p class="cli-label">Synopsis</p>

```sh
coffer vault problems [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |
