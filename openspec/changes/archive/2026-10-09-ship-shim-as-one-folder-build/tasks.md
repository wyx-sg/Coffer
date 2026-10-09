## 1. Build

- [x] 1.1 Shim spec: one-folder build with `coffer-mcp-shim-lib`, no `collect_submodules`, daemon stacks excluded
- [x] 1.2 `build_binaries.sh` moves the shim and its folder up into `dist/`
- [x] 1.3 Runtime hook marking the unpack directory of the three one-file binaries; spec gate checks it

## 2. Install paths

- [x] 2.1 Frozen-start deploy copies the library folder (from beside the daemon or the app's `Resources`)
- [x] 2.2 `install.sh` and `coffer update` install the library folder
- [x] 2.3 Shim resolver falls back to the deployed `~/.coffer/bin/coffer-mcp-shim`

## 3. Release and app

- [x] 3.1 Archive, notarisation and app staging carry the library folder; the app ships the shim in `Contents/Resources`
- [x] 3.2 Smoke test checks the shim's payload and runs against the built app too

## 4. Cleanup and docs

- [x] 4.1 The daemon deletes marked unpack directories whose process has exited
- [x] 4.2 ADR and docs-site (en + zh)
