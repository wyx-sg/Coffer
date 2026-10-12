# One Replace Dialog for Every Secret a Resource Uses, Shown Inline in Edit Dialogs

**Status**: Accepted
**Date**: 2026-10-12
**Deciders**: Yuxing Wu
**Related**: [Resources Cite Secrets by Opaque Reference, Resolved Only at the Moment of Use](credential-references.md),
[Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](standalone-secrets-are-named-references-injected-into-one-child.md),
spec web-ui "Replace a resource's secret through one dialog",
spec provider-switching "Rotate a connection's secret in place"

## Context

A resource cites a secret by reference; changing what it sends means either a
new value under the same reference (every resource citing it gets the value) or
pointing this one resource at another stored secret. By October 2026 the app
did this through five different dialogs and seven entry points:

| Entry point | Dialog | Could do |
| --- | --- | --- |
| Provider page, Replace key… | `ReplaceKeyDialog` | new value (checked as pasted) or another secret |
| Provider Edit dialog | a read-only row: "use Replace key" | nothing |
| Channel Settings, Replace key… | `ChannelReplaceSecretDialog` | new value (checked) or another secret |
| MCP server Requires, Replace key… | `ReplaceSecretRefDialog` | new value or another secret |
| Secret menu "Change value…" (env/header rows, sync remote) | `ReplaceSecretDialog` | new value only, listed who uses it |
| Missing / rejected banners (MCP, custom tools, a tool test) | `ReplaceSecretDialog` | new value only |
| Secrets page, Edit | `EditSecretDialog` | name, description, value |

They used three verbs (Replace key / Replace value / Change value), different
layouts, and only some said that a new value reaches every other resource using
the secret. The person had to learn each one, and could not change a provider's
key from the dialog literally called Edit.

### How comparable products do it

- **GitHub Actions secrets** — an "Update secret" page per secret: the name is
  fixed, the value field starts empty and is write-only.
- **Vercel / Netlify environment variables** — the variable's own Edit dialog
  changes the value; a sensitive value cannot be read back and must be typed again.
- **n8n credentials** — a node picks a credential from a list that ends in
  "Create new credential"; editing the credential's value changes it for every
  node that uses it, and the editor says so.
- **1Password `op://` references, Doppler** — applications hold only the
  reference; the value is changed once in the vault and every reference follows.
- **Raycast, Cursor, Zed API-key settings** — a password field with a verify
  step when the key is entered.

Common ground: the value is changed where the thing is edited, the field is
write-only and starts empty, the product says that a shared value changes for
everyone, and "use a different credential" is a separate choice from "change
this credential's value".

## Decision

One **Replace** dialog (`components/secret/ReplaceSecretDialog.tsx`) replaces a
secret wherever a resource uses one. Its body is one component,
`ReplaceSecretFields`: the current secret by name, a segmented **Enter a new
value | Use another secret**, then either a write-only value field (with "also
used by …" when other resources cite the secret, and an optional check slot) or
a picker of the other stored secrets with **New secret…**. Callers vary only in
what they plug in: the field's name for the title, how a value is written (the
store, a provider PATCH, a channel edit), how a rebind is saved, and a check of
the pasted value (a provider's model list, a bot's handle). Without a rebind the
picker is not offered; a secret this Mac holds no value for reads **Add**.

An **Edit** dialog that holds a secret (a provider's) shows the same fields
inline: **Replace** on the key row expands them, they are submitted with the
form's Save after the other fields, and **Keep current key** folds them away.

Two surfaces stay as they are, because they do something else: the Secrets
page's own Edit changes the secret itself (name, description, value) and has
nothing to re-point; the add forms' `SecretField` *chooses* a secret for a
resource that does not exist yet.

## Options

### Option A — one dialog, the same fields inline in Edit dialogs (chosen)

- **Good:** one pattern to learn; every replace says who else is affected and
  offers both a new value and another (or a new) secret, which the project's
  rule "every place that adds a secret supports picking and creating" asks for;
  Edit really edits everything; Cancel on an Edit dialog changes nothing.
- **Cost:** the provider's Edit dialog gains a mutation step (the key is sent
  last, so a refused rename or address stops before the key moves); callers
  that check values must hold the draft themselves (controlled mode).

### Option B — one dialog, opened on top of the Edit dialog

Edit's key row keeps a "Replace…" button that stacks the same dialog over Edit
and applies at once.

- **Good:** no change to Edit's save path; least code.
- **Lost because:** a dialog over a dialog, and Cancel on Edit would not undo a
  key already replaced — the Edit dialog would look like it holds the change
  when it does not. The person chose inline (2026-10-12).

### Option C — keep the per-resource dialogs, align only their words

- **Good:** smallest change; each dialog keeps its tailored copy.
- **Lost because:** the layouts, the missing "Use another secret" in half of
  them and the missing "who else uses it" stay; five components drift apart
  again with every change.

### Option D — replace values only on the Secrets page

Resources would link to their secret's page, and only its Edit would change values.

- **Good:** one place, matches the 1Password / Doppler vault model.
- **Lost because:** rotating a provider key or a bot token is a task done from
  that resource (often from its rejected-key banner), and the resource-specific
  checks (models listed with the new key, same-bot pairing) need the resource.
  Re-pointing one resource cannot be done from the secret's page at all.

## Consequences

- `ReplaceSecretRefDialog` and `SecretSourceSwitch` are gone; `ReplaceKeyDialog`
  and `ChannelReplaceSecretDialog` are thin wrappers that add their check and
  their write path.
- The labels are one set: title **Replace {field}** / **Add {field}**, value
  **New value**, buttons **Replace key**, **Add key**, **Use this secret**.
- A new kind that cites a secret uses `ReplaceSecretDialog` for its replace path
  and `ReplaceSecretFields` inside its Edit dialog; it does not write its own.
