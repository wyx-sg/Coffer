## 1. Frontend

- [x] 1.1 `ReplaceSecretFields`: current secret, who else uses it, new value or another secret with New secret…
- [x] 1.2 `ReplaceSecretDialog` built on it, with optional rebind, value writer, check and Add for a missing secret
- [x] 1.3 Provider Replace API key and channel Replace token / secret become wrappers adding their check
- [x] 1.4 MCP Requires, secret menus and missing-secret banners use the one dialog; `ReplaceSecretRefDialog` and `SecretSourceSwitch` removed
- [x] 1.5 Provider Edit dialog: Replace on the key row, saved with the form; Test uses the entered key
- [x] 1.6 Tests carrying acceptance markers for the new scenarios

## 2. Docs and design

- [x] 2.1 ADR one-replace-dialog-for-every-secret
- [x] 2.2 docs-site en + zh guides and contributing notes
- [x] 2.3 Design canvases updated

## 3. Close

- [x] 3.1 Frontend lint, typecheck, knip and unit tests pass
- [x] 3.2 Archive this change
