---
title: Secrets
description: How Coffer keeps secrets from the agents it serves — plaintext only in the desktop app, approval before a secret goes somewhere new — and how to use the Secrets page, store standalone secrets, run commands with them through coffer run, answer approvals, list what uses a secret, move plaintext keys into the store, and back up the master key.
---

# Secrets

Coffer holds secrets for your agents, and your agents run as you. This page explains the line Coffer draws between the two, and how to work with it day to day: storing a secret that belongs to no resource, running a command with it, answering the approvals Coffer asks for, finding what uses a secret, moving plaintext keys into the store, and backing up the master key.

For storing, citing, rotating and deleting a resource's secrets — an MCP server's token, a provider key — see [Secret store](/guides/secret-store). The threat model behind all of this is on [Security model](/architecture/security).

## The idea in plain words

A coding agent can read a hostile web page, issue or README and start following the instructions in it. Such an agent runs with your shell: it can read your files, run `coffer`, and call Coffer's API exactly as you can. Coffer does not try to stop it from configuring Coffer — setting Coffer up for you is part of an agent's job. It protects the **secret** instead:

1. **Only you, at the desktop app, see a secret's value.** No command, REST route or MCP tool returns a stored value or the master key. Revealing or copying a value, and backing up the master key, happen only in the desktop app, each after its own Touch ID or login-password check. The next reveal asks again.
2. **A secret goes somewhere new only after you approve it.** Sending an existing secret to a place it has not gone before — a new MCP server, a changed command line, another git remote — waits for you to approve it in the desktop app. Until then nothing is sent.
3. **Switching these protections off also takes you, at the desktop app.** No environment variable, config file or flag does it.
4. **Agents get capabilities, not keys.** The gateway puts an HTTP server's token into the request itself, so the agent sees the tool's results and never the token.

Writing a resource's secret stays open to every surface: whoever supplies a value already has it. Storing a secret, whether a new standalone one or a new value for one in use, takes effect at once.

::: danger Only a signed release holds this boundary
Coffer does not yet ship binaries signed with an Apple Developer ID. Until it does, every build is a **development build**: the master key is the file `~/.coffer/master.key`, which any program running as you can read, and with it a program can forge the desktop app's approval. The commands and approvals on this page work the same way in a development build, and the desktop app labels every prompt "Development build", but they do not stop a determined agent there. See [Security model → Development builds](/architecture/security#development-builds).
:::

## The Secrets page

**Secrets** in the sidebar's System group (`/secrets`) is the one place in the web UI that lists and manages stored secrets. Secrets come only from Coffer: a secret field inside a resource's own dialog — an MCP server's token, a provider's key — either picks a stored secret from this page or takes a pasted value and saves it here with the form, and a header or environment row is plain text with a 🔑 button at the end of the field that picks a stored secret instead. A value pasted into a plain row that looks like a secret offers to be stored. Nothing secret sits in a resource's own settings, only the secret's id. This page is where you see all of them together and what each one is for.

The page is a split view. The list is on the left; the secret you choose is on the right, at `/secrets/<id>`.

Every secret has a fixed **id** — its reference, what configs and files cite — and a **name** you can change at any time, with an optional **description**. Changing the name or the description touches nothing that cites the secret.

**The list.** **Find a secret** (or `/`) filters by name, description or id, and the **Status** chip narrows it to **All**, **In use** (something cites the secret) or **Not used** (nothing cites it, so it is safe to delete). The secrets are grouped under **In use** and **Not used** headings. Each row shows the name alone — the description is in the secret's header — with a status (**No value on this Mac**, **Waiting for approval**, and a terminal icon where other programs running as you can read the value), and how many things use it ("used by 2"). A secret you have not named shows the thing that uses it and the slot it fills, such as **confluence · CONFLUENCE_PERSONAL_TOKEN**. The header carries **Add secret** and **Find plaintext keys**.

To delete several at once, tick rows (or the header checkbox for the whole list); a bar over the list reads "3 of 8 selected" with **Delete…**, and **Esc** clears the selection. The confirmation names the secrets it will delete and says which selected ones it skips because they are in use or waiting for approval.

### Missing on this Mac

