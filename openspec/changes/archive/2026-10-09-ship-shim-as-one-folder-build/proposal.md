## Why

Every MCP session an agent opens starts a `coffer-mcp-shim`. The shim was a
PyInstaller one-file binary: each start unpacked its whole archive (about
170 MB on macOS, roughly two seconds) into `$TMPDIR/_MEI*`, ran as a bootloader
plus a child process, and left the unpacked copy behind whenever the client
killed it. One machine collected 1,155 such directories, 17 GB, in a week. The
shim also froze every `coffer` submodule, so it carried the daemon's
dependencies (Pillow, numpy, cryptography, keyring, test libraries) to forward
JSON-RPC over loopback.

## What Changes

- The shim becomes a one-folder build: the executable plus a
  `coffer-mcp-shim-lib/` folder beside it. It unpacks nothing, runs as one
  process, and freezes only what its entry script imports (about 30 MB).
- The CLI archive carries the folder beside the four binaries; `install.sh`,
  `coffer update` and the daemon's frozen-start deploy put it beside the shim.
- The desktop app ships the shim and its folder in `Contents/Resources`
  (`Contents/MacOS` may hold only code); `coffer` and `coffer-daemon` stay
  `externalBin`. The app's daemon writes the deployed
  `~/.coffer/bin/coffer-mcp-shim` into agent configs.
- The three single-file binaries mark their unpack directory with their pid,
  and the daemon deletes the marked directories whose process has exited.
- The release smoke test fails a shim whose library folder is missing, carries
  the daemon's stacks, or is over 60 MB, and also runs against the built app.

## Impact

- Specs: daemon ("Release the macOS arm64 terminal archive", "Deploy frozen
  sibling binaries and back up the history database before migrating",
  "Upgrade the installed binaries from the command line", new "Delete what
  exited one-file binaries unpacked"), desktop-app ("Ship the desktop tier as a
  macOS arm64 dmg").
- Code: `backend/*.spec`, `backend/packaging/rth_unpack_owner.py`,
  `application/binary_deploy.py`, `application/agent/mcp_service.py`,
  `infrastructure/daemon/binary_update.py`, `infrastructure/daemon/unpack_keepalive.py`,
  `scripts/build_binaries.sh`, `scripts/smoke_test_bundle.sh`,
  `scripts/check_pyinstaller_specs.py`, `docs-site/public/install.sh`,
  `desktop/tauri*.conf.json`, `Makefile`, `.github/workflows/release.yml`.
- Docs: ADR distribution-pyinstaller, docs-site architecture distribution and
  daemon pages (en + zh).
