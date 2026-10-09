---
title: coffer secret
description: "Secrets: list, store, delete, reveal in the app, import, approvals."
pageClass: cli-ref
---

# coffer secret

Secrets: list, store, delete, reveal in the app, import, approvals.

```sh
coffer secret [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer secret --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`secret set`](#secret-set) | Create a secret with `--name "<label>"` (and `--description`), or replace one by ref. |
| [`secret list`](#secret-list) | List every stored secret and every ref a resource cites. |
| [`secret reveal`](#secret-reveal) | Show a secret's value to the person, in the Coffer window, after Touch ID. |
| [`secret backup-key`](#secret-backup-key) | Open the master key backup in the Coffer app; the person checks presence, types the passphrase and picks the folder there. |
| [`secret import-key`](#secret-import-key) | Open the master key import in the Coffer app; the person picks the backup file, types its passphrase and checks presence there. |
| [`secret delete`](#secret-delete) | Delete a secret nothing uses any more. |
| [`secret describe`](#secret-describe) | Label and describe a secret. |
| [`secret scan`](#secret-scan) | Find plaintext secrets in skills and MCP servers (values are never shown). |
| [`secret import`](#secret-import) | Move found plaintext secrets into the store. |
| [`secret ignore`](#secret-ignore) | Remember found values as not secrets, so scans stop reporting them. |
| [`secret unignore`](#secret-unignore) | Forget values remembered as not secrets. |
| [`secret key-fingerprint`](#secret-key-fingerprint) | This machine's master key fingerprint (never the key). |
| [`secret key-preview`](#secret-key-preview) | Whose key a key backup holds, beside this machine's; changes nothing. |
| [`secret key-install`](#secret-key-install) | The request the Coffer app sends to install a key backup. |
| [`secret local-access`](#secret-local-access) | Hand a standalone secret to programs `coffer run` starts. |
| [`secret local-access request`](#secret-local-access-request) | Ask to hand a secret to programs coffer run starts; waits for approval. |
| [`secret local-access revoke`](#secret-local-access-revoke) | Withdraw the grant. |

## secret set

Create a secret with `--name "<label>"` (and `--description`), or replace one by ref.

A new secret is given a label by you and an id by Coffer: the command prints its ref and `coffer://secret/<id>`, which is how files cite it. `coffer secret set <ref>` only replaces the value of a secret that exists.

Without --value the secret is read from stdin, or prompted for. --value still stores, but warns that the value lands in your shell history; the value itself is never echoed. --json prints the ref and its URI (and the --value warning), never the value; a failure is the shared JSON error.

<p class="cli-label">Synopsis</p>

```sh
coffer secret set [OPTIONS] [REF]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `REF` <span class="cli-chip">argument</span> | text |  | An existing secret's reference, to replace its value |
| `--name` <span class="cli-chip">option</span> | text |  | Create a new secret with this label; Coffer mints its id |
| `--description` <span class="cli-chip">option</span> | text |  | With --name: what the new secret is for |
| `--value` <span class="cli-chip">option</span> | text |  | Provide the secret on the command line (UNSAFE — visible in shell history; prefer stdin) |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

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

## secret reveal

Show a secret's value to the person, in the Coffer window, after Touch ID.

The value never reaches this command, its output or any log.

<p class="cli-label">Synopsis</p>

```sh
coffer secret reveal [OPTIONS] REF
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `REF` <span class="cli-chip">argument</span> | text | required | The secret's ref (coffer secret list) |
| `--timeout` <span class="cli-chip">option</span> | float | `120.0` | Seconds to wait for the app and the person |
| `--no-launch` <span class="cli-chip">option</span> | flag |  | Do not start the desktop app |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## secret backup-key

Open the master key backup in the Coffer app; the person checks presence, types the passphrase and picks the folder there.

Waits until the person has written the backup, then prints where (exit 0); closing the dialog, or no backup by --timeout, exits 11 with nothing written. The path is the one the daemon wrote, reported by the app.

<p class="cli-label">Synopsis</p>

```sh
coffer secret backup-key [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--timeout` <span class="cli-chip">option</span> | float | `600.0` | Seconds to wait for the person |
| `--no-launch` <span class="cli-chip">option</span> | flag |  | Do not start the desktop app |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## secret import-key

Open the master key import in the Coffer app; the person picks the backup file, types its passphrase and checks presence there.

<p class="cli-label">Synopsis</p>

```sh
coffer secret import-key [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--timeout` <span class="cli-chip">option</span> | float | `600.0` | Seconds to wait for the person |
| `--no-launch` <span class="cli-chip">option</span> | flag |  | Do not start the desktop app |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## secret delete

Delete a secret nothing uses any more.

<p class="cli-label">Synopsis</p>

```sh
coffer secret delete [OPTIONS] REF
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `REF` <span class="cli-chip">argument</span> | text | required | ref |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## secret describe

Label and describe a secret. Body: ref, label, description.

<p class="cli-label">Synopsis</p>

```sh
coffer secret describe [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## secret scan

Find plaintext secrets in skills and MCP servers (values are never shown).

<p class="cli-label">Synopsis</p>

```sh
coffer secret scan [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## secret import

Move found plaintext secrets into the store. Body: ids, dry_run.

<p class="cli-label">Synopsis</p>

```sh
coffer secret import [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## secret ignore

Remember found values as not secrets, so scans stop reporting them. Body: ids.

<p class="cli-label">Synopsis</p>

```sh
coffer secret ignore [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## secret unignore

Forget values remembered as not secrets. Body: ids.

<p class="cli-label">Synopsis</p>

```sh
coffer secret unignore [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## secret key-fingerprint

This machine's master key fingerprint (never the key).

<p class="cli-label">Synopsis</p>

```sh
coffer secret key-fingerprint [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## secret key-preview

Whose key a key backup holds, beside this machine's; changes nothing. Body: material (read from a file with --data @backup.json).

<p class="cli-label">Synopsis</p>

```sh
coffer secret key-preview [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## secret key-install

The request the Coffer app sends to install a key backup. Body: material, passphrase, nonce, signature, where nonce and signature are the presence grant the app signs after its own Touch ID check; the command line cannot get one, and without it nothing is installed. To import a key, run `coffer secret import-key`, which opens the import in the app.

<p class="cli-label">Synopsis</p>

```sh
coffer secret key-install [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## secret local-access

Hand a standalone secret to programs `coffer run` starts.

<p class="cli-label">Synopsis</p>

```sh
coffer secret local-access [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `request`, `revoke`.

## secret local-access request

Ask to hand a secret to programs coffer run starts; waits for approval. Body: name.

<p class="cli-label">Synopsis</p>

```sh
coffer secret local-access request [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## secret local-access revoke

Withdraw the grant. Body: name.

<p class="cli-label">Synopsis</p>

```sh
coffer secret local-access revoke [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--data, -d` <span class="cli-chip">option</span> | text |  | Request body: JSON text, @path to read a file, or - to read stdin. |
| `--set` <span class="cli-chip">option</span> | text (repeatable) |  | Set one body field: key=value (dotted keys nest; the value is JSON when it parses). |
| `--json` <span class="cli-chip">option</span> | flag |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
