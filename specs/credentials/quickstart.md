# Quickstart — Credentials

Everything a secret does inside Coffer, from a terminal. There is no page that
lists stored secrets, by design: a secret is entered where the thing that needs
it is configured, and managed from here.

## Prerequisites

- A running daemon (`coffer daemon start`). Every command below goes through it.

## Store a secret

Pipe it in, so it never lands in shell history:

```bash
printf 'ghp_xxxxxxxxxxxx' | coffer credentials set github-token
# → stored: github-token
```

On a terminal with no pipe you are prompted with the input hidden. `--value` is
accepted and is documented as unsafe — the value lands in shell history.

The reference (`github-token`) is yours to choose. It may contain slashes, which
is how kinds namespace their own: `mcp_server` dialogs write `<server>.<key>`,
channels write their own.

## Reference it from a resource

```bash
coffer mcp add github --http https://api.github.com/mcp \
  --credential "Authorization=github-token"
```

The resource config stores `github-token`, never the secret. The same is true of
a channel's bot token and a provider's API key — every kind that needs a secret
cites a ref.

## See what the vault expects, and what it has

```bash
coffer credentials list
# Ref            Present in store
# github-token   yes
```

The refs come from registered resources; "present" comes from a probe that does
not decrypt anything and is not audited. A vault copied to a new machine without
its secrets shows `no` in that column for each one to re-enter.

## Read one back

```bash
coffer credentials get github-token
# → [redacted]

coffer credentials get github-token --show
# → ghp_xxxxxxxxxxxx
```

`--show` goes through the audited read. Every deliberate look at a secret leaves
a `credential_read` row carrying the ref — never the value — so `coffer audit
list` can answer "when was this read, and by which surface".

## Rotate one

```bash
printf '<new value>' | coffer credentials set github-token
```

Nothing else changes: the resource still cites the same ref, so there is no
config to update and no resource to re-register.

## Delete one

```bash
coffer credentials delete github-token
# Delete credential 'github-token'? [y/N]
```

`--force` skips the prompt. If something still cites the ref the delete is
refused and the message names it:

```
credential 'github-token' is referenced by: mcp_server:github;
detach or delete those resources before deleting the credential
```

Deleting the *resource* instead releases the refs nothing else cites, so the
common case needs no explicit credential delete at all.

## Where the master key lives

```bash
coffer credentials storage
# → master key storage: file
```

`file` means `~/.coffer/master.key`, mode `0600`, beside the database. That is
the default and matches the threat model: an attacker who can already read
`~/.coffer/` is out of scope.

Move it into the OS keychain when you want the vault directory to be worthless
on its own:

```bash
coffer credentials storage --set keychain
```

The keychain copy is written and read back before the file is removed, so an
interrupted move leaves the key resolvable from the file. Moving back is the
same command with `--set file`. Settings → Security does the same thing with a
confirmation, because the move can cost an OS authorisation prompt on every
daemon start afterwards.

## When something goes wrong

| Symptom                                                   | Meaning                                                            | Fix                                                                                        |
| --------------------------------------------------------- | ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- |
| Daemon refuses to start: `MASTER_KEY_MISSING`             | Ciphertext exists and no key resolves — the message names the path | Restore the key file (or unlock the keychain). Coffer will not write a new key over ciphertext. |
| `CREDENTIAL_UNREADABLE`                                   | The row exists but this key does not open it                       | The wrong key is installed. Restore the right one, or re-enter that secret.                  |
| `CREDENTIAL_LOCKED`                                       | The OS keychain is locked or refused                               | Unlock it (macOS: log in to the GUI; Linux: unlock GNOME-keyring / KWallet).                  |
| `CREDENTIAL_IN_USE` on delete                             | A registered resource still cites the ref                          | Detach or delete the resources the message names, then delete again.                          |
| `coffer credentials list` shows a ref as not present       | The vault arrived without its secrets                              | `coffer credentials set <ref>` for each one.                                                  |

## Carrying secrets to another machine

Ciphertext travels with the vault when you ask for it; the key does not travel
with it, ever. Both halves are spec vault-sync's: the convergence carries
`credentials/*.enc` under an explicit opt-in, and the key moves only through the
deliberate out-of-band export/import, which moves key material and nothing else.

A vault without its key works for everything except *reading* secrets stored
previously — re-enter those with `coffer credentials set`.
