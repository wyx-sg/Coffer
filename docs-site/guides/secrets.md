---
title: Secrets
description: How Coffer keeps secrets from the agents it serves — plaintext only in the desktop app, approval before a secret goes somewhere new — and how to use the Secrets page, store standalone secrets, run commands with them through coffer run, answer approvals, list what uses a secret, move plaintext files into the store, and back up the master key.
---

# Secrets

Coffer holds secrets for your agents, and your agents run as you. This page explains the line Coffer draws between the two, and how to work with it day to day: storing a secret that belongs to no resource, running a command with it, answering the approvals Coffer asks for, finding what uses a secret, moving plaintext secret files into the store, and backing up the master key.

For storing, citing, rotating and deleting a resource's secrets — an MCP server's token, a provider key — see [Secret store](/guides/secret-store). The threat model behind all of this is on [Security model](/architecture/security).

## The idea in plain words

A coding agent can read a hostile web page, issue or README and start following the instructions in it. Such an agent runs with your shell: it can read your files, run `coffer`, and call Coffer's API exactly as you can. Coffer does not try to stop it from configuring Coffer — setting Coffer up for you is part of an agent's job. It protects the **secret** instead:

1. **Only you, at the desktop app, see a secret's value.** No command, REST route or MCP tool returns a stored value or the master key. Revealing or copying a value, and backing up the master key, happen only in the desktop app, each after its own Touch ID or login-password check. The next reveal asks again.
2. **A secret goes somewhere new only after you approve it.** Sending an existing secret to a place it has not gone before — a new MCP server, a changed command line, another git remote — waits for you to approve it in the desktop app. Until then nothing is sent.
3. **Switching these protections off also takes you, at the desktop app.** No environment variable, config file or flag does it.
4. **Agents get capabilities, not keys.** The gateway puts an HTTP server's token into the request itself, so the agent sees the tool's results and never the token.

Writing a resource's secret stays open to every surface: whoever supplies a value already has it. Adding a standalone secret, or a new value for one in use, waits for your approval.

::: danger Only a signed release holds this boundary
Coffer does not yet ship binaries signed with an Apple Developer ID. Until it does, every build is a **development build**: the master key is the file `~/.coffer/master.key`, which any program running as you can read, and with it a program can forge the desktop app's approval. The commands and approvals on this page work the same way in a development build, and the desktop app labels every prompt "Development build", but they do not stop a determined agent there. See [Security model → Development builds](/architecture/security#development-builds).
:::

## The Secrets page

**Secrets** in the sidebar's System group (`/secrets`) is the one place in the web UI that lists and manages stored secrets. Secrets come only from Coffer: a secret field inside a resource's own dialog — an MCP server's token, a provider's key — either picks a stored secret from this page or takes a pasted value and saves it here with the form, and a header or environment row is plain text with a 🔑 button at the end of the field that picks a stored secret instead. A value pasted into a plain row that looks like a secret offers to be stored. Nothing secret sits in a resource's own settings, only the secret's name. This page is where you see all of them together and what each one is for.

The list is one table, sorted by name. **Find a secret** (or `/`) filters it by name, and the **Status** pill narrows it to **All**, **In use** (something cites the secret) or **Not used** (nothing cites it, so it is safe to delete). The **Name** column shows a standalone secret by its name and any other secret by its ref, such as `mcp_server/…/GITHUB_TOKEN`. **Waiting for approval** marks a secret whose new value or new destination waits for you in the desktop app, and a terminal icon marks one that other programs running as you can read where Coffer puts it. **Used by** names the things that use the secret (the first two, then "+1"), or **Nothing**.

Each row also says when the secret was **last used** on this Mac (when something last had its value decrypted to use it, such as a server starting or `coffer run`; revealing it does not count), as a relative time such as "3 h ago" and, past a week, a date such as "Aug 12", and when it was **created**. A secret never used here reads **Never**.

To delete several at once, tick rows (or the header checkbox for the whole list); a bar over the table reads "3 of 8 selected" with **Delete…**, and **Esc** clears the selection. The confirmation names the secrets it will delete and says which selected ones it skips because they are in use or waiting for approval.

### Missing on this Mac

