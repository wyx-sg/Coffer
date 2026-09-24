## MODIFIED Requirements

### Requirement: Ship the desktop tier as a macOS arm64 dmg
The release pipeline MUST produce, per `v*` tag, a **macOS arm64** `.dmg` containing the Tauri shell with the three frozen binaries — `coffer`, `coffer-daemon` and `coffer-mcp-shim` — embedded as Tauri `externalBin`, so that installing it requires nothing installed beforehand. macOS x64 (Intel), Linux and Windows are deliberately not built; those legs were never validated end to end. The desktop leg MUST reuse the artifacts the terminal leg already built rather than running PyInstaller a second time; the freezing is the expensive half and it is done once. This `.dmg` is the double-click install and it ships on every tag; the terminal install is the archive tier of [daemon](../daemon/spec.md), and neither tier is a substitute for the other.

#### Scenario: a release tag produces the desktop tier
- **GIVEN** a release tag matching `v*` is pushed,
- **WHEN** the release workflow finishes,
- **THEN** the release contains a macOS arm64 `.dmg` holding the shell with `coffer`, `coffer-daemon` and `coffer-mcp-shim` embedded, and no other binary,
- **AND** those binaries are the artifacts the terminal tier's build already produced, not a second PyInstaller run,
- **AND** no other platform is built.
