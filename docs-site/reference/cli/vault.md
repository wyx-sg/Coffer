---
title: coffer vault
description: "The vault's history: versions, diffs, restore, and hand edits that were refused."
---

# coffer vault

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer vault [OPTIONS] COMMAND [ARGS]...
```

The vault's history: versions, diffs, restore, and hand edits that were refused.

## vault history

```sh
coffer vault history [OPTIONS] PATH
```

List a file's or folder's versions, newest first, with who wrote each.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `PATH` | argument | text | required | A vault file, or a folder ending in / |
| `--limit` | option | integer | `20` | How many versions |
| `--json` | option | flag |  | JSON output for scripts |

## vault diff

```sh
coffer vault diff [OPTIONS] PATH VERSION
```

Print what one version did to a file, as a unified diff.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `PATH` | argument | text | required | A vault file |
| `VERSION` | argument | text | required | The version (from `history`) |

## vault show

```sh
coffer vault show [OPTIONS] PATH VERSION
```

Print a file's content as one version left it.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `PATH` | argument | text | required | A vault file |
| `VERSION` | argument | text | required | The version (from `history`) |
| `--json` | option | flag |  | JSON output for scripts |

## vault restore

```sh
coffer vault restore [OPTIONS] PATH VERSION
```

Put one version back, as a new version. A folder is restored whole: files the version did not have are removed.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `PATH` | argument | text | required | A vault file, or a folder ending in / |
| `VERSION` | argument | text | required | The version to put back (from `history`) |
| `--yes, -y` | option | flag |  | Do not ask |

## vault problems

```sh
coffer vault problems [OPTIONS]
```

List hand edits that were refused: still on disk, not in effect until fixed.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output for scripts |
