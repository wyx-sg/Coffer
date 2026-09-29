---
title: Secrets
description: How Coffer keeps secrets from the agents it serves — plaintext only in the desktop app, approval before a secret goes somewhere new — and how to store standalone secrets, run commands with them through coffer run, answer approvals, list what uses a secret, move plaintext files into the store, and back up the master key.
---

# Secrets

Coffer holds secrets for your agents, and your agents run as you. This page explains the line Coffer draws between the two, and how to work with it day to day: storing a secret that belongs to no resource, running a command with it, answering the approvals Coffer asks for, finding what uses a secret, moving plaintext secret files into the store, and backing up the master key.

For storing, citing, rotating and deleting a resource's credentials — an MCP server's token, a provider key — see [Credentials](/guides/credentials). The threat model behind all of this is on [Security model](/architecture/security).

## The idea in plain words

A coding agent can read a hostile web page, issue or README and start following the instructions in it. Such an agent runs with your shell: it can read your files, run `coffer`, and call Coffer's API exactly as you can. Coffer does not try to stop it from configuring Coffer — setting Coffer up for you is part of an agent's job. It protects the **secret** instead:

1. **Only you, at the desktop app, see a secret's value.** No command, REST route or MCP tool returns a stored value or the master key. Revealing or copying a value, and backing up the master key, happen only in the desktop app, each after its own Touch ID or login-password check. The next reveal asks again.
2. **A secret goes somewhere new only after you approve it.** Sending an existing secret to a place it has not gone before — a new MCP server, a changed command line, another git remote — waits for you to approve it in the desktop app. Until then nothing is sent.
3. **Switching these protections off also takes you, at the desktop app.** No environment variable, config file or flag does it.
4. **Agents get capabilities, not keys.** The gateway puts an HTTP server's token into the request itself, so the agent sees the tool's results and never the token.

Writing a secret stays open to every surface: whoever supplies a value already has it.

::: danger Only a signed release holds this boundary
Coffer does not yet ship binaries signed with an Apple Developer ID. Until it does, every build is a **development build**: the master key is the file `~/.coffer/master.key`, which any program running as you can read, and with it a program can forge the desktop app's approval. The commands and approvals on this page work the same way in a development build, and the desktop app labels every prompt "Development build", but they do not stop a determined agent there. See [Security model → Development builds](/architecture/security#development-builds).
:::

## Standalone secrets

Most secrets belong to a resource and are stored by the dialog that registers it. A **standalone secret** belongs to no resource: the database password a skill's script needs, an internal API token you use from the terminal. It lives in the same encrypted store under `secret/<name>`, and files cite it as `coffer://secret/<name>`.

A name is one segment of letters, digits, `.`, `_` and `-`, at most 64 characters. It is fixed once created, because it is quoted in files Coffer cannot see: to rename, store it under the new name and delete the old one.

### Store one

```sh
# From stdin, so the value never reaches your shell history
printf '%s' "$ORDERS_DB_PASSWORD" | coffer credentials set secret/orders-db

# Or at a hidden prompt
coffer credentials set secret/orders-db
```

