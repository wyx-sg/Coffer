## Why

The UI QA run on 2026-10-06 (UI-004, UI-005, UI-006) found three places where a
correct refusal or a saved change was reported wrongly. Testing a stored key
against a new endpoint was refused before anything was sent, but the dialog
said the endpoint could not be reached and suggested a revoked key. A login
check that started with the command's path was refused with the generic
"can't be added as given", without saying the check must start with the
command name. A provider added with a pasted key kept showing its key as
"Unnamed secret" until the page was reloaded.

## What Changes

- The stored-key destination refusal carries `details.reason`
  `stored_key_destination`; the provider dialogs' Test shows it as "Not tested"
  with the remedy (paste the key, or add the provider and approve its key).
- A login check that does not start with the command name is refused with
  `details.reason` `login_check_command`, `details.field` `login_check` and
  `details.command`; Add CLI shows the refusal at the Login check field, and the
  field's hint says the check starts with the command name.
- Adding a provider reads the secrets list again after the new key's label is
  written, so every link to the key shows its name at once.

## Impact

- Backend: provider introspection gate, CLI declaration validation, domain errors.
- Frontend: provider Test verdict, Add CLI dialog, provider key labelling.
- Specs (edited in place, `skip_specs`): secret "a stored key goes only to the
  endpoint of the connection that holds it"; skill-manager "Declare a
  command-line tool without a skill" (new scenario "a path command's login
  check starts with its file name").
