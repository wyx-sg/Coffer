"""The bundled starter skill catalog (FR-032).

A small curated seed shipped with Coffer so discovery works out of the box.
Each entry points at a public Git repo + subpath that the install path fetches
through the same SSRF-guarded, validated, content-scanned pipeline as a manual
`coffer skill fetch`. Expanding this list (or fetching a remote index) is
future work; an install whose coordinates no longer resolve fails cleanly at
fetch/validate time rather than corrupting anything.
"""

from __future__ import annotations

# name, description, git_url, git_ref, git_subpath, publisher
BUILTIN_CATALOG: list[dict[str, str]] = [
    {
        "name": "pdf",
        "description": "Fill, read, and manipulate PDF files.",
        "git_url": "https://github.com/anthropics/skills",
        "git_ref": "main",
        "git_subpath": "document-skills/pdf",
        "publisher": "anthropics",
    },
    {
        "name": "docx",
        "description": "Create and edit Microsoft Word documents.",
        "git_url": "https://github.com/anthropics/skills",
        "git_ref": "main",
        "git_subpath": "document-skills/docx",
        "publisher": "anthropics",
    },
    {
        "name": "xlsx",
        "description": "Create and edit Microsoft Excel spreadsheets.",
        "git_url": "https://github.com/anthropics/skills",
        "git_ref": "main",
        "git_subpath": "document-skills/xlsx",
        "publisher": "anthropics",
    },
    {
        "name": "pptx",
        "description": "Create and edit Microsoft PowerPoint presentations.",
        "git_url": "https://github.com/anthropics/skills",
        "git_ref": "main",
        "git_subpath": "document-skills/pptx",
        "publisher": "anthropics",
    },
]
