#!/usr/bin/env python3
"""Keep the docs site's English and Chinese trees one to one.

The site ships English at `docs-site/` and Simplified Chinese at
`docs-site/zh/`, page for page. This fails when the two drift:

- **Pages.** Every English page has a Chinese page at the same path under
  `zh/`, and every Chinese page has an English one, except the paths listed in
  :data:`EN_ONLY` and :data:`ZH_ONLY`.
- **Sidebar.** Every entry in `.vitepress/sidebar.json`, the one file both
  locales' sidebars are built from, carries an English and a Chinese label, and
  its page exists in both trees.
- **Anchors.** A Chinese page has the same heading anchors as its English page,
  so a link such as `/zh/guides/agents#adopt-an-agent` lands where the English
  one does. A translated heading keeps the English anchor with an explicit id:
  `## 纳入托管 {#adopt-an-agent}`.
- **Links.** A Chinese page links to Chinese pages, not to the English ones.

Each failure names the path. Fix a page or anchor failure by translating the
page, or by keeping its headings one to one with the English page; after
translating a page, `--stamp-anchors docs-site/zh/<path>.md` writes the English
anchors onto its headings when the two pages have the same headings in the same
order.

    .venv/bin/python scripts/check_docs_locales.py
    .venv/bin/python scripts/check_docs_locales.py --stamp-anchors docs-site/zh/guides/agents.md
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE = REPO_ROOT / "docs-site"

#: The locales besides English, each a directory under the site root.
LOCALES = ("zh",)

#: Pages that exist only in English, relative to the site root. Keep empty
#: unless a page genuinely has no Chinese counterpart, and say why.
EN_ONLY: frozenset[str] = frozenset()

#: Pages that exist only under a locale directory, relative to that directory.
ZH_ONLY: frozenset[str] = frozenset()

#: Directories under the site root that hold no pages.
_NOT_PAGES = frozenset({"node_modules", ".vitepress", "scripts", "public", *LOCALES})

_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_EXPLICIT_ID = re.compile(r"\s*\{#([^}\s]+)\}\s*$")
_LINK = re.compile(r"\]\((/[^)\s]*)\)")

# VitePress's own slugify (vitepress/dist/node: `slugify`), so a computed anchor
# is the one the built page has.
_R_CONTROL = re.compile(r"[\u0000-\u001f]")
_R_SPECIAL = re.compile(r"[\s~`!@#$%^&*()\-_+=\[\]{}|\\;:\"'“”‘’<>,.?/]+")
_R_COMBINING = re.compile(r"[̀-ͯ]")


def slugify(text: str) -> str:
    s = unicodedata.normalize("NFKD", text)
    s = _R_COMBINING.sub("", s)
    s = _R_CONTROL.sub("", s)
    s = _R_SPECIAL.sub("-", s)
    s = re.sub(r"-{2,}", "-", s)
    s = re.sub(r"^-+|-+$", "", s)
    s = re.sub(r"^(\d)", r"_\1", s)
    return s.lower()


def _plain(heading: str) -> str:
    """A heading's rendered text: what VitePress slugifies."""
    parts = re.split(r"(`[^`]*`)", heading)
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            out.append(part[1:-1])
            continue
        part = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", part)
        part = re.sub(r"<[^>]+>", "", part)
        part = part.replace("**", "").replace("*", "")
        out.append(part)
    return "".join(out).strip()


def headings(text: str) -> list[tuple[int, int, str, str]]:
    """(line index, level, heading text, anchor) for each heading outside code."""
    lines = text.split("\n")
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start = i + 1
                break
    found: list[tuple[int, int, str, str]] = []
    used: set[str] = set()
    fence: str | None = None
    for i in range(start, len(lines)):
        line = lines[i]
        m = _FENCE.match(line)
        if m:
            if fence is None:
                fence = m.group(1)
            elif m.group(1) == fence:
                fence = None
            continue
        if fence is not None:
            continue
        h = _HEADING.match(line)
        if not h:
            continue
        body = h.group(2)
        explicit = _EXPLICIT_ID.search(body)
        if explicit:
            anchor = explicit.group(1)
            body = body[: explicit.start()]
        else:
            base = slugify(_plain(body))
            anchor, n = base, 1
            while anchor in used:
                anchor = f"{base}-{n}"
                n += 1
        used.add(anchor)
        found.append((i, len(h.group(1)), body, anchor))
    return found


