"""Choosing a pass's candidate documents: the terms asked about and the cap.

Spec knowledge "Assemble a pass from a bounded context": at most five existing
documents reach a pass in full, chosen by literal matching.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from coffer.application.knowledge import candidates
from coffer.application.knowledge.candidates import DEFAULT_CANDIDATE_LIMIT, MAX_TERMS


def test_identifiers_come_before_the_generic_tail() -> None:
    text = "Notes on `account.session` and SESSION_TTL, under the Login Flow heading."
    terms = candidates.distinctive_terms(text, title="Gateway")

    assert terms[0] == "account.session"
    assert "SESSION_TTL" in terms
    assert "Gateway" in terms
    # Stopwords and short words never become a term.
    assert "the" not in {t.lower() for t in terms}
    assert "under" not in {t.lower() for t in terms}


def test_terms_are_capped_and_deduplicated() -> None:
    text = " ".join(f"`ident_{n}.x`" for n in range(MAX_TERMS + 10)) + " `ident_0.x`"
    terms = candidates.distinctive_terms(text)

    assert len(terms) == MAX_TERMS
    assert len({t.lower() for t in terms}) == len(terms)


def test_cjk_runs_are_terms() -> None:
    assert candidates.distinctive_terms("会话的登录状态由 网关持有") == (
        "会话的登录状态由",
        "网关持有",
    )


class _Service:
    def __init__(self, paths: list[str]) -> None:
        self._paths = paths

    async def match_documents(self, _pattern: str, *, collection: str) -> Any:
        return SimpleNamespace(matches=[SimpleNamespace(path=p) for p in self._paths])


@pytest.mark.anyio
async def test_at_most_five_candidates_best_first_and_the_readme_is_never_one() -> None:
    # `shopee/d0.md` matches six times, `d1` five, ... so ranking by hits decides.
    matched = ["shopee/README.md"]
    for n in range(7):
        matched += [f"shopee/d{n}.md"] * (7 - n)
    source = SimpleNamespace(path="shopee/.inbox/x.md", body="`account.session` fact", title="T")

    chosen = await candidates.select(_Service(matched), "shopee", source)  # type: ignore[arg-type]

    assert len(chosen) == DEFAULT_CANDIDATE_LIMIT == 5
    assert chosen == tuple(f"shopee/d{n}.md" for n in range(5))


@pytest.mark.anyio
async def test_a_nested_readme_is_a_document_and_the_edited_document_is_not_its_own_candidate() -> (
    None
):
    source = SimpleNamespace(path="shopee/self.md", body="`account.session` fact", title="T")
    matched = ["shopee/self.md", "shopee/sub/README.md", "shopee/README.md"]

    chosen = await candidates.select(_Service(matched), "shopee", source)  # type: ignore[arg-type]

    assert chosen == ("shopee/sub/README.md",)
