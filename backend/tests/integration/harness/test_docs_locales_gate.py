"""Tests for scripts/check_docs_locales.py — the docs site's two-language gate.

The gate fails when the English tree and the `zh/` tree stop being one to one:
a page, a sidebar entry or a heading anchor on one side only, or a Chinese page
linking an English one. Each check is proved on a throwaway site under
`tmp_path`, and the real site is proved clean.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from .conftest import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "check_docs_locales.py"


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_docs_locales", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_docs_locales"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sidebar(site: Path, *links: str) -> None:
    items = [{"text": {"en": link, "zh": link}, "link": link} for link in links]
    data = {"guides": [{"text": {"en": "Guides", "zh": "指南"}, "items": items}]}
    _write(site, ".vitepress/sidebar.json", json.dumps(data))


@pytest.fixture
def site(tmp_path: Path) -> Path:
    _write(tmp_path, "guides/agents.md", "# Agents\n\n## Adopt an agent\n\nText.\n")
    _write(
        tmp_path,
        "zh/guides/agents.md",
        "# 智能体 {#agents}\n\n## 纳入托管 {#adopt-an-agent}\n\n见[技能](/zh/guides/agents)。\n",
    )
    _sidebar(tmp_path, "/guides/agents")
    return tmp_path


def test_a_matching_site_passes(gate, site) -> None:
    assert gate.check(site) == []


def test_an_english_page_without_a_chinese_twin_fails_with_its_path(gate, site) -> None:
    _write(site, "guides/skills.md", "# Skills\n")
    assert gate.check(site) == [
        "zh/guides/skills.md: missing — the English page guides/skills.md has no zh page"
    ]


def test_a_chinese_page_without_an_english_one_fails(gate, site) -> None:
    _write(site, "zh/guides/extra.md", "# 多余\n")
    assert gate.check(site) == ["zh/guides/extra.md: has no English page guides/extra.md"]


def test_a_missing_heading_anchor_fails(gate, site) -> None:
    _write(site, "zh/guides/agents.md", "# 智能体 {#agents}\n\n## 纳入托管\n")
    errors = gate.check(site)
    assert "zh/guides/agents.md: missing heading anchor #adopt-an-agent" in errors


def test_headings_inside_code_blocks_are_not_anchors(gate, site) -> None:
    _write(site, "guides/agents.md", "# Agents\n\n```sh\n# a comment\n```\n\n## Adopt an agent\n")
    assert gate.check(site) == []


def test_a_chinese_page_linking_an_english_page_fails(gate, site) -> None:
    _write(
        site,
        "zh/guides/agents.md",
        "# 智能体 {#agents}\n\n## 纳入托管 {#adopt-an-agent}\n\n见[智能体](/guides/agents#x)。\n",
    )
    assert gate.check(site) == ["zh/guides/agents.md: links the English page /guides/agents#x"]


def test_a_sidebar_entry_needs_both_labels_and_both_pages(gate, site) -> None:
    data = {
        "guides": [
            {
                "text": {"en": "Guides", "zh": "指南"},
                "items": [
                    {"text": {"en": "Agents"}, "link": "/guides/agents"},
                    {"text": {"en": "Skills", "zh": "技能"}, "link": "/guides/skills"},
                ],
            }
        ]
    }
    _write(site, ".vitepress/sidebar.json", json.dumps(data))
    errors = gate.check(site)
    assert "sidebar.json: /guides/agents has no zh label" in errors
    assert "sidebar.json: /guides/skills has no English page guides/skills.md" in errors
    assert "sidebar.json: /guides/skills has no zh page zh/guides/skills.md" in errors


def test_slugify_matches_vitepress(gate) -> None:
    assert gate.slugify("What is Coffer?") == "what-is-coffer"
    assert gate.slugify("coffer__search_tools") == "coffer-search-tools"
    assert gate.slugify("1.0 layout") == "_1-0-layout"
    assert gate.slugify("Don’t “quote”") == "don-t-quote"  # noqa: RUF001


def test_duplicate_headings_get_numbered_anchors(gate) -> None:
    anchors = [a for *_, a in gate.headings("## Example\n\n## Example\n\n## `Example`\n")]
    assert anchors == ["example", "example-1", "example-2"]


def test_stamp_anchors_writes_the_english_ids(gate, site) -> None:
    page = site / "zh" / "guides" / "agents.md"
    page.write_text("# 智能体\n\n## 纳入托管\n", encoding="utf-8")
    assert gate.stamp_anchors(site, page) is None
    assert (
        page.read_text(encoding="utf-8") == "# 智能体 {#agents}\n\n## 纳入托管 {#adopt-an-agent}\n"
    )


def test_stamp_anchors_refuses_pages_whose_headings_differ(gate, site) -> None:
    page = site / "zh" / "guides" / "agents.md"
    page.write_text("# 智能体\n", encoding="utf-8")
    assert gate.stamp_anchors(site, page) is not None


def test_the_real_site_is_one_to_one(gate) -> None:
    assert gate.check(REPO_ROOT / "docs-site") == []
