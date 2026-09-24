## 1. Code

- [x] 1.1 `coffer sync remote set` builds on the stored remote and changes only the options it is given; `--with-credentials/--without-credentials` is tri-state
- [x] 1.2 The CLI maps every `httpx.TransportError` to exit 3 with the daemon-unreachable message
- [x] 1.3 A synced internal-default move releases the holder just before the target's write and reverts it if that write fails
- [x] 1.4 Shelving an oversized knowledge item clears its cut-off count and tolerates material that has since gone

## 2. Specs and docs

- [x] 2.1 Deltas for agent-registry and vault-sync
- [x] 2.2 Every new scenario's test carries its acceptance marker
- [x] 2.3 `docs-site/guide/sync.md` describes the tri-state credential flag and what re-running `remote set` keeps

## 3. Close

- [x] 3.1 Run make verify
- [x] 3.2 Archive the change
