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

- **List** — every secret the store holds or a resource cites, sorted by its
  displayed name, with whether this Mac holds it, so a reference cited but
  missing reads as missing on this Mac (spec [secret](../secret/spec.md) "List
  every stored and cited secret with what uses it"). The list's controls are
  those of the other library lists: a filter box, then a **Status: All / In use /
  Not used** filter chip (a select), then the secrets grouped under **In use**
  and **Not used** headings. The page has no owner line, no
  owner-type filter, no by-owner view and no "Delete unused".
- **Used by** — for each secret, what cites it, by kind, current name and slot,
  each opening that thing's page; a secret nothing cites reads Nothing and is
  found with the Not used filter.
- **Add and replace** — store a new secret at once, or replace the value of one
  that exists, at once and without the value ever being shown back (spec
  [secret](../secret/spec.md) "Store a secret through the API").
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
- **List and detail** — the page is a split view like the other library pages:
  `/secrets/<id>` with the list on the left and the chosen secret on the
  right. A list row shows the secret's label — or, without one, the first
  citer's name and the slot, never a hex id — with its description as a muted
  second line, its status (missing on this Mac, waiting for approval) and how
  many things use it; search matches the label, description and id. The
  detail's header holds the label and description, each edited in place (spec
  [secret](../secret/spec.md) "Label and describe a secret without changing its
  reference"), with Replace value… and Reveal value… beside them and Copy
  reference and Delete… in its ⋯ menu. The detail shows the overview directly,
  with no tabs: the id and `coffer://secret/<id>`, each with Copy, whether this
  Mac holds it and whether local processes can read it, created and last used,
  and everything that uses it — by kind, current name and slot, each opening
  its page — with the approvals it holds or waits for. Individual uses are not
  listed on the page; they are audit entries, read in Activity.
- **Find plaintext keys** — the entry point that moves plaintext secrets out of
  what Coffer manages and into the store (spec [secret](../secret/spec.md)
  "Move plaintext secrets in managed resources into the store").
- **Approvals** — a banner counting the changes waiting for approval, with
  **Review**, which opens the one approvals table (spec
  [secret](../secret/spec.md) "Approve several bindings in one confirmation").
  A rejection shows a toast; the page keeps no list of refused changes and has
  no "Ask again".

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
- **THEN** both are listed, the first as present and the second as missing on this Mac
- **AND** choosing a row shows its citer in the detail by kind and current name, which opens that resource's page

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

#### Scenario: the secrets page offers to find plaintext keys
- **GIVEN** the Secrets page
- **WHEN** it is opened, with secrets and with none
- **THEN** its header offers Find plaintext keys beside Add secret, and the empty page offers both

#### Scenario: a secret opens on its own detail page with overview and usage
- **GIVEN** the Secrets page listing a secret an MCP server cites under a hex ref, which the server has used
- **WHEN** its row is chosen
- **THEN** the list row reads as the server's name and the slot, the address becomes `/secrets/<id>`, and the detail shows the id, the times and the server under Used by, which opens the server's page, with no tabs
- **AND** a label and description typed in the header show on the row while the id stays the same