A row reads **No value on this Mac** when this Mac has no value to hand out for it: a resource or skill cites it but it was never stored here, or its encrypted value came with the vault from another Mac whose master key this one does not have (encrypted secrets don't sync by default). Whatever uses it cannot start until it has a value. The detail's **Add value** (or a field in **Add values**) stores one; like any write it may [wait for your approval](#approvals). While any secret is missing, a banner at the top counts them ("3 secrets have no value on this Mac"), names them, and offers **Add values**: one dialog with a field per missing secret, where a field left empty stays missing and **Save N values** stores the rest. The same count appears on [Overview](/guides/web-ui#overview), whose button opens this page. The other way to open every secret at once is the other Mac's master key, which is imported in the [vault sync](/guides/vault-sync) join flow or in Settings › Security, not on this page. Coffer finds a secret it cannot open by checking the encrypted value's signature against this Mac's key, without decrypting anything.

Choosing a row opens that secret in the right-hand pane. Its header holds the **name** and **description**, each edited in place (a name of up to 64 characters, a description of up to 200; both sync with your vault), with **Replace value…** and **Reveal value…** beside them and a **⋯** menu. Under the header the detail shows the secret's id and its `coffer://secret/<id>` URI, each with **Copy**; whether this Mac holds the value and whether other local processes can read it; when it was created and last used; and **Used by** — everything that uses it, by kind (MCP server, model provider, channel, skill, …), current name and slot, with the approvals it holds or waits for. Choosing a name opens that thing's page. The other way round, wherever a page shows the secret a thing uses — a provider's **API Key**, a sync remote's push secret — it shows the secret's name, and the name opens that secret here; the id and URI appear only here, to copy. Individual uses are not listed here; they are in [Activity](/guides/activity).

| Control | What it does |
| --- | --- |
| **Replace value…** | Takes a new value without ever showing the old one. The dialog names what uses the secret. It takes effect at once. For a secret [without a value on this Mac](#missing-on-this-mac) the button reads **Add value**. |
| **Reveal value…** | Only in the desktop app — see [See or copy a value](#see-or-copy-a-value). A browser shows it disabled as **Reveal in the Coffer app**. |
| **⋯ › Copy reference (…)** | Copies what a file or config cites, shown in the item: `coffer://secret/<id>` for a standalone secret, the ref otherwise. |
| **⋯ › Delete…** | For a secret nothing uses, asks once and deletes it — on this Mac and, if encrypted secrets sync, on your other Macs at their next round. For one in use, it deletes nothing: the dialog lists each thing that still uses it, with **Open** to go there, and the secret stays. |

**Find plaintext keys** looks for credentials written in plain text in what Coffer manages: the files of your skills (an assignment whose name says password, secret, token or key, or a well-known token shape such as `ghp_…` or `sk-…`), and each registered MCP server's environment variables and HTTP headers, custom tools' headers included. A reference, a `$VAR` or `${VAR}`, or a placeholder such as `<your-token>` is left alone. The dialog lists what it found under Skills and MCP servers — the skill's file and line or the server's `env`/`header` key, and what each becomes — never the value, with everything ticked. Untick what should stay, then **Review N changes**: Coffer works out the move without writing anything and lists the secrets it would add and the files and servers it would change. **Apply N changes** moves them:

- a skill's value becomes a standalone secret named after the finding, and its file cites `coffer://secret/<id>` in its place (see [Run a command with a secret](#run-a-command-with-a-secret) for using it from a script). A file Coffer cannot rewrite keeps its value: the value is stored all the same, the dialog names the file and offers **Try again**.
- a server's value becomes a secret of that server's own, cited from the server's config under the same variable or header name; the server gets the same value as before, with no approval to answer.

Each move is recorded in [Activity](/guides/activity) as **Imported secrets**, without the value. A scan that finds nothing says how many files and servers it read.

**Add secret** adds a new standalone secret: a name and a value, which is never shown back. Coffer mints its id, `secret/<id>`, and the dialog then shows `coffer://secret/<id>` with **Copy** — that is what a script or a skill cites. The secret is stored as soon as you add it, with nothing to approve. A secret added here, or with `coffer secret set --name`, needs your approval the first time a resource cites it; see [Approvals](#approvals).

To use a stored secret in a command, see [Run a command with a secret](#run-a-command-with-a-secret).

While any change waits for approval, a banner at the top says how many ("1 change waiting for approval") and what approving takes here (Touch ID or your login password in the desktop app; in a browser, the desktop app), with **Review** to reopen the approvals dialog. Overview carries the same item, and its **Review** opens the same dialog. A banner's **×** ignores it, on this page and on Overview alike: the page then says "… — ignored on Overview. Show it again", and the item returns by itself when the situation changes. With no secrets at all, the page offers **Add secret** and **Find plaintext keys**.

## Standalone secrets

Most secrets belong to a resource and are stored by the dialog that registers it. A **standalone secret** belongs to no resource: the database password a skill's script needs, an internal API token you use from the terminal. It lives in the same encrypted store under `secret/<id>`, and files cite it as `coffer://secret/<id>`.

Coffer always mints the id, on the Secrets page and with `coffer secret set --name "<name>"` alike; you never choose one. You choose only a **name** and an optional **description**, and you can change both at any time, since they are notes kept beside the secret in your vault and synced with it. The id never changes, so renaming the secret on the Secrets page leaves everything that cites it working. When a dialog asks for a secret, its picker lists secrets by name and writes the id into the config.

Every secret of every kind has this one shape. A secret you paste into a resource's own dialog — an MCP server's token, a provider's key — is minted as `secret/<id>` too, and belongs to that resource (see [Secret store → Delete a secret](/guides/secret-store#delete-a-secret)).

### Store one

```sh
# From stdin, so the value never reaches your shell history
printf '%s' "$ORDERS_DB_PASSWORD" | coffer secret set --name "Orders DB"
# stored: Orders DB
#   id:  secret/<id>
#   uri: coffer://secret/<id>

# Or at a hidden prompt
coffer secret set --name "Orders DB"
```

The command prints the new id and its `coffer://secret/<id>` URI; that is what you cite. `coffer secret set <existing ref>` only replaces the value of a secret that exists. It never creates one, and a ref that is not `secret/<id>` is refused.

On the [Secrets page](#the-secrets-page), **Add secret** does the same: a name and a value, then the URI to copy. The new secret is stored at once, so `coffer run` resolves it right away.

### Cite it

Wherever a skill or a project needs the secret, write its reference instead of its value:

```sh
# connection.env, next to a skill's script
DB_HOST=db.internal
DB_USER=orders_ro
DB_PASSWORD=coffer://secret/<id>
```

A skill's `connection.md` names it the same way. A file holding only references is safe to commit and safe to sync. Nothing reads it by itself: [`coffer run`](#run-a-command-with-a-secret) resolves the references when a command starts.

A resource can cite a standalone secret too, as `secret/<id>` in its secret refs, like any other ref.

## Run a command with a secret

`coffer run` resolves standalone secrets through the daemon and starts one command with the values set **only in that command's environment**. A secret's id is not a variable name, so name the variable yourself:

```sh
coffer run --secret PGPASSWORD=coffer://secret/<id> -- psql -h db.internal orders
coffer run --env-file connection.env -- ./query.sh
```

| Option | Meaning |
| --- | --- |
| `--secret ENV=coffer://secret/<id>` | Set `secret/<id>` as the variable `ENV`. Repeatable. This is the form to use, and the form a skill cites: the secret then lists the skill under **Used by**. `ENV=<id>` works too. |
| `--secret coffer://secret/<id>` or `--secret <id>` | Set `secret/<id>` as a variable whose name is derived from the id (upper-cased, `-` and `.` turned into `_`). Since an id is a string of hex characters, the derived name is rarely what the command wants; prefer `ENV=coffer://secret/<id>`. |
| `--env-file FILE` | Read `KEY=VALUE` lines. Plain values are passed through; each `coffer://secret/<id>` value is resolved. |
| `--no-masking` | Pass the command's output through untouched, for tools that need a real terminal. |

A `coffer://secret/<id>` value already in `coffer run`'s own environment is resolved too, so a wrapper script can export the references once. Everything after `--` is the command and its arguments.

What happens:

- **Only standalone secrets resolve.** The id must be stored under `secret/`; a resource's secret can never be fetched this way. An unknown id fails with `SECRET_NOT_FOUND` and the command does not start.
- **The values go to the child only.** The shell that ran `coffer run` does not get them, and neither do its other children.
- **Output is masked.** Every exact occurrence of a value in the command's standard output and error prints as `***`, even when it is split across two writes. Values shorter than 8 characters are not masked — masking a short value would shred ordinary output — and `coffer run` says so when it skips one.
- **The exit status passes through**, so `coffer run` fits into scripts. A command killed by a signal exits `128 + signal`; a command that cannot start exits `127`. `Ctrl-C` and `SIGTERM` are forwarded to the command.
- **Every resolve is audited** as `secret_resolved`, naming the secret, the program and the working directory — never the value, and never the rest of the command line, which might carry a secret of its own. Read them with `coffer log audit --event-type secret_resolved`.

::: warning `coffer run` guards against accidents, not against an agent
`coffer run` keeps a secret out of files, git, the agent's own environment and transcripts **by accident**. It does **not** hide the secret from an agent that runs the command: the agent is the command's parent, so it can read the child's environment (`ps eww`), run `coffer run --secret TOKEN=<id> -- env`, or print the value base64-encoded, which masking does not recognise. Masking also never sees what the command writes to files. Every standalone secret is listed as readable by local processes for this reason.
:::

## See or copy a value

Open the [Secrets page](#the-secrets-page) in the **desktop app** and choose **Reveal value…** on the row. A warning comes first: anyone who can see your screen can read the value. Then macOS asks for Touch ID or your login password, and the prompt names the secret. The value shows for 30 seconds, with **Copy** and **Hide**, then hides again; closing the dialog drops it at once. Each reveal asks again; there is no window during which a second one is free. The reveal is audited as `secret_revealed` with the ref only.

The browser UI offers no reveal: the menu item reads **Reveal in the Coffer app** and is disabled.

## Approvals

A secret added on the Secrets page or with `coffer secret set --name` belongs to no resource, so the first time a resource cites it, that waits for a person's approval too. An approval is a change that would widen where a secret goes, held until you answer it in the desktop app.

### What asks for approval

| You, or an agent, do this | What waits |
| --- | --- |
| Register a resource that cites a secret already sent somewhere else, such as a second MCP server using the same token. | The new server gets no secret until you approve. The first keeps working. |
| Change where a resource sends a secret: a stdio server's command, arguments, working directory or other environment; an HTTP server's URL; a SeaTalk channel's app. | The resource gets no secret until you approve the new target. |
| Point the sync remote's push token at a different URL. | The remote is not saved until you approve. |
| Turn off secret approval in **Settings › Security**. | The protection stays on until you approve. |

What counts is the **target** — the thing that actually receives the value, written so you can judge it: a stdio server's whole command line with its working directory and other environment variables (a variable such as `NODE_OPTIONS=--require …` changes what the process does), an HTTP server's URL, a git remote's URL, a channel's bot or app. An approval reads, for example:

```text
send secret 'github/token' to mcp_server 'gh-work' (GITHUB_TOKEN) at stdio npx -y @modelcontextprotocol/server-github
```

Approve only a target you recognise. A command line you did not write, pointing at a script in a temporary directory, is exactly what an injected agent would register.

### What needs no approval

- **A secret created for that resource.** A secret you paste into a resource's own dialog — an MCP server's token, a provider's key — is minted for that resource and belongs to it, so registering the resource needs no extra approval for it. A second place citing the same secret is a second place, and waits.
- **Anything, while the protection is off.**

A binding is also checked when you register or change the place that uses it, so an approval it needs appears right when you save, with the approvals dialog opening on the page you are on. A binding is checked at the moment of use — when a server starts, a channel connects, a sync round pushes — so a change that arrives behind Coffer's back, such as a vault file edited by hand or a server another machine synced in, is caught too.

### Answering one

When something waits, the desktop app posts a notification, **Coffer needs your approval**, naming the change, and opens the approvals dialog, one table with a row per change: the kind of change (**New use**, **Turn off protection**), the secret, where it goes (what uses it, or the target that receives it), who asked (**You · in the Coffer UI**, **You · on the command line**, **Through the API**) and when. With one change, **Approve…** runs Touch ID or your login password, with a prompt that names the change, then applies it; the server, channel or remote picks the secret up on its next attempt, with no restart. **Reject** needs no presence check, since refusing only narrows what Coffer does.

In a browser, **Approve** is disabled — "Approve in the Coffer desktop app" — and only **Reject** works.

### Answering several at once

When two or more changes wait — after an upgrade, say, when several destinations ask at once — the same table has a header checkbox, and nothing is ticked to begin with. Tick the changes you want to answer: the bar reads "2 of 3 selected" with **Reject 2** and **Approve 2…**, and with nothing ticked the buttons read **Reject all** and **Approve all 3…**. Pressing **Approve…** runs the presence check directly, once, and the prompt names the first few changes and counts the rest; there is no second review step, because the table already lists every change the confirmation will cover. The rows then say what became of each: **Approved**, or **Skipped**. A change whose target moved after you opened the list is skipped and keeps waiting, and so is anything no longer waiting; nothing outside the list you saw is approved. Turning the protection off is never part of a batch — approve it on its own. **Reject** needs no presence check.

Rejecting shows a toast and nothing more: the page keeps no list of refused changes and has no "Ask again". A rejection stands for that target: the secret stays withheld, and a server or command that meets it is told it was refused (`SECRET_BINDING_REJECTED`) rather than that something waits. Change the destination to put the question to you afresh. An approval ends as `approved`, `rejected`, or `superseded` — when the resource it was for was deleted or has since moved to another target, which raises a fresh approval of its own.

### On the command line

A command whose change leaves a secret waiting, such as registering a second server that cites a secret already sent elsewhere, prints `waiting for approval in the Coffer app` with what waits and exits `9`. `coffer secret set` itself never waits: it stores the value at once and exits `0`.

An agent that hits exit `9` should tell you what it registered and that it waits for you, not retry.

### Switching the protection off

`secrets.require_approval` defaults by the build: **on** in a signed release, **off** in a development build, whose master key any program running as you can read, so approvals there would stop only accidents (Settings and this page say so in one line). A setting you store wins in either. Turning it on takes effect at once. Turning it off waits for an approval in the desktop app, and while it is off every new destination is approved without asking. Nothing else — no environment variable, file or flag — switches it off. The switch is the **Approvals** section of **Settings › Security**; a browser shows it as **Turn off in the Coffer desktop app**.

## List your secrets

```sh
coffer secret list
```

The [Secrets page](#the-secrets-page) shows the same list. The table has a **Name** column with each secret's label, and `--json` carries, per secret, `ref`, `uri`, `label`, `description`, `created_for` (the uid of the resource it was minted for, if any), `locked` (stored, but this Mac's master key cannot open it), `created_at` and `last_used_at`, and `cited_by` — each citer with its kind, name and the **slot** it cites the secret under. The list has every ref the store holds and every ref a resource cites, with what uses each one — resources, skills whose files cite `coffer://secret/<id>`, destinations waiting for approval — and `(unreferenced)` for a secret nothing uses. Each managed agent's model-proxy token (`proxy-token/<agent name>`) is not listed: Coffer mints it and the agent fetches it on its own, so there is nothing to enter, replace or cite. **Readable by local processes** is `yes` where another program running as you can read the value where Coffer puts it: every standalone secret (it goes into a `coffer run` child) and every secret in a stdio MCP server's environment. See [Secret store → List and inspect](/guides/secret-store#list-and-inspect) for the columns.

Deleting a secret is refused while a resource cites it or a skill's files cite its URI; the message names them.

Every time Coffer decrypts a secret to use it — a server starting, a channel connecting, a provider key fetched, a sync push, `coffer run` — it records `secret_resolved` in [Activity](/guides/activity), naming who used it and the slot, never the value. The same secret and destination is recorded at most once a minute. Read them in Activity or with `coffer log audit --event-type secret_resolved`.

## The master key and its backup

Every secret is encrypted with one master key. How it is kept depends on the build:

- **A signed release** keeps it in a Keychain item only Coffer's signed binaries can read. No other program gets access, or a dialog to click. The daemon reads it without asking, so it starts unattended after a crash or at login.
- **A development build** keeps it in `~/.coffer/master.key` (or the OS keychain, opt-in), readable by any program running as you.

Presence checks guard what lets plaintext out, not the key itself: that is why the daemon never waits for you.

**Back up the key in the desktop app** (Settings › Security): choose a passphrase, confirm with Touch ID or your login password, pick a folder, and the app writes the passphrase-protected `coffer-master-key.cfk` there with mode `0600`, audited as `master_key_exported`. No command or browser page can do it. Install the backup on another machine with **Import a master key** on **Settings › Security** — see [Secret store → Carry the key to another machine](/guides/secret-store#carry-the-key-to-another-machine). In a signed release the Keychain is the only copy, so make a backup.

## Related

- [Secret store](/guides/secret-store) — storing, citing, rotating and deleting a resource's secrets
- [Security model](/architecture/security) — the threat model, and what stays exposed
- [Desktop app](/guides/desktop-app) — where reveals, key backups and approvals happen
- [Writing skill libraries](/guides/writing-skill-libraries) — citing secrets from a skill
- [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)
- [Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/standalone-secrets-are-named-references-injected-into-one-child.md)
- Spec: [secret](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/secret/spec.md)
