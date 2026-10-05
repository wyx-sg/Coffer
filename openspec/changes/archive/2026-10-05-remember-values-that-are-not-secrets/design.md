## Context

Plaintext detection is one detector (spec secret "Detect plaintext secrets with
the bundled rules"). Push anyway today records allowed blob hashes in
`local/sync/round.json` (`plaintext_allowed`); the Secrets page keeps nothing.

## Decisions

### A value is remembered by an HMAC fingerprint

`fingerprint = HMAC-SHA256(derive_purpose_key(master_key,
b"coffer-plaintext-ignore-key/v1"), value)`, hex. A plain SHA-256 of a
low-entropy password could be checked against guesses by anyone who reads the
file; the HMAC needs the master key, which already opens every secret. Machines
that share a vault share the master key, so a fingerprint means the same on
each, though the list itself stays machine-local like the rest of `local/`.

### Identity is the value alone

The person's statement is about the value ("this string is not a secret"), so
matching is by fingerprint only, not by path, line or rule: moving the line,
editing the file or renaming it does not bring it back, and the same harmless
value elsewhere is not re-asked. Each entry still records the place, rule and
key where it was first found, who said so and when, for the dialog's ignored
list and the audit.

### Where fingerprints are made

Values never leave infrastructure. The push check's `find_plaintext` returns a
fingerprint with each place (the wiring closes over the master key manager);
the round record keeps it so Push anyway can remember what the last round found
without reading the files again. The scan service fingerprints `Hit.value` the
same way. With no master key there is no fingerprint: nothing is filtered, and
ignore/unignore are refused with `SECRET_LOCKED`.

### Push anyway keeps allowing blobs

Push anyway still allows the exact blobs (as before) and now also remembers the
values. The blob allow costs nothing, keeps working when no fingerprint can be
made, and needs no change to existing local state.

### Rejected

- **A `gitleaks:allow`-style marker in the file**: edits the person's own
  files, and a knowledge note is not code.
- **Syncing the list**: a new vault document kind for a convenience; each
  machine is asked at most once per value.
