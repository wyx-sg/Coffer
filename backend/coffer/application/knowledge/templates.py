"""The templates a new collection can start from (spec knowledge "Start a
collection from a template").

A template is a handful of files copied into the new collection once, after
which they are the collection's own: Coffer never reads them as rules of its
own and never rewrites them (ADR knowledge-collections-own-their-format).
``blank`` is a README with the collection's heading and description and
nothing else; ``llm-wiki`` adds the rules of a wiki compiled from kept sources
(``AGENTS.md``) and an ``index.md``, and its README declares both. Each
template lives under ``skill_assets/templates/<name>/``, shipped with the
package; its ``README.md`` carries ``{name}`` and ``{description}``.
"""

from __future__ import annotations

from importlib import resources

from coffer.infrastructure.knowledge.collection_files import blank_readme

BLANK = "blank"
LLM_WIKI = "llm-wiki"
#: Every template, the default first.
TEMPLATES = (LLM_WIKI, BLANK)
DEFAULT_TEMPLATE = LLM_WIKI

_README = "README.md"


def _folder(name: str) -> resources.abc.Traversable:
    return resources.files(__package__).joinpath("skill_assets", "templates", name)


def render(template: str, collection: str, description: str | None) -> dict[str, str]:
    """The files ``template`` gives a collection named ``collection``, by
    path relative to it. An unknown template is refused."""
    if template not in TEMPLATES:
        raise ValueError(f"unknown template {template!r}")
    if template == BLANK:
        return {_README: blank_readme(collection, description)}
    text = (description or "").strip()
    files: dict[str, str] = {}
    for entry in sorted(_folder(template).iterdir(), key=lambda e: e.name):
        if not entry.is_file() or not entry.name.endswith(".md"):
            continue
        body = entry.read_text(encoding="utf-8")
        if entry.name == _README:
            body = body.replace("{name}", collection)
            body = body.replace("{description}\n\n", f"{text}\n\n" if text else "")
        files[entry.name] = body
    return files


__all__ = ["BLANK", "DEFAULT_TEMPLATE", "LLM_WIKI", "TEMPLATES", "render"]
