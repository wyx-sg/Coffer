## MODIFIED Requirements

### Requirement: Manage stored secrets on the Secrets page
The Secrets page (`/secrets`, under the sidebar's System group) MUST be the one
page in the web UI that lists and manages stored secrets. A secret is shared
infrastructure data — one reference can be cited by MCP servers, model
providers, channels and skills at once (spec
[secret](../secret/spec.md) "Address a secret by an opaque reference") —
so it gets a page of its own rather than a section of any one kind's page, and
it is not a Settings tab, because it holds data the user manages rather than a
preference. A secret field inside a resource's own dialog stays there: a secret
is still entered where the thing that needs it is configured.

The page MUST carry:

- **List** — one table of every secret the store holds or a resource cites, by
  its reference (a standalone secret by its name), sorted by name, with whether
  this Mac holds it, so a reference cited but missing reads as missing on this
  Mac (spec [secret](../secret/spec.md) "List every stored and cited secret with
  what uses it"). Search by name, and a status filter of All, In use and Not
  used, narrow it; its columns are Name, Used by, Last used and Created, the
  times relative ("3 h ago") and, past a week, a date ("Aug 12"). The page has
  no owner line, no owner-type filter, no by-owner view and no "Delete unused".
- **Used by** — for each secret, what cites it, by kind and current name, each
  opening that thing's page; a secret nothing cites reads Nothing and is found
  with the Not used filter.
- **Add and replace** — store a new secret, or replace the value of one that
  exists, without the value ever being shown back; a change that waits for a
  person's approval says so (spec [secret](../secret/spec.md) "Hold a new
  standalone secret until a person approves it").
- **Reveal** — show one value behind an explicit, confirmed action, only in the
  desktop app, audited as `secret_revealed` (spec [secret](../secret/spec.md)
  "Release plaintext only to a present human in the desktop app"); in a
  browser the action is disabled and names the desktop app.
- **Delete** — refused while the secret is cited: the control MUST say what still
  uses it, naming each citer as the delete refusal does (spec
  [secret](../secret/spec.md) "Refuse to delete a secret still in use"), and
  the row MUST stay. Several rows can be ticked and deleted at once from the
  table's selection bar ("N of M selected"; Esc clears it); the confirmation
  names the secrets it deletes and skips those in use or waiting for approval.
- **Missing values** — a banner counting the secrets this Mac has no value for,
  with **Add values** (spec [secret](../secret/spec.md) "Show a secret this Mac
  cannot open as missing on this Mac"); it offers no master-key import.
- **Approvals** — a banner counting the changes waiting for approval, with
  **Review**, which opens the one approvals table (spec
  [secret](../secret/spec.md) "Approve several bindings in one confirmation").
  A rejection shows a toast; the page keeps no list of refused changes and has
  no "Ask again".
- **Find plaintext keys** — the entry point that moves plaintext secret files
  into the store (spec [secret](../secret/spec.md) "Move plaintext secret files
  into the store").

Each banner has an × that ignores it exactly as Ignore does on Overview, where
the same two situations are listed (spec [secret](../secret/spec.md) "List
secrets with no value here and waiting approvals on Overview"); the page's
header then says it is ignored on Overview and offers Show it again, and the
banner returns when the set changes. The help icon beside the title is gone: how
to run a command with a secret is in the documentation, not on the page.

This requirement fixes the page's place and its parts. What the store enumerates,
how each operation behaves, and the steps of finding plaintext keys are the
secret capability's, specified with it.

#### Scenario: the secrets page lists each secret with what uses it
- **GIVEN** a registered MCP server citing a stored reference, and a model provider citing a reference the store does not hold
- **WHEN** the user opens `/secrets`
- **THEN** both references are listed in one table, the first as present and the second as missing on this Mac
- **AND** each row names its citer by kind and current name, and choosing it opens that resource's page

#### Scenario: a secret in use cannot be deleted from the secrets page
- **GIVEN** a stored secret cited by a registered channel
- **WHEN** the user tries to delete it from the Secrets page
- **THEN** the delete is refused with the channel named as what still uses it
- **AND** the secret's row is still listed

#### Scenario: revealing a secret is an explicit, audited read
- **GIVEN** a stored secret listed on the Secrets page in the desktop app
- **WHEN** the page renders, and then the user chooses Reveal value on that row and confirms
- **THEN** no value is shown until the reveal is confirmed, and then only that secret's value is asked for and shown
- **AND** the page says the reveal is recorded as `secret_revealed`