Storing a new name takes effect at once. Replacing the value of a standalone secret that already exists [waits for your approval](#replacing-a-value-in-use).

### Cite it

Wherever a skill or a project needs the secret, write its reference instead of its value:

```sh
# connection.env, next to a skill's script
DB_HOST=db.internal
DB_USER=orders_ro
DB_PASSWORD=coffer://secret/orders-db
```

A skill's `connection.md` names it the same way. A file holding only references is safe to commit and safe to sync. Nothing reads it by itself: [`coffer run`](#run-a-command-with-a-secret) resolves the references when a command starts.

A resource can cite a standalone secret too, as `secret/<name>` in its credential refs, like any other ref.

## Run a command with a secret

`coffer run` resolves standalone secrets through the daemon and starts one command with the values set **only in that command's environment**:

```sh
coffer run --secret orders-db -- psql -h db.internal orders          # $ORDERS_DB
coffer run --secret PGPASSWORD=orders-db -- psql -h db.internal orders
coffer run --env-file connection.env -- ./query.sh
```

| Option | Meaning |
| --- | --- |
| `--secret NAME` | Set `secret/NAME` as the variable `NAME`, upper-cased with `-` and `.` turned into `_` (`orders-db` becomes `ORDERS_DB`). Repeatable. |
| `--secret ENV=NAME` | Set `secret/NAME` as the variable `ENV`. |
| `--env-file FILE` | Read `KEY=VALUE` lines. Plain values are passed through; each `coffer://secret/<name>` value is resolved. |
| `--no-masking` | Pass the command's output through untouched, for tools that need a real terminal. |

A `coffer://secret/<name>` value already in `coffer run`'s own environment is resolved too, so a wrapper script can export the references once. Everything after `--` is the command and its arguments.

What happens:

- **Only standalone secrets resolve.** A name must be stored under `secret/`; a resource's credential can never be fetched this way. An unknown name fails with `SECRET_NOT_FOUND` and the command does not start.
- **The values go to the child only.** The shell that ran `coffer run` does not get them, and neither do its other children.
- **Output is masked.** Every exact occurrence of a value in the command's standard output and error prints as `***`, even when it is split across two writes. Values shorter than 8 characters are not masked — masking a short value would shred ordinary output — and `coffer run` says so when it skips one.
- **The exit status passes through**, so `coffer run` fits into scripts. A command killed by a signal exits `128 + signal`; a command that cannot start exits `127`. `Ctrl-C` and `SIGTERM` are forwarded to the command.
- **Every resolve is audited** as `secret_resolved`, naming the secret, the program and the working directory — never the value, and never the rest of the command line, which might carry a secret of its own. Read them with `coffer log audit --event-type secret_resolved`.

::: warning `coffer run` guards against accidents, not against an agent
`coffer run` keeps a secret out of files, git, the agent's own environment and transcripts **by accident**. It does **not** hide the secret from an agent that runs the command: the agent is the command's parent, so it can read the child's environment (`ps eww`), run `coffer run --secret orders-db -- env`, or print the value base64-encoded, which masking does not recognise. Masking also never sees what the command writes to files. Every standalone secret is listed as readable by local processes for this reason.
:::

## See or copy a value

Open the secret in the **desktop app** and choose reveal or copy. macOS asks for Touch ID or your login password, and the prompt names the secret. Each reveal asks again; there is no window during which a second one is free. The reveal is audited as `credential_revealed` with the ref only.

The browser UI offers no reveal: it shows **Open in Coffer app** in its place. `coffer credentials get <ref>` only confirms that a value is stored.

## Approvals

An approval is a change that would widen where a secret goes, held until you answer it in the desktop app.

### What asks for approval

| You, or an agent, do this | What waits |
| --- | --- |
| Register a resource that cites a secret already sent somewhere else, such as a second MCP server using the same token. | The new server gets no secret until you approve. The first keeps working. |
| Change where a resource sends a secret: a stdio server's command, arguments, working directory or other environment; an HTTP server's URL; a SeaTalk channel's app. | The resource gets no secret until you approve the new target. |
| Point the sync remote's push token at a different URL. | The remote is not saved until you approve. |
| Store a new value for a ref something already receives, or for any standalone secret. | The old value stays in use; the new one waits encrypted. |
| `coffer config set secrets.require_approval off` | The protection stays on until you approve. |

What counts is the **target** — the thing that actually receives the value, written so you can judge it: a stdio server's whole command line with its working directory and other environment variables (a variable such as `NODE_OPTIONS=--require …` changes what the process does), an HTTP server's URL, a git remote's URL, a channel's bot or app. An approval reads, for example:

```text
send secret 'github/token' to mcp_server 'gh-work' (GITHUB_TOKEN) at stdio npx -y @modelcontextprotocol/server-github
```

Approve only a target you recognise. A command line you did not write, pointing at a script in a temporary directory, is exactly what an injected agent would register.

### What needs no approval

- **A secret you just supplied for it.** A value stored within the last five minutes under a ref that has never been sent anywhere is used at once. This is what every "add" dialog and `coffer mcp add` with a pasted token do, seconds apart. It does not apply to standalone secrets or to an older secret.
- **Everything that already worked when you upgraded.** The first time a daemon with approvals starts, every secret already in use is approved once for its current target.
- **Anything, while the protection is off.**

A binding is checked at the moment of use — when a server starts, a channel connects, a sync round pushes — so a change that arrives behind Coffer's back, such as a vault file edited by hand or a server another machine synced in, is caught too.

### Answering one

When something waits, the desktop app posts a notification, **Coffer needs your approval**, naming the change, and opens a sheet listing what waits. Approve runs Touch ID or your login password, with a prompt that names the change, then applies it; the server, channel or remote picks the secret up on its next attempt, with no restart. Reject needs no presence check, since refusing only narrows what Coffer does.

In a browser, the page offers **Open in Coffer app** where the approve button would be.

From a terminal you can list and reject, never approve:

```sh
coffer credentials approvals              # what waits now
coffer credentials approvals --all        # decided ones too; --json for scripts
coffer credentials reject <id>
```

An approval ends as `approved`, `rejected`, or `superseded` — when the resource it was for was deleted or has since moved to another target, which raises a fresh approval of its own.

### On the command line

A command whose change waits — `coffer mcp add`, any `coffer <kind> edit`, `coffer channel add`, `coffer sync remote set`, `coffer credentials set`, `coffer config set secrets.require_approval off` — saves what it can, prints what waits and exits `9`:

```text
$ coffer mcp add gh-work --stdio "npx -y @modelcontextprotocol/server-github" --credential GITHUB_TOKEN=github/token
waiting for approval in the Coffer app: send secret 'github/token' to mcp_server 'gh-work' (GITHUB_TOKEN) at stdio npx -y @modelcontextprotocol/server-github (approval 3f9c0a7d12e45b68)
$ echo $?
9
```

Add `--wait` to keep the command running until you answer in the app: it exits `0` once approved and non-zero once rejected, and gives up after ten minutes, leaving the approval in the app. `coffer config set` has no `--wait`; approve in the app and check with `coffer config get secrets.require_approval`.

An agent that hits exit `9` should tell you what it registered and that it waits for you, not retry.

### Replacing a value in use

`coffer credentials set` on a ref that an approved destination receives, or on any standalone secret, answers with a pending approval instead of replacing the value. Until you approve, everything keeps using the old value; the new one is held encrypted and is dropped if you reject. A new ref, or one nothing receives, is stored at once.

### Switching the protection off

`secrets.require_approval` is on by default. Turning it on takes effect at once. Turning it off waits for an approval in the desktop app, and while it is off every new destination is approved without asking. Nothing else — no environment variable, file or flag — switches it off.

```sh
coffer config get secrets.require_approval      # on
coffer config set secrets.require_approval off  # exits 9 until approved in the app
coffer config set secrets.require_approval on   # at once
```

## List your secrets

```sh
coffer credentials list
```

The list has every ref the store holds and every ref a resource cites, with what uses each one — resources, skills whose files cite `coffer://secret/<name>`, destinations waiting for approval — and `(unreferenced)` for a secret nothing uses. **Readable by local processes** is `yes` where another program running as you can read the value where Coffer puts it: every standalone secret (it goes into a `coffer run` child) and every secret in a stdio MCP server's environment. See [Credentials → List and inspect](/guides/credentials#list-and-inspect) for the columns.

Deleting a standalone secret is refused while a resource cites it or a skill's files cite its URI; the message names them.

## Move plaintext secret files into the store

Earlier advice kept skill secrets in plaintext files such as `~/.coffer/secrets/<name>.env`. Any program that walks your home directory reads those — backup tools, a cloud-drive client, an agent's file search. `coffer credentials scan` finds them, and `coffer credentials import` moves them into the store:

```sh
coffer credentials scan
```

The scan reads `~/.coffer/secrets/*.env` (`KEY=VALUE` lines) and `*.json` (a flat map of strings), and every text file in your managed skills (assignments whose name says password, secret, token or key, and well-known token shapes). For each finding it prints the file, line, key and the standalone name it would get, such as `coffer://secret/db.PASSWORD` — never the value. It also names every skill that still reads a file under `~/.coffer/secrets/`, so you can move its command to `coffer run --env-file`.

```sh
coffer credentials import --dry-run     # print the plan, write nothing
coffer credentials import               # move every finding (asks first; --yes skips)
coffer credentials import --id <id>     # only this finding (repeatable)
```

For each finding the import stores the value as `secret/<name>`, reads it back and compares, and only then replaces the value in its file with `coffer://secret/<name>`, atomically and keeping the file's mode. A name that already holds a different value is skipped and its file left untouched. No plaintext backup is kept. Each move is audited as `secret_imported`.

Then change the skill's commands to run under `coffer run`, for example `coffer run --env-file ~/.coffer/secrets/db.env -- ./query.sh`.

## The master key and its backup

Every secret is encrypted with one master key. How it is kept depends on the build:

- **A signed release** keeps it in a Keychain item only Coffer's signed binaries can read. No other program gets access, or a dialog to click. The daemon reads it without asking, so it starts unattended after a crash or at login.
- **A development build** keeps it in `~/.coffer/master.key` (or the OS keychain, opt-in), readable by any program running as you.

Presence checks guard what lets plaintext out, not the key itself: that is why the daemon never waits for you.

**Back up the key in the desktop app**: pick a folder, confirm with Touch ID or your login password, and the app writes `coffer-master-key-<fingerprint>.key` there with mode `0600`, audited as `master_key_exported`. No command or browser page can do it. Install the backup on another machine with `coffer sync key import <file>` — see [Credentials → Carry the key to another machine](/guides/credentials#carry-the-key-to-another-machine). In a signed release the Keychain is the only copy, so make a backup.

## Related

- [Credentials](/guides/credentials) — storing, citing, rotating and deleting a resource's secrets
- [Security model](/architecture/security) — the threat model, and what stays exposed
- [Desktop app](/guides/desktop-app) — where reveals, key backups and approvals happen
- [Writing skill libraries](/guides/writing-skill-libraries) — citing secrets from a skill
- [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)
- [Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/standalone-secrets-are-named-references-injected-into-one-child.md)
- Spec: [credentials](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/credentials/spec.md)
