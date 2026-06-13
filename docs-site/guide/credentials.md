# Credentials

Coffer stores every secret you register — API keys, bot tokens — as **Fernet ciphertext** inside the local SQLite database, unlocked by a single **master key**. Encryption is transparent: features that need a secret reference it, and Coffer decrypts it in memory only when used. Plaintext never lands in logs, audit records, or events.

## Store and reference a secret

```bash
coffer credentials set openai-key            # paste the value at a hidden prompt (or pipe via stdin)
coffer credentials list                      # → openai-key | present
coffer credentials get openai-key            # presence check only ([redacted])
coffer credentials get openai-key --show     # print the real value (an audited read)
coffer credentials delete openai-key
```

- Other features take a **reference**, not the secret: a model cites `--credential-ref openai-key`, a channel cites `--bot-token-ref`, and so on.
- Prefer the prompt or stdin over `--value`, which is visible in your shell history.

## Where the master key lives

Exactly one backend is active at a time:

```bash
coffer credentials storage                   # show the current backend
coffer credentials storage --set keychain    # move the key into the OS keychain
coffer credentials storage --set file        # move it back to a 0600 file
```

- **file** (default) — `~/.coffer/master.key`, mode `0600`. Zero keychain prompts. This does not defend against an attacker who can already read `~/.coffer/`.
- **keychain** (opt-in) — the OS keychain. Defends against offline exfiltration of `~/.coffer/`, at the cost of at most one prompt per daemon start. Switching relocates only the key; no secret is re-encrypted.

::: warning Back up the master key with your database
`coffer.db` now holds only ciphertext. Restoring it requires the matching master key, so back up `~/.coffer/master.key` (or your keychain entry) alongside the database. If ciphertext exists but no key resolves, the daemon refuses to start rather than run half-blind.
:::

In the app, the storage backend is a toggle under **Settings → Security**. Individual secrets are set as you register the models, channels, and MCP servers that reference them.

[Web UI →](/guide/web-ui)
