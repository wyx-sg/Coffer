## 1. Backend

- [x] 1.1 Scan: skill files (existing rules) and MCP server env / headers / http_api headers, no values out
- [x] 1.2 Import: skill → standalone secret + file rewrite; server → own ref + `update_config`; dry run; `secret_imported` audit
- [x] 1.3 Routes `POST /secrets/scan`, `POST /secrets/import`, schemas, contract regenerated
- [x] 1.4 Tests carrying the scenarios' acceptance markers

## 2. Frontend

- [x] 2.1 Codegen; Find plaintext keys dialog (findings by source → Review changes → Apply → result)
- [x] 2.2 Secrets page header and empty state entry; i18n en + zh; tests

## 3. Docs

- [x] 3.1 docs-site guides/secrets (en + zh)
