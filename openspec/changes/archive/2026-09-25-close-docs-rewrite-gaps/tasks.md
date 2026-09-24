## 1. Daemon

- [ ] 1.1 The status probe reports `ready` / `draining`; the phase type drops `starting`
- [ ] 1.2 `coffer daemon status` reports a stopped daemon without spawning one and exits non-zero (`--json` → `{"status": "stopped"}`)

## 2. Providers and agents

- [ ] 2.1 `apiKeyHelper` names the coffer CLI by absolute path; de-projection recognises the absolute and the legacy bare form
- [ ] 2.2 Spec text: projection target `<config_dir>/settings.json`; Claude Code's `agents/` entry under key `subagents`

## 3. Memory

- [ ] 3.1 `feedback` entries file into their project's partition when they carry a project root, else `global`
- [ ] 3.2 Spec text: distil runs on its own upkeep interval

## 4. Internal engine

- [ ] 4.1 Rename the Settings requirement and scenario to "Settings → Coffer's model"; update the TS acceptance marker and the citation that quote them

## 5. Channels

- [ ] 5.1 SeaTalk group replies attach through the thread rooted at the triggering message
- [ ] 5.2 `require_mention` / `ignore_other_mentions` are editable from the detail page, `coffer channel register` and `coffer channel set`

## 6. Web UI

- [ ] 6.1 The MCP JSON import reviews an HTTP server's `headers` for secrets like `env`

## 7. Sync

- [ ] 7.1 The 60-second interval floor on the route, the CLI and the web form
- [ ] 7.2 `coffer sync remote pause` / `resume`
- [ ] 7.3 Spec text: the publish-side deletion guard at step 1, the apply-side one at step 4

## 8. Close

- [ ] 8.1 Every new scenario's test carries its acceptance marker
- [ ] 8.2 Docs-site pages that recorded these gaps describe the new behaviour
- [ ] 8.3 Run `make verify`
- [ ] 8.4 Archive the change
