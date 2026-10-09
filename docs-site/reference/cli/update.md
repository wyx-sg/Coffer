---
title: coffer update
description: "Upgrade Coffer to the newest release and restart the daemon on it."
pageClass: cli-ref
---

# coffer update

Upgrade Coffer to the newest release and restart the daemon on it.

```sh
coffer update [OPTIONS]
```

This page matches what `coffer update --help` prints. Add `--help` to any command below to see its options in the terminal.

The installer's binaries are downloaded, checked against the release's SHA256SUMS and swapped in place; the desktop app installs its own signed update; a source checkout is upgraded with git.

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--check` <span class="cli-chip">option</span> | flag |  | Only say whether a newer release exists |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
