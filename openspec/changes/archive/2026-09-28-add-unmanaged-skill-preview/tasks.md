## 1. Backend

- [x] 1.1 `unmanaged_ops.get_unmanaged` finds one entry through the list's scan and returns its view, SKILL.md description and folder
- [x] 1.2 `GET /agents/{uid}/unmanaged-skills/{skill}`, `.../files`, `.../files/content` (read-only, `location` required, `file_ops` containment)
- [x] 1.3 `coffer skill files|cat --agent --location`
- [x] 1.4 Contract: three operations and `UnmanagedSkillDetailOut`; frontend codegen

## 2. Frontend

- [x] 2.1 `UnmanagedSkillDetailPage` at `/agents/:uid/skills/unmanaged/:location/:name` with Overview and Files tabs, back link to the agent's Skills tab
- [x] 2.2 Header actions: Open folder, Adopt (navigates to `/skills/{uid}`), Delete (confirm, back to the Skills tab)
- [x] 2.3 `SkillFileBrowser` shared by the managed and unmanaged file trees; read-only unmanaged viewer
- [x] 2.4 Unmanaged table: row click opens the page, no Open folder button; en/zh strings

## 3. Tests and docs

- [x] 3.1 HTTP tests: metadata, tree, content, binary, invalid folder, `..` / absolute / symlink escape refused, unknown entry 404, bad location 422 — acceptance markers for "preview an unmanaged skill's metadata and files", "an invalid unmanaged skill still opens and says why", "reject reading a path outside an unmanaged skill folder"
- [x] 3.2 CLI test for "read an unmanaged skill's files from the command line"
- [x] 3.3 Frontend tests for "open an unmanaged skill's detail page from the agent's Skills tab", "adopt or delete an unmanaged skill from its detail page" and the invalid-folder notice
- [x] 3.4 Skills guide, CLI and REST references
- [x] 3.5 `make verify`, then archive this change
