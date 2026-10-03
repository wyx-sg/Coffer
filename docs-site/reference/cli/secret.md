---
title: coffer secret
description: "Manage encrypted secrets."
pageClass: cli-ref
---

# coffer secret

Manage encrypted secrets.

```sh
coffer secret [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer secret --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`secret set`](#secret-set) | Store a secret in the encrypted secret store (via the daemon). |
| [`secret get`](#secret-get) | Check that a secret is stored, without its value. |
| [`secret list`](#secret-list) | List every stored secret and every ref a resource cites. |
| [`secret rm`](#secret-rm) | Delete a secret from the encrypted secret store (via the daemon). |
| [`secret approvals`](#secret-approvals) | List what waits for approval in the Coffer app. |
| [`secret reject`](#secret-reject) | Refuse a pending approval. |
| [`secret scan`](#secret-scan) | Find plaintext secrets in ~/.coffer/secrets/ and in your skills. |
| [`secret import`](#secret-import) | Move plaintext secrets into the encrypted store, leaving references. |

## secret set

Store a secret in the encrypted secret store (via the daemon).

Without --value the secret is read from stdin, or prompted for. --value still stores, but warns that the value lands in your shell history; the value itself is never echoed.

<p class="cli-label">Synopsis</p>

```sh
coffer secret set [OPTIONS] REF
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `REF` <span class="cli-chip">argument</span> | text | required | Secret reference key |
| `--value` <span class="cli-chip">option</span> | text |  | Provide the secret on the command line (UNSAFE — visible in shell history; prefer stdin) |
| `--wait` <span class="cli-chip">option</span> | flag |  | Wait for approval in the Coffer app instead of exiting |

## secret get

Check that a secret is stored, without its value.

Prints [redacted] when it is, exits 4 when it is not. No value leaves the daemon and nothing is audited. To see a value, open the Coffer desktop app: it asks for Touch ID or your password each time.

<p class="cli-label">Synopsis</p>

```sh
coffer secret get [OPTIONS] REF
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `REF` <span class="cli-chip">argument</span> | text | required | Secret reference key |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## secret list

List every stored secret and every ref a resource cites.

Shows whether the store holds each one, what uses it (resources, skills citing coffer://secret/&lt;name&gt;), unreferenced ones, and whether another process on this Mac can read it where Coffer puts it. No value crosses the API.

<p class="cli-label">Synopsis</p>

```sh
coffer secret list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## secret rm

Delete a secret from the encrypted secret store (via the daemon).

Asks first unless --force is given.

<p class="cli-label">Synopsis</p>

```sh
coffer secret rm [OPTIONS] REF
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `REF` <span class="cli-chip">argument</span> | text | required | Secret reference key |
| `--force, -f` <span class="cli-chip">option</span> | flag |  | Skip confirmation prompt |

## secret approvals

List what waits for approval in the Coffer app.

Approving takes Touch ID or your password in the desktop app; the terminal can only list and reject.

<p class="cli-label">Synopsis</p>

```sh
coffer secret approvals [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--all` <span class="cli-chip">option</span> | flag |  | Include decided approvals |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## secret reject

Refuse a pending approval. Refusing needs no presence check.

<p class="cli-label">Synopsis</p>

```sh
coffer secret reject [OPTIONS] APPROVAL_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `APPROVAL_ID` <span class="cli-chip">argument</span> | text | required | Approval id (see `coffer secret approvals`) |

## secret scan

Find plaintext secrets in ~/.coffer/secrets/ and in your skills.

Prints where each one is and the name it would get — never the value. Move them into the encrypted store with `coffer secret import`.

<p class="cli-label">Synopsis</p>

```sh
coffer secret scan [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |
| `--prompt` <span class="cli-chip">option</span> | flag |  | Print the prompt that hands rewriting skills still reading ~/.coffer/secrets/ to an agent |

## secret import

Move plaintext secrets into the encrypted store, leaving references.

Each value is stored as coffer://secret/&lt;name&gt;, read back and compared, and only then replaced in its file by the reference. No plaintext backup is kept.

<p class="cli-label">Synopsis</p>

```sh
coffer secret import [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--id` <span class="cli-chip">option</span> | text (repeatable) |  | Only this finding (repeatable; default: every finding) |
| `--dry-run` <span class="cli-chip">option</span> | flag |  | Print the plan and write nothing |
| `--yes, -y` <span class="cli-chip">option</span> | flag |  | Skip the confirmation prompt |
