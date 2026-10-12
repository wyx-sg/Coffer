## Why

Changing the secret a resource uses went through five different dialogs with three verbs (Replace key, Replace value, Change value); only some offered another stored secret or said who else uses the secret, and a provider's Edit dialog could not change its key at all. The maintainer asked for one pattern, modelled on the provider's Replace API key dialog. The options and the research are in ADR [One Replace Dialog for Every Secret a Resource Uses, Shown Inline in Edit Dialogs](../../../docs/decisions/one-replace-dialog-for-every-secret.md).

## What Changes

- One Replace dialog replaces a secret wherever a resource uses one — a provider's API key, a channel's token, an MCP server's variable or header, a custom-tool group's header, a secret menu's Change value…, and the missing or rejected banners: current secret, who else uses it, **Enter a new value | Use another secret** (with **New secret…**), and the resource's own check of a pasted value.
- A secret this Mac holds no value for reads **Add {field}** in the same dialog.
- A provider's Edit dialog replaces its key in place: **Replace** on the key row opens the same fields, saved with the form; **Keep current key** folds them away.

## Impact

- Specs: web-ui (new "Replace a resource's secret through one dialog"; "Offer an MCP server's hand-off beside Test and View log" names the Replace dialog).
- Code: frontend `components/secret/ReplaceSecretDialog.tsx`, `ReplaceSecretFields.tsx`; provider, channel, MCP and custom-tool callers; `ReplaceSecretRefDialog` and `SecretSourceSwitch` removed.
- Docs: guides (secret store, providers, channels Telegram and SeaTalk, MCP servers), contributing frontend; ADR; canvases Foundations, Capabilities, Run.