def _pages(root: Path, skip: frozenset[str]) -> set[str]:
    out: set[str] = set()
    for path in root.rglob("*.md"):
        rel = path.relative_to(root)
        if rel.parts[0] in skip:
            continue
        out.add(rel.as_posix())
    return out


def _page_for_link(link: str) -> str:
    """`/guides/agents#x` -> `guides/agents.md`; `/start/` -> `start/index.md`."""
    path = link.split("#", 1)[0].split("?", 1)[0].lstrip("/")
    if path == "" or path.endswith("/"):
        return f"{path}index.md"
    return path if path.endswith(".md") else f"{path}.md"


def check(site: Path) -> list[str]:
    errors: list[str] = []
    en_pages = _pages(site, _NOT_PAGES)
    for locale in LOCALES:
        loc_root = site / locale
        loc_pages = _pages(loc_root, frozenset()) if loc_root.is_dir() else set()
        for rel in sorted(en_pages - loc_pages - EN_ONLY):
            errors.append(f"{locale}/{rel}: missing — the English page {rel} has no {locale} page")
        for rel in sorted(loc_pages - en_pages - ZH_ONLY):
            errors.append(f"{locale}/{rel}: has no English page {rel}")

        for rel in sorted(en_pages & loc_pages):
            en_text = (site / rel).read_text(encoding="utf-8")
            loc_text = (loc_root / rel).read_text(encoding="utf-8")
            en_anchors = {a for *_, a in headings(en_text)}
            loc_anchors = {a for *_, a in headings(loc_text)}
            for anchor in sorted(en_anchors - loc_anchors):
                errors.append(f"{locale}/{rel}: missing heading anchor #{anchor}")
            for anchor in sorted(loc_anchors - en_anchors):
                errors.append(f"{locale}/{rel}: heading anchor #{anchor} is not on {rel}")
            for link in _LINK.findall(loc_text):
                if link.startswith(f"/{locale}/") or link == f"/{locale}":
                    continue
                if _page_for_link(link) in en_pages:
                    errors.append(f"{locale}/{rel}: links the English page {link}")

    errors += _check_sidebar(site, en_pages)
    return errors


def _check_sidebar(site: Path, en_pages: set[str]) -> list[str]:
    path = site / ".vitepress" / "sidebar.json"
    if not path.exists():
        return [f"{path.relative_to(site.parent)}: missing"]
    errors: list[str] = []
    langs = ("en", *LOCALES)
    data = json.loads(path.read_text(encoding="utf-8"))
    for section, groups in data.items():
        for group in groups:
            for lang in langs:
                if not group.get("text", {}).get(lang):
                    errors.append(f"sidebar.json: group in {section} has no {lang} label")
            for item in group.get("items", []):
                link = item.get("link", "")
                for lang in langs:
                    if not item.get("text", {}).get(lang):
                        errors.append(f"sidebar.json: {link} has no {lang} label")
                page = _page_for_link(link)
                if page not in en_pages:
                    errors.append(f"sidebar.json: {link} has no English page {page}")
                for locale in LOCALES:
                    if not (site / locale / page).exists():
                        errors.append(f"sidebar.json: {link} has no {locale} page {locale}/{page}")
    return errors


def stamp_anchors(site: Path, loc_page: Path) -> str | None:
    """Write the English page's anchors onto a translated page's headings.

    Returns an error when the two pages' headings are not one to one.
    """
    rel_parts = loc_page.resolve().relative_to(site.resolve()).parts
    en_page = site.joinpath(*rel_parts[1:])
    en = headings(en_page.read_text(encoding="utf-8"))
    text = loc_page.read_text(encoding="utf-8")
    loc = headings(text)
    if [lvl for _, lvl, *_ in en] != [lvl for _, lvl, *_ in loc]:
        return (
            f"{loc_page}: {len(loc)} headings against {len(en)} on {en_page.name} "
            "(or levels differ); make them one to one first"
        )
    lines = text.split("\n")
    for (_, _, _, anchor), (idx, level, body, _) in zip(en, loc, strict=True):
        lines[idx] = f"{'#' * level} {body.strip()} {{#{anchor}}}"
    loc_page.write_text("\n".join(lines), encoding="utf-8")
    return None


def main(argv: list[str]) -> int:
    if argv[:1] == ["--stamp-anchors"]:
        problems = [p for p in (stamp_anchors(SITE, Path(a)) for a in argv[1:]) if p]
        for problem in problems:
            print(f"check_docs_locales: {problem}", file=sys.stderr)
        return 1 if problems else 0
    errors = check(SITE)
    for error in errors:
        print(f"check_docs_locales: docs-site/{error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
