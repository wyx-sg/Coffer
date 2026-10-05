## Why

The Secrets page shows a secret by its ref, and many refs are unreadable — a
resource's own secret is minted at `<kind>/<uuid4 hex>/<slot>`, and older
vaults hold `name.KEY` shapes. A person cannot give a secret a name they
recognise, or say what it is for. Changing the ref itself would mean moving
the value and rewriting every config, skill file and script that cites it.

## What Changes

- A secret keeps its ref for life; the ref is its identity, like a resource's
  uid. What the page shows is a **label**: a name the person can change at any
  time, and a **description** — both kept in one vault document keyed by ref,
  synced with the vault. Changing them touches nothing that cites the secret.
- Without a label, the page shows a readable default: a standalone secret's
  name, else the first citer's name and the slot (`confluence ·
  CONFLUENCE_PERSONAL_TOKEN`), never a hex segment.
- A standalone secret added on the page is given a minted id, `secret/<uuid4
  hex>`; the person types only its label and value, and copies
  `coffer://secret/<id>` from the dialog. Existing standalone secrets keep their
  names as ids; `coffer secret set <name>` still names one explicitly.
- `PUT /api/v1/secrets/notes` sets a ref's label and description; the list
  carries both.
- Clicking a row opens a wide detail sheet on the right — label and
  description edited in place, reference with Copy, times, everything that
  uses it with its approvals, and its actions. The Used by popover is removed.

## Impact

- Backend: a `secret-notes` vault state document, its port and store; the list
  route; a notes route; delete and resource-release drop a ref's notes;
  `secret_notes_updated` audit.
- Frontend: the detail sheet, the Name cell (label and description), Used by
  as plain text, search over label and description.
- Specs: secret, web-ui. Docs: guides/secrets (en + zh).
