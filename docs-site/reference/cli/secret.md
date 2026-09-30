---
title: coffer secret
description: "Manage encrypted secrets."
---

# coffer secret

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer secret [OPTIONS] COMMAND [ARGS]...
```

Manage encrypted secrets.

## secret set

```sh
coffer secret set [OPTIONS] REF
```

Store a secret in the encrypted secret store (via the daemon).

Without --value the secret is read from stdin, or prompted for. --value still stores, but warns that the value lands in your shell history; the value itself is never echoed.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `REF` | argument | text | required | Secret reference key |
| `--value` | option | text |  | Provide the secret on the command line (UNSAFE — visible in shell history; prefer stdin) |
| `--wait` | option | flag |  | Wait for approval in the Coffer app instead of exiting |

## secret get

```sh
coffer secret get [OPTIONS] REF
```

Check that a secret is stored, without its value.

Prints [redacted] when it is, exits 4 when it is not. No value leaves the daemon and nothing is audited. To see a value, open the Coffer desktop app: it asks for Touch ID or your password each time.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `REF` | argument | text | required | Secret reference key |
| `--json` | option | flag |  | JSON output for scripts |

## secret list

```sh
coffer secret list [OPTIONS]
```

List every stored secret and every ref a resource cites.

Shows whether the store holds each one, what uses it (resources, skills citing coffer://secret/&lt;name&gt;), unreferenced ones, and whether another process on this Mac can read it where Coffer puts it. No value crosses the API.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output for scripts |

## secret rm

```sh
coffer secret rm [OPTIONS] REF
```

Delete a secret from the encrypted secret store (via the daemon).

Asks first unless --force is given.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `REF` | argument | text | required | Secret reference key |
| `--force, -f` | option | flag |  | Skip confirmation prompt |

## secret approvals

```sh
coffer secret approvals [OPTIONS]
```

List what waits for approval in the Coffer app.

Approving takes Touch ID or your password in the desktop app; the terminal can only list and reject.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--all` | option | flag |  | Include decided approvals |
| `--json` | option | flag |  | JSON output for scripts |

## secret reject

```sh
coffer secret reject [OPTIONS] APPROVAL_ID
```

Refuse a pending approval. Refusing needs no presence check.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `APPROVAL_ID` | argument | text | required | Approval id (see `coffer secret approvals`) |

## secret scan

```sh
coffer secret scan [OPTIONS]
```

Find plaintext secrets in ~/.coffer/secrets/ and in your skills.

Prints where each one is and the name it would get — never the value. Move them into the encrypted store with `coffer secret import`.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output for scripts |
| `--prompt` | option | flag |  | Print the prompt that hands rewriting skills still reading ~/.coffer/secrets/ to an agent |

## secret import

```sh
coffer secret import [OPTIONS]
```

Move plaintext secrets into the encrypted store, leaving references.

Each value is stored as coffer://secret/&lt;name&gt;, read back and compared, and only then replaced in its file by the reference. No plaintext backup is kept.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--id` | option | text (repeatable) |  | Only this finding (repeatable; default: every finding) |
| `--dry-run` | option | flag |  | Print the plan and write nothing |
| `--yes, -y` | option | flag |  | Skip the confirmation prompt |
