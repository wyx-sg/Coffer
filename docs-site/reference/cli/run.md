---
title: coffer run
description: "Run a command with secrets set only in its environment."
pageClass: cli-ref
---

# coffer run

Run a command with secrets set only in its environment.

```sh
coffer run [OPTIONS]
```

This page matches what `coffer run --help` prints. Add `--help` to any command below to see its options in the terminal.

Only a secret granted to local programs in the Coffer app resolves; any other is refused and the request waits there. Each resolution is audited. Output is masked: exact secret values print as \*\*\*. Masking guards against accidents — a value landing in a transcript, a file or git — and does not hide a granted secret from an agent that runs the command.

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--secret` <span class="cli-chip">option</span> | text (repeatable) |  | NAME, ENV=NAME or ENV=coffer://secret/&lt;id&gt; of a standalone secret (repeatable) |
| `--env-file` <span class="cli-chip">option</span> | path |  | KEY=VALUE file; coffer://secret/&lt;name&gt; values are resolved |
| `--no-masking` <span class="cli-chip">option</span> | flag |  | Pass the child's output through unfiltered |