A row reads **Missing on this Mac** when this Mac has no value to hand out for it: a resource or skill cites it but it was never stored here, or its encrypted value came with the vault from another Mac whose master key this one does not have (encrypted secrets don't sync by default). Whatever uses it cannot start until it has a value. The row's **Add value** stores one; like any write it may [wait for your approval](#approvals). While any secret is missing, a banner at the top counts them ("3 secrets have no value on this Mac"), names them, and offers **Add values**: one dialog with a field per missing secret, where a field left empty stays missing and **Save N values** stores the rest. The same count appears on [Overview](/guides/web-ui#overview), whose button opens this page. The other way to open every secret at once is the other Mac's master key, which is imported in the [vault sync](/guides/vault-sync) join flow or in Settings › Security, not on this page. Coffer finds a secret it cannot open by checking the encrypted value's signature against this Mac's key, without decrypting anything.

Choosing **Used by** opens the list of what uses the secret, each by kind (MCP server, model provider, channel, skill, …) and current name; choosing a name opens that thing's page.

Each row's **⋯** menu:

| Item | What it does |
| --- | --- |
| **Replace value…** | Takes a new value without ever showing the old one. The dialog names what uses the secret. A value something already receives, and any standalone secret's, [waits for your approval](#replacing-a-value-in-use); the page then says "Saved, waiting for approval" instead of claiming it took effect. For a secret [missing on this Mac](#missing-on-this-mac) the item reads **Add value…**. |
| **Reveal value…** | Only in the desktop app — see [See or copy a value](#see-or-copy-a-value). A browser shows it disabled as **Reveal in the Coffer app**. |
| **Copy reference (…)** | Copies what a file or config cites, shown in the item: `coffer://secret/<name>` for a standalone secret, the ref otherwise. |
| **View in Activity** | Opens the Changes tab of [Activity](/guides/activity), where every store, replace, reveal and delete is recorded. |
| **Delete…** | For a secret nothing uses, asks once, saying when it was last used, and deletes it — on this Mac and, if encrypted secrets sync, on your other Macs at their next round. For one in use, it deletes nothing: the dialog lists each thing that still uses it, with **Open** to go there, and the row stays. |

**Add secret** adds a new standalone secret: a name (letters, digits, `.`, `_` and `-`, at most 64, fixed once added) and a value, which is never shown back. A name that already exists is caught before anything is sent, with a link to replace that secret's value instead. The dialog shows the reference to cite. A new secret [waits for your approval](#approvals) before it exists: the value is held encrypted, and the approvals window asks "Approve the new secret …?".

To use a stored secret in a command, see [Run a command with a secret](#run-a-command-with-a-secret).

**Find plaintext keys** runs the [plaintext scan](#move-plaintext-secret-files-into-the-store) from the page. It lists each key it found by file, line, key and the secret name it would get — never the value — with every finding ticked. Untick what should stay, then **Review changes**: Coffer works out what the import would do without writing anything, and shows the secrets it would add and the files it would change. **Apply** moves them. A name that already holds a different value is skipped with its file untouched. A file Coffer cannot rewrite — in a read-only folder, say — keeps its key: the value is saved as the secret all the same, but the file still holds it in plain text, and the dialog says "Moved 2 of 3 keys", names the file and offers **Try again**. A scan that finds nothing says how many files it read. Skills that still point at `~/.coffer/secrets/` are listed too, for you to update by hand — or to hand to your agent with **Ask an agent** (**Copy prompt** in its menu) beside the list. The prompt names each skill, file and line and the secret names the keys become, asks the agent to rewrite the commands to use `coffer run` and show you the diff, and never carries a value.

While any change waits for approval, a banner at the top says how many ("1 change waiting for approval") and what approving takes here (Touch ID or your login password in the desktop app; in a browser, the desktop app), with **Review** to reopen the approvals dialog. Overview carries the same item, and its **Review** opens the same dialog. A banner's **×** ignores it, on this page and on Overview alike: the page then says "… — ignored on Overview. Show it again", and the item returns by itself when the situation changes. With no secrets at all, the page offers **Add secret** and **Find plaintext keys**.

## Standalone secrets

Most secrets belong to a resource and are stored by the dialog that registers it. A **standalone secret** belongs to no resource: the database password a skill's script needs, an internal API token you use from the terminal. It lives in the same encrypted store under `secret/<name>`, and files cite it as `coffer://secret/<name>`.

A name is one segment of letters, digits, `.`, `_` and `-`, at most 64 characters. It is fixed once created, because it is quoted in files Coffer cannot see: to rename, store it under the new name and delete the old one.

### Store one

```sh
# From stdin, so the value never reaches your shell history
printf '%s' "$ORDERS_DB_PASSWORD" | coffer secret set secret/orders-db

# Or at a hidden prompt
coffer secret set secret/orders-db
```

On the [Secrets page](#the-secrets-page), **Add secret** does the same. A new name [waits for your approval](#approvals): until you approve it in the desktop app nothing is stored under the name and `coffer run` cannot resolve it; `coffer secret set` prints that it waits and exits `9` (or waits with `--wait`). Replacing the value of a standalone secret that already exists [waits for your approval](#replacing-a-value-in-use) too.

### Cite it

Wherever a skill or a project needs the secret, write its reference instead of its value:

```sh
# connection.env, next to a skill's script
DB_HOST=db.internal
DB_USER=orders_ro
DB_PASSWORD=coffer://secret/orders-db
```

A skill's `connection.md` names it the same way. A file holding only references is safe to commit and safe to sync. Nothing reads it by itself: [`coffer run`](#run-a-command-with-a-secret) resolves the references when a command starts.

A resource can cite a standalone secret too, as `secret/<name>` in its secret refs, like any other ref.

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

- **Only standalone secrets resolve.** A name must be stored under `secret/`; a resource's secret can never be fetched this way. An unknown name fails with `SECRET_NOT_FOUND` and the command does not start.
- **The values go to the child only.** The shell that ran `coffer run` does not get them, and neither do its other children.
- **Output is masked.** Every exact occurrence of a value in the command's standard output and error prints as `***`, even when it is split across two writes. Values shorter than 8 characters are not masked — masking a short value would shred ordinary output — and `coffer run` says so when it skips one.
- **The exit status passes through**, so `coffer run` fits into scripts. A command killed by a signal exits `128 + signal`; a command that cannot start exits `127`. `Ctrl-C` and `SIGTERM` are forwarded to the command.
- **Every resolve is audited** as `secret_resolved`, naming the secret, the program and the working directory — never the value, and never the rest of the command line, which might carry a secret of its own. Read them with `coffer log audit --event-type secret_resolved`.

::: warning `coffer run` guards against accidents, not against an agent
`coffer run` keeps a secret out of files, git, the agent's own environment and transcripts **by accident**. It does **not** hide the secret from an agent that runs the command: the agent is the command's parent, so it can read the child's environment (`ps eww`), run `coffer run --secret orders-db -- env`, or print the value base64-encoded, which masking does not recognise. Masking also never sees what the command writes to files. Every standalone secret is listed as readable by local processes for this reason.
:::

## See or copy a value

Open the [Secrets page](#the-secrets-page) in the **desktop app** and choose **Reveal value…** on the row. A warning comes first: anyone who can see your screen can read the value. Then macOS asks for Touch ID or your login password, and the prompt names the secret. The value shows for 30 seconds, with **Copy** and **Hide**, then hides again; closing the dialog drops it at once. Each reveal asks again; there is no window during which a second one is free. The reveal is audited as `secret_revealed` with the ref only.

The browser UI offers no reveal: the menu item reads **Reveal in the Coffer app** and is disabled. `coffer secret get <ref>` only confirms that a value is stored.

## Approvals

An approval is a change that would widen where a secret goes, held until you answer it in the desktop app.

### What asks for approval

| You, or an agent, do this | What waits |
| --- | --- |
| Register a resource that cites a secret already sent somewhere else, such as a second MCP server using the same token. | The new server gets no secret until you approve. The first keeps working. |
| Change where a resource sends a secret: a stdio server's command, arguments, working directory or other environment; an HTTP server's URL; a SeaTalk channel's app. | The resource gets no secret until you approve the new target. |
| Point the sync remote's push token at a different URL. | The remote is not saved until you approve. |
| Store a new value for a ref something already receives, or for any standalone secret. | The old value stays in use; the new one waits encrypted. |
| Add a new standalone secret. | Nothing is stored under the name until you approve; the value waits encrypted. |
| `coffer config set secrets.require_approval off` | The protection stays on until you approve. |

What counts is the **target** — the thing that actually receives the value, written so you can judge it: a stdio server's whole command line with its working directory and other environment variables (a variable such as `NODE_OPTIONS=--require …` changes what the process does), an HTTP server's URL, a git remote's URL, a channel's bot or app. An approval reads, for example:

```text
send secret 'github/token' to mcp_server 'gh-work' (GITHUB_TOKEN) at stdio npx -y @modelcontextprotocol/server-github
```

Approve only a target you recognise. A command line you did not write, pointing at a script in a temporary directory, is exactly what an injected agent would register.

### What needs no approval

- **A secret you just supplied for it.** A value stored on this machine in the last five minutes under a ref that has never been sent anywhere is approved when you register the server, channel or connection that cites it. This is what every "add" dialog and `coffer mcp add` with a pasted token do. A second place citing the same ref is a second place, and waits. It does not apply to standalone secrets.
- **Everything that already worked when you upgraded.** The first time a daemon with approvals starts, every secret already in use is approved once for its current target. The move to the vault layout (`coffer migrate`) is the exception: it carries no approvals, so each secret's first use at each destination waits once ([Upgrading](/guides/upgrading)).
- **Anything, while the protection is off.**

A binding is also checked when you register or change the place that uses it, so an approval it needs appears right when you save, with the approvals dialog opening on the page you are on. A binding is checked at the moment of use — when a server starts, a channel connects, a sync round pushes — so a change that arrives behind Coffer's back, such as a vault file edited by hand or a server another machine synced in, is caught too.

### Answering one

When something waits, the desktop app posts a notification, **Coffer needs your approval**, naming the change, and opens the approvals dialog, one table with a row per change: the kind of change (**New value**, **New secret**, **New use**, **Turn off protection**), the secret, where it goes (what uses it, or the target that receives it), who asked (**You · in the Coffer UI**, **You · on the command line**, **Through the API**) and when. With one change, **Approve…** runs Touch ID or your login password, with a prompt that names the change, then applies it; the server, channel or remote picks the secret up on its next attempt, with no restart. **Reject** needs no presence check, since refusing only narrows what Coffer does.

In a browser, **Approve** is disabled — "Approve in the Coffer desktop app" — and only **Reject** works.

### Answering several at once

When two or more changes wait — after an upgrade, say, when several destinations ask at once — the same table has a header checkbox, and nothing is ticked to begin with. Tick the changes you want to answer: the bar reads "2 of 3 selected" with **Reject 2** and **Approve 2…**, and with nothing ticked the buttons read **Reject all** and **Approve all 3…**. Pressing **Approve…** runs the presence check directly, once, and the prompt names the first few changes and counts the rest; there is no second review step, because the table already lists every change the confirmation will cover. The rows then say what became of each: **Approved**, or **Skipped**. A change whose target moved after you opened the list is skipped and keeps waiting, and so is anything no longer waiting; nothing outside the list you saw is approved. Turning the protection off is never part of a batch — approve it on its own. **Reject** needs no presence check. `coffer secret approvals` remains list-only: approving is the desktop app's.

From a terminal you can list and reject, never approve:

```sh
coffer secret approvals              # what waits now
coffer secret approvals --all        # decided ones too; --json for scripts
coffer secret reject <id>
```

Rejecting shows a toast and nothing more: the page keeps no list of refused changes and has no "Ask again". A rejection stands for that target: the secret stays withheld, and a server or command that meets it is told it was refused (`SECRET_BINDING_REJECTED`) rather than that something waits. Change the destination to put the question to you afresh. An approval ends as `approved`, `rejected`, or `superseded` — when the resource it was for was deleted or has since moved to another target, which raises a fresh approval of its own.

### On the command line

A command whose change waits — `coffer mcp add`, any `coffer <kind> edit` (including `coffer provider edit --secret` or `--base-url`), `coffer channel add`, `coffer provider add`, `coffer sync remote set`, `coffer secret set`, `coffer config set secrets.require_approval off` — saves what it can, prints what waits and exits `9`:

```text
$ coffer mcp add gh-work --stdio "npx -y @modelcontextprotocol/server-github" --secret GITHUB_TOKEN=github/token
waiting for approval in the Coffer app: send secret 'github/token' to mcp_server 'gh-work' (GITHUB_TOKEN) at stdio npx -y @modelcontextprotocol/server-github (approval 3f9c0a7d12e45b68)
$ echo $?
9
```

Add `--wait` to keep the command running until you answer in the app: it exits `0` once approved and non-zero once rejected, and gives up after ten minutes, leaving the approval in the app. `coffer config set` has no `--wait`; approve in the app and check with `coffer config get secrets.require_approval`.

An agent that hits exit `9` should tell you what it registered and that it waits for you, not retry.

### Replacing a value in use

`coffer secret set` on a ref that an approved destination receives, or on any standalone secret, answers with a pending approval instead of replacing the value. Until you approve, everything keeps using the old value; the new one is held encrypted and is dropped if you reject. A new ref, or one nothing receives, is stored at once.

### Switching the protection off

`secrets.require_approval` is on by default. Turning it on takes effect at once. Turning it off waits for an approval in the desktop app, and while it is off every new destination is approved without asking. Nothing else — no environment variable, file or flag — switches it off.

```sh
coffer config get secrets.require_approval      # on
coffer config set secrets.require_approval off  # exits 9 until approved in the app
coffer config set secrets.require_approval on   # at once
```

## List your secrets

```sh
coffer secret list
```

The [Secrets page](#the-secrets-page) shows the same list, grouped into in use and not used by anything. `--json` also carries, per secret, `locked` (stored, but this Mac's master key cannot open it), `created_at` and `last_used_at`. The list has every ref the store holds and every ref a resource cites, with what uses each one — resources, skills whose files cite `coffer://secret/<name>`, destinations waiting for approval — and `(unreferenced)` for a secret nothing uses. **Readable by local processes** is `yes` where another program running as you can read the value where Coffer puts it: every standalone secret (it goes into a `coffer run` child) and every secret in a stdio MCP server's environment. See [Secret store → List and inspect](/guides/secret-store#list-and-inspect) for the columns.

Deleting a standalone secret is refused while a resource cites it or a skill's files cite its URI; the message names them.

## Move plaintext secret files into the store

Earlier advice kept skill secrets in plaintext files such as `~/.coffer/secrets/<name>.env`. Any program that walks your home directory reads those — backup tools, a cloud-drive client, an agent's file search. `coffer secret scan` finds them, and `coffer secret import` moves them into the store. **Find plaintext keys** on the [Secrets page](#the-secrets-page) runs the same scan, dry run and import:

```sh
coffer secret scan
```

The scan reads `~/.coffer/secrets/*.env` (`KEY=VALUE` lines) and `*.json` (a flat map of strings), and every text file in your managed skills (assignments whose name says password, secret, token or key, and well-known token shapes). For each finding it prints the file, line, key and the standalone name it would get, such as `coffer://secret/db.PASSWORD` — never the value. It also names every skill that still reads a file under `~/.coffer/secrets/`, so you can move its command to `coffer run --secret` or `coffer run --env-file`; `coffer secret scan --prompt` prints a prompt that hands that rewrite to your agent.

```sh
coffer secret import --dry-run     # print the plan, write nothing
coffer secret import               # move every finding (asks first; --yes skips)
coffer secret import --id <id>     # only this finding (repeatable)
```

For each finding the import stores the value as `secret/<name>`, reads it back and compares, and only then replaces the value in its file with `coffer://secret/<name>`, atomically and keeping the file's mode. A new name waits for your approval like any new standalone secret: the first import stores nothing and leaves the file as it is, and importing again after you approve moves it. A name that already holds a different value is skipped and its file left untouched. A file that cannot be rewritten is reported as skipped with the value stored — the store has it, the file still holds it — while the other files are rewritten; importing the same finding again retries the file. No plaintext backup is kept. Each value stored is audited as `secret_imported`.

Then change the skill's commands to run under `coffer run`, for example `coffer run --env-file ~/.coffer/secrets/db.env -- ./query.sh`.

## The master key and its backup

Every secret is encrypted with one master key. How it is kept depends on the build:

- **A signed release** keeps it in a Keychain item only Coffer's signed binaries can read. No other program gets access, or a dialog to click. The daemon reads it without asking, so it starts unattended after a crash or at login.
- **A development build** keeps it in `~/.coffer/master.key` (or the OS keychain, opt-in), readable by any program running as you.

Presence checks guard what lets plaintext out, not the key itself: that is why the daemon never waits for you.

**Back up the key in the desktop app** (Settings › Security): choose a passphrase, confirm with Touch ID or your login password, pick a folder, and the app writes the passphrase-protected `coffer-master-key.cfk` there with mode `0600`, audited as `master_key_exported`. No command or browser page can do it. Install the backup on another machine with `coffer sync key import <file>` — see [Secret store → Carry the key to another machine](/guides/secret-store#carry-the-key-to-another-machine). In a signed release the Keychain is the only copy, so make a backup.

## Related

- [Secret store](/guides/secret-store) — storing, citing, rotating and deleting a resource's secrets
- [Security model](/architecture/security) — the threat model, and what stays exposed
- [Desktop app](/guides/desktop-app) — where reveals, key backups and approvals happen
- [Writing skill libraries](/guides/writing-skill-libraries) — citing secrets from a skill
- [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)
- [Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/standalone-secrets-are-named-references-injected-into-one-child.md)
- Spec: [secret](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/secret/spec.md)
