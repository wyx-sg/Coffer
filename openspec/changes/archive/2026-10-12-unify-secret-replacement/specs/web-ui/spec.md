## ADDED Requirements

### Requirement: Replace a resource's secret through one dialog
Wherever the app replaces a secret a resource already uses — a model provider's API key, a channel's
bot token or app secret, an MCP server's environment variable or header, a custom-tool group's
header, a secret menu's **Change value…**, and the banners for a missing or rejected secret — it MUST
use one **Replace** dialog titled **Replace <field>**. The dialog MUST name the current secret
(a link to its page on the Secrets page), say which other resources use it when there are any,
and offer **Enter a new value** — an empty, write-only field whose value is written under the
reference the resource already cites, so everything citing it gets the value — and, where the
resource can be re-pointed, **Use another secret**, a picker of the other stored secrets that also
offers **New secret…**, which re-points only that resource and leaves the old secret and its value
as they are. A resource that can check a pasted value (a provider listing its models, a channel
asking its platform) checks it in the same dialog, and a value the platform rejects cannot be
saved. A secret this Mac holds no value for reads **Add <field>** with **Add key**. An Edit dialog
that holds a secret (a model provider's) MUST offer the same fields in place: **Replace** on its
key row opens them, what is entered there is saved with the rest of the form, and **Keep current
key** folds them away with nothing changed. The Secrets page's own Edit, which changes the secret
itself, and the add forms' secret field, which chooses one, are not Replace dialogs.

#### Scenario: replacing a secret offers a new value or another stored secret
- **GIVEN** a resource field citing a stored secret, and another stored secret
- **WHEN** the user opens Replace on that field
- **THEN** the dialog reads **Replace <field>** and names the current secret
- **AND** a new value with **Replace key** is written under the current reference, while **Use another secret** lists only the other secret and **Use this secret** re-points the field to it

#### Scenario: a secret missing on this Mac reads Add
- **GIVEN** a field citing a secret this Mac holds no value for
- **WHEN** the user opens its Replace dialog
- **THEN** it reads **Add <field>**, and **Add key** stores the value under the reference the field cites

#### Scenario: a provider's Edit dialog replaces its key with the form
- **GIVEN** a model provider with a stored key
- **WHEN** the user opens Edit, chooses **Replace** on the API Key row, enters a new value and saves
- **THEN** the key's value is replaced under the same reference when the form is saved
- **AND** **Keep current key** folds the fields away and Save then leaves the key as it was

## MODIFIED Requirements

### Requirement: Offer an MCP server's hand-off beside Test and View log
An MCP server's page MUST offer the backend's hand-off (Copy prompt, and Ask an agent when a managed agent
is available) wherever the server's state is a chore for an agent, passing the prompt on as served and
never assembling it: the missing-launcher callout offers the status read's `handoff` in place of any install
command, and the failing callout and a failed test's result offer the diagnosis `handoff` beside View log
(or Show stderr) while Test stays in the header. The page MUST NOT show a package-manager command or an
"install it, then refresh" instruction. A failed test of an unsaved config in the Add and Edit dialogs offers the daemon's hand-off in the result when the failure depends on this machine, and the page never writes a prompt of its own.

#### Scenario: a missing launcher offers the hand-off, not an install command
- **GIVEN** an MCP server whose status names a missing launcher and carries a `handoff`
- **WHEN** its page opens
- **THEN** the launcher callout names the launcher and offers Copy prompt, which copies the served prompt, and shows no `brew install` line

#### Scenario: a rejected key reads Replace key
- **GIVEN** an MCP server whose status reads failing with `failure_reason` `auth_rejected`, and an Overview item with the verb `replace_key`
- **WHEN** the server's page opens and the Overview lists the item
- **THEN** the failing callout says the key was rejected and offers Replace key, which opens the Replace dialog on the secret its env or headers cite (the edit dialog when the key is typed into the config itself), and the Overview row's action reads Replace key and opens the server's page

#### Scenario: a failed test offers a diagnosis hand-off beside View log
- **GIVEN** an MCP server whose test just failed with an error and a `handoff`
- **WHEN** the result is shown
- **THEN** the result callout shows the error with View log and Copy prompt beside it, and the header still offers Test
