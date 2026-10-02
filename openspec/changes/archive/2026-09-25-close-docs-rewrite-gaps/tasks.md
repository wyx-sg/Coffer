## 1. Daemon

- [x] 1.1 The status probe reports `ready` / `draining`; the phase type drops `starting`
- [x] 1.2 `coffer daemon status` reports a stopped daemon without spawning one and exits non-zero (`--json` → `{"status": "stopped"}`)

## 2. Providers and agents

- [x] 2.1 `apiKeyHelper` names the coffer CLI by absolute path; de-projection recognises the absolute and the legacy bare form
- [x] 2.2 Spec text: projection target `<config_dir>/settings.json`; Claude Code's `agents/` entry under key `subagents`

## 3. Memory

- [x] 3.1 `feedback` entries file into their project's partition when they carry a project root, else `global`
- [x] 3.2 Spec text: distil runs on its own upkeep interval

## 4. Internal engine

- [x] 4.1 Rename the Settings requirement and scenario to "Settings → Coffer's model"; update the TS acceptance marker and the citation that quote them

## 5. Channels

- [x] 5.1 SeaTalk group replies attach through the thread rooted at the triggering message
- [x] 5.2 `require_mention` / `ignore_other_mentions` are editable from the detail page, `coffer channel register` and `coffer channel set`

## 6. Web UI

- [x] 6.1 The MCP JSON import reviews an HTTP server's `headers` for secrets like `env`

## 7. Sync

- [x] 7.1 The 60-second interval floor on the route, the CLI and the web form
- [x] 7.2 `coffer sync remote pause` / `resume`
- [x] 7.3 Spec text: the publish-side deletion guard at step 1, the apply-side one at step 4

## 8. Close

- [x] 8.1 Every new scenario's test carries its acceptance marker
- [x] 8.2 Docs-site pages that recorded these gaps describe the new behaviour
- [x] 8.3 Run `make verify`
- [x] 8.4 Archive the change
