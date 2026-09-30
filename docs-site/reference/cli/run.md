---
title: coffer run
description: "Run a command with secrets set only in its environment."
---

# coffer run

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer run [OPTIONS]
```

Run a command with secrets set only in its environment.

Each resolution is audited. Output is masked: exact secret values print as \*\*\*. This guards against accidents — a value landing in a transcript, a file or git — and does not hide a secret from an agent that runs the command: the agent is the command's parent and can read its environment.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--secret` | option | text (repeatable) |  | NAME or ENV=NAME of a standalone secret (repeatable) |
| `--env-file` | option | path |  | KEY=VALUE file; coffer://secret/&lt;name&gt; values are resolved |
| `--no-masking` | option | flag |  | Pass the child's output through unfiltered |
