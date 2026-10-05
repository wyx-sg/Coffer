## Why

Adding a secret on the Secrets page asked for a name and a value but not a
description, though every secret has one and the menus search it. The secret's
detail edited its name and description in place, in always-there fields in the
header, unlike the other detail pages, which edit through Edit and a dialog
(the CLI page among them); replacing the value was a separate button and dialog.

## What Changes

- Add secret (and the New secret dialog a secret field opens) takes an optional
  description beside the name and value. `POST /api/v1/secrets` accepts
  `description` with a label, and `coffer secret set --name` takes
  `--description`.
- The secret's header shows the name and description as text, with **Edit**
  beside Reveal value…. Edit opens one dialog for the name, description and
  value; the value field starts empty and, left empty, keeps the value.
- Replace value… leaves the header: replacing (or, for a secret missing on this
  Mac, adding) the value is done in Edit.
- Local access for `coffer run` stays on the overview's Access row: it is a
  request that waits for approval, not a field a Save applies.
- After a person refused that request, **Allow coffer run…** answered
  `SECRET_BINDING_REJECTED` forever and left an error toast on every press.
  Asking for the grant again now retires the refusal and puts a new request up;
  `coffer run` alone still stays refused.

## Impact

- Backend: `SecretSetIn` gains an optional `description`; the CLI gains
  `--description`. Stored secrets are unchanged: notes already carry a
  description.
- Frontend: Add secret, New secret, the secret's header, a new Edit dialog; the
  in-place note field goes.
- Specs: web-ui, secret. Docs: Secrets guide and CLI reference (en + zh).
