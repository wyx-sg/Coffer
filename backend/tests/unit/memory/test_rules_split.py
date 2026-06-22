"""Unit: autonomous rules-lane split orchestration (no LLM — fake classifier)."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Callable

import pytest

from coffer.application.memory.rules_split import run_rules_split, split_oversized_rules
from coffer.domain.provider.config import Protocol, ProviderConfig, ResolvedConnection
from coffer.infrastructure.knowledge.paths import rule_file_path, rules_dir, rules_path
from coffer.infrastructure.memory.rules_files import append_rule, count_rules, rule_bullets


def _model() -> ResolvedConnection:
    return ResolvedConnection(
        config=ProviderConfig(
            protocol=Protocol.OLLAMA,
            base_url="http://localhost:11434",
            credential_ref=None,
        ),
        model="llama3",
    )


class _Llm:
    """Fake LlmCompletionPort returning queued classification JSON per call."""

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)

    async def complete(self, *, system, user, model, credential_resolver) -> str:  # type: ignore[no-untyped-def]
        return self._responses.pop(0)


def _assign(n: int, cat: Callable[[int], str]) -> str:
    return json.dumps({"assignments": [{"index": i, "category": cat(i)} for i in range(n)]})


pytestmark = pytest.mark.asyncio


class _Scripted:
    """A fake classifier driving a scripted sequence of rule→slug mappings — one
    script per ``split_oversized_rules`` call (last script repeats)."""

    def __init__(self, *scripts: Callable[[list[str]], dict[str, str]]) -> None:
        self._scripts = scripts
        self.calls = 0

    async def __call__(self, rules: list[str]) -> dict[str, str]:
        fn = self._scripts[min(self.calls, len(self._scripts) - 1)]
        self.calls += 1
        return fn(rules)


def _seed(store_dir: pathlib.Path, n: int) -> None:
    for i in range(n):
        append_rule(rules_path(store_dir), f"rule {i}")


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


async def test_below_threshold_is_noop(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    _seed(store_dir, 10)
    classify = _Scripted(lambda rules: dict.fromkeys(rules, "git"))
    written = await split_oversized_rules(store_dir, threshold=100, classify=classify)
    assert written == 0
    assert classify.calls == 0  # never even asked the classifier
    assert rules_path(store_dir).exists()
    assert sorted(p.name for p in rules_dir(store_dir).glob("*.md")) == ["rules.md"]


async def test_over_threshold_splits_and_removes_source(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    _seed(store_dir, 150)

    def split_two(rules: list[str]) -> dict[str, str]:
        return {r: ("alpha" if i < 120 else "beta") for i, r in enumerate(rules)}

    classify = _Scripted(split_two)
    written = await split_oversized_rules(store_dir, threshold=100, classify=classify)
    assert written >= 2
    assert not rules_path(store_dir).exists()  # source redistributed + removed
    assert count_rules(_text(rule_file_path(store_dir, "alpha"))) == 120
    assert count_rules(_text(rule_file_path(store_dir, "beta"))) == 30


async def test_recursively_splits_oversized_result_file(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    _seed(store_dir, 150)

    def pass1(rules: list[str]) -> dict[str, str]:
        return {r: ("big" if i < 120 else "small") for i, r in enumerate(rules)}

    def pass2(rules: list[str]) -> dict[str, str]:  # re-split the oversized "big"
        return {r: ("big-a" if i < 60 else "big-b") for i, r in enumerate(rules)}

    classify = _Scripted(pass1, pass2)
    await split_oversized_rules(store_dir, threshold=100, classify=classify)
    names = sorted(p.name for p in rules_dir(store_dir).glob("*.md"))
    assert names == ["big-a.md", "big-b.md", "small.md"]
    assert all(count_rules(_text(p)) <= 100 for p in rules_dir(store_dir).glob("*.md"))


async def test_unsplittable_single_category_terminates(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    _seed(store_dir, 150)
    classify = _Scripted(lambda rules: dict.fromkeys(rules, "general"))
    written = await split_oversized_rules(store_dir, threshold=100, classify=classify)
    # One category for everything → cannot reduce; leaves the file, does not loop.
    assert written == 0
    assert classify.calls <= 2  # tried, gave up — no runaway recursion


async def test_merges_into_existing_category_file(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    # A pre-existing category file the split must merge into, not clobber.
    from coffer.infrastructure.memory.rules_files import write_rules_file

    write_rules_file(rule_file_path(store_dir, "alpha"), ["pre-existing alpha rule"])
    _seed(store_dir, 150)

    def split_two(rules: list[str]) -> dict[str, str]:
        return {r: ("alpha" if i < 120 else "beta") for i, r in enumerate(rules)}

    await split_oversized_rules(store_dir, threshold=100, classify=_Scripted(split_two))
    alpha = rule_bullets(_text(rule_file_path(store_dir, "alpha")))
    assert "pre-existing alpha rule" in alpha
    assert "rule 0" in alpha


async def test_run_rules_split_drives_llm_classify_recursively(tmp_path: pathlib.Path) -> None:
    store_dir = tmp_path / "store"
    _seed(store_dir, 150)
    llm = _Llm(
        _assign(150, lambda i: "alpha" if i < 120 else "beta"),  # rules.md → alpha(120)+beta(30)
        _assign(120, lambda i: "aa" if i < 60 else "ab"),  # oversized alpha → aa(60)+ab(60)
    )
    written = await run_rules_split(
        store_dir,
        llm=llm,
        model=_model(),
        credential_resolver=lambda ref: "",
        threshold=100,
    )
    assert written >= 3
    names = sorted(p.name for p in rules_dir(store_dir).glob("*.md"))
    assert names == ["aa.md", "ab.md", "beta.md"]
