# Credentials

Coffer stores every secret you register — API keys, bot tokens — as **Fernet ciphertext** inside the local SQLite database, unlocked by a single **master key**. Encryption is transparent: features that need a secret reference it, and Coffer decrypts it in memory only when used. Plaintext never lands in logs, audit records, or events.

## Store and reference a secret

```bash
printf 'sk-xxxx' | coffer credentials set openai-key   # pipe it in, so it never lands in shell history
coffer credentials set openai-key            # or type it at a hidden prompt
coffer credentials list                      # → openai-key | yes | provider openai
coffer credentials get openai-key            # presence check only ([redacted]); not audited
coffer credentials get openai-key --show     # print the real value (an audited read)
```

- The reference name is yours to choose, and may contain slashes — that is how features namespace their own (for example `sync/github-token`).
- Other features take a **reference**, not the secret: an MCP server cites `--credential Authorization=github-token`, a model cites `--credential-ref openai-key`, a channel cites `--bot-token-ref`, and so on. The resource's configuration stores the name, never the value.
- Prefer the pipe or the prompt over `--value`, which is visible in your shell history.
- `--show` leaves a `credential_read` record in the [activity log](./activity) naming the reference — never the value.

To **rotate** a secret, `set` the same reference again. Everything that cites it picks up the new value; there is no configuration to edit and nothing to re-register.

`coffer credentials list` shows every reference any registered model, channel or MCP server cites, whether the store holds it (a probe that decrypts nothing), and who cites it — after restoring a vault without its secrets, the `no` rows are the ones to set again. `--json` carries the same fields.

## Delete a secret

```bash
coffer credentials delete github-token       # asks for confirmation; --force skips it
```

The delete is refused while anything still cites the reference, and the message says what does:

```
credential 'github-token' is still used by: mcp_server 'github'; detach or delete those resources before deleting the credential
```

Usually you do not need this command at all: deleting the resource releases the references nothing else cites.

## Where the master key lives

Exactly one backend is active at a time:

```bash
coffer credentials storage                   # show the current backend
coffer credentials storage --set keychain    # move the key into the OS keychain
coffer credentials storage --set file        # move it back to a 0600 file
```

- **file** (default) — `~/.coffer/master.key`, mode `0600`. Zero keychain prompts. This does not defend against an attacker who can already read `~/.coffer/`.
- **keychain** (opt-in) — the OS keychain. Defends against offline exfiltration of `~/.coffer/`, at the cost of at most one prompt per daemon start. Switching relocates only the key; no secret is re-encrypted. The old copy is removed last (a keychain write is read back first), so an interrupted move still leaves a working key.

::: warning Back up the master key with your database
`coffer.db` now holds only ciphertext. Restoring it requires the matching master key, so back up `~/.coffer/master.key` (or your keychain entry) alongside the database. If ciphertext exists but no key resolves, the daemon refuses to start rather than run half-blind.
:::

In the app, the storage backend is a toggle under **Settings → Security**. Individual secrets are set as you register the models, channels, and MCP servers that reference them.

## When something goes wrong

| Symptom | Meaning | Fix |
| --- | --- | --- |
| Daemon refuses to start with `MASTER_KEY_MISSING` | Ciphertext exists but no key resolves; the message names the path | Restore the key file (or unlock the keychain). Coffer never writes a new key over existing ciphertext. |
| `CREDENTIAL_UNREADABLE` | The secret is stored, but the installed key does not open it | The wrong key is installed. Restore the right one, or re-enter that secret. |
| `CREDENTIAL_LOCKED` | The OS keychain is locked or refused access | Unlock it (macOS: log in to the desktop session; Linux: unlock GNOME Keyring / KWallet). |
| `CREDENTIAL_IN_USE` on delete | A registered resource still cites the reference | Detach or delete the resources the message names, then delete again. |
| `list` shows a reference as `no` | The vault arrived without that secret | `coffer credentials set <ref>` for each one. |

Credential ciphertext moves between machines only through [Sync](./sync), and only when you opt in; the master key never travels with it and is carried separately with `coffer sync key export` / `import`.

[Activity →](/guide/activity)
