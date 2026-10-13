## 1. Files stay in place

- [x] 1.1 Delete the sweep's loose-document filing and its quiet-minute retry
- [x] 1.2 Restore a deleted collection's files byte for byte, root files, folders and assets included
- [x] 1.3 Tests: sweeps leave every file in place; an upload moves nothing; root files read, listed and restored

## 2. Links and checks

- [x] 2.1 Resolve and check standard relative links; add `outside_link`
- [x] 2.2 Count links in collection files, the README and sources for reachability; never check a source's links
- [x] 2.3 `evidence`, `sourceless_types`, page `verify_after_days`; free-text types
- [x] 2.4 Carry standard links on a page's read

## 3. Uploads and Confluence imports

- [x] 3.1 One frontmatter per Markdown upload, nested block merged
- [x] 3.2 Confluence Storage Format converter, exports in JSON and `*.storage.xml`, storage markers in Markdown
- [x] 3.3 Assets under `assets/confluence-<id>-v<version>/`, reuse or suffix the folder
- [x] 3.4 Upload report, `replaces` and `dry_run` on the route and the CLI
- [x] 3.5 `display_body` on a read of a file holding storage markers
- [x] 3.6 Descriptions drawn from prose only, never from tables, labels or notices

## 4. Reading

- [x] 4.1 Sanitised HTML in the Knowledge reader; `display_body` in the preview
- [x] 4.2 Open standard relative links in the reader; label `outside_link`
- [x] 4.3 Show a partial upload's issues

## 5. Docs

- [x] 5.1 Knowledge spec and data model
- [x] 5.2 docs-site in English and Chinese, CLI reference
- [x] 5.3 `coffer-guide` skill source
- [x] 5.4 ADRs: files stay where their writer put them; Confluence import from an export the person fetched
