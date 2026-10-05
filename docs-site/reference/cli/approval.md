---
title: coffer approval
description: "Secret approvals: list, show, approve with Touch ID, reject."
pageClass: cli-ref
---

# coffer approval

Secret approvals: list, show, approve with Touch ID, reject.

```sh
coffer approval [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer approval --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`approval list`](#approval-list) | Approvals, newest first (pending ones by default). |
| [`approval show`](#approval-show) | One approval: what it sends, to which destination and target, and its state. |
| [`approval approve`](#approval-approve) | Approve with the person's own presence check, in the desktop app. |
| [`approval reject`](#approval-reject) | Refuse approvals. |

## approval list

Approvals, newest first (pending ones by default).

<p class="cli-label">Synopsis</p>

```sh
coffer approval list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--status` <span class="cli-chip">option</span> | text | `pending` | pending, approved, rejected, superseded, or all |
| `--destination` <span class="cli-chip">option</span> | text |  | A destination's uid |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## approval show

One approval: what it sends, to which destination and target, and its state.

<p class="cli-label">Synopsis</p>

```sh
coffer approval show [OPTIONS] APPROVAL_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `APPROVAL_ID` <span class="cli-chip">argument</span> | text | required |  |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## approval approve

Approve with the person's own presence check, in the desktop app.

The system prompt names each action, secret, destination and environment; the approvals are applied only after it passes, and only while each still names the target it named when asked. Exit 0 when every one is approved, 11 when the person did not confirm (cancelled, failed or timed out — they stay pending), 12 when the desktop app is not available.

<p class="cli-label">Synopsis</p>

```sh
coffer approval approve [OPTIONS] APPROVAL_IDS...
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `APPROVAL_IDS` <span class="cli-chip">argument</span> | text (variadic) | required | The approvals to approve — exactly these |
| `--timeout` <span class="cli-chip">option</span> | float | `120.0` | Seconds to wait for the person |
| `--no-launch` <span class="cli-chip">option</span> | flag |  | Do not start the desktop app |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## approval reject

Refuse approvals. Needs no presence check: refusing only narrows.

<p class="cli-label">Synopsis</p>

```sh
coffer approval reject [OPTIONS] APPROVAL_IDS...
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `APPROVAL_IDS` <span class="cli-chip">argument</span> | text (variadic) | required | The approvals to refuse |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
