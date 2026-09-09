"""Unit: StoreMergeService scan tiers, direction heuristic, pair validation.

Pure logic with fake ports — the real merge machinery (consolidator, repos,
LLM adapter) is covered in integration.
"""

from __future__ import annotations

import json

import pytest

from coffer.application.memory.merge import MAX_ENGINE_PAIRS, StoreMergeService
from coffer.application.memory.merge_prompt import StoreEvidence
from coffer.domain.errors import MemoryStoreMergeInvalid

_A = "project-" + "A" * 26
_B = "project-" + "B" * 26
_C = "project-" + "C" * 26


def _evidence(store: str, **over: object) -> StoreEvidence:
    base: dict = {
        "store": store,
        "label": None,
        "root": None,
        "remote": None,
        "facts": 0,
        "fact_titles": [],
        "topic_slugs": [],
    }
    base.update(over)
    return StoreEvidence(**base)


class _FakeModels:
    def __init__(self, model: object | None) -> None:
        self._model = model

    async def get_default(self) -> object | None:
        return self._model


class _FakeLlm:
    """Returns a canned verdict per (a, b) store-name pair; records calls."""

    def __init__(self, verdicts: dict[tuple[str, str], str] | None = None) -> None:
        self.verdicts = verdicts or {}
        self.calls: list[str] = []

    async def complete(self, *, system: str, user: str, model, credential_resolver) -> str:
        payload = json.loads(user.split("\n\n", 1)[1])
        key = (payload["store_a"]["store"], payload["store_b"]["store"])
        self.calls.append(key)
        if key in self.verdicts:
            return self.verdicts[key]
        return '{"same_project": false, "confidence": "low", "reason": "different"}'


def _service(
    evidence: dict[str, StoreEvidence],
    *,
    llm: _FakeLlm | None = None,
    model: object | None = object(),
    root_exists=lambda p: False,
) -> StoreMergeService:
    async def list_stores() -> list[str]:
        return list(evidence)

    async def get_evidence(name: str) -> StoreEvidence:
        return evidence[name]

    async def reorg(name: str) -> str:
        return "ok"

    return StoreMergeService(
        list_project_stores=list_stores,
        evidence=get_evidence,
        root_exists=root_exists,
        llm=llm or _FakeLlm(),
        models=_FakeModels(model),
        credential_resolver=lambda ref: "",
        consolidator=None,  # type: ignore[arg-type] — scan never touches it
        reorg=reorg,
        audit=None,  # type: ignore[arg-type] — scan never audits
    )


# ----- deterministic tier -----


async def test_same_remote_pair_is_certain_and_skips_the_engine():
    llm = _FakeLlm()
    svc = _service(
        {
            _A: _evidence(_A, remote="github.com/u/repo", root="/a", facts=5),
            _B: _evidence(_B, remote="github.com/u/repo", root="/b", facts=1),
        },
        llm=llm,
    )
    result = await svc.scan()
    assert result.engine == "ok"
    assert [p.judged_by for p in result.proposals] == ["remote"]
    assert result.proposals[0].confidence == "certain"
    assert llm.calls == []  # provable pair never consulted the engine


async def test_missing_or_differing_remotes_go_to_the_engine():
    llm = _FakeLlm()
    svc = _service(
        {
            _A: _evidence(_A, remote="github.com/u/repo"),
            _B: _evidence(_B, remote=None),
        },
        llm=llm,
    )
    result = await svc.scan()
    assert result.proposals == []  # fake LLM says different
    assert len(llm.calls) == 1


# ----- engine tier -----


async def test_engine_verdict_same_project_becomes_a_proposal():
    llm = _FakeLlm(
        {
            (_A, _B): '{"same_project": true, "confidence": "medium", "reason": "same title set"}',
        }
    )
    svc = _service({_A: _evidence(_A, facts=2), _B: _evidence(_B, facts=7)}, llm=llm)
    result = await svc.scan()
    assert len(result.proposals) == 1
    p = result.proposals[0]
    assert (p.judged_by, p.confidence, p.reason) == ("engine", "medium", "same title set")


async def test_malformed_engine_response_skips_the_pair():
    llm = _FakeLlm({(_A, _B): "definitely the same project!"})
    svc = _service({_A: _evidence(_A), _B: _evidence(_B)}, llm=llm)
    result = await svc.scan()
    assert result.proposals == []
    assert result.engine == "ok"  # a bad response is a skip, not an error


async def test_engine_transport_error_skips_the_pair():
    class _Boom(_FakeLlm):
        async def complete(self, **kw) -> str:
            raise RuntimeError("llm down")

    svc = _service({_A: _evidence(_A), _B: _evidence(_B)}, llm=_Boom())
    result = await svc.scan()
    assert result.proposals == [] and result.engine == "ok"


async def test_engine_tier_is_capped_and_flagged_truncated():
    stores = {
        f"project-{i:026d}": _evidence(f"project-{i:026d}") for i in range(12)
    }  # 66 pairs > 50
    llm = _FakeLlm()
    svc = _service(stores, llm=llm)
    result = await svc.scan()
    assert result.truncated is True
    assert len(llm.calls) == MAX_ENGINE_PAIRS


@pytest.mark.acceptance(spec="007-memory", scenario="merge scan proposes same-project stores")
async def test_scan_proposes_provable_and_engine_judged_pairs_without_mutating():
    """One scan, both tiers: the provable pair is certain/remote (no engine
    call), the plausible pair carries the engine verdict, directions follow
    the heuristic — and nothing is mutated (consolidator/audit are None, so
    any write would crash)."""
    llm = _FakeLlm(
        {
            (_A, _C): '{"same_project": true, "confidence": "high", "reason": "same fact titles"}',
            (_B, _C): '{"same_project": false, "confidence": "low", "reason": "unrelated"}',
        }
    )
    svc = _service(
        {
            _A: _evidence(_A, remote="github.com/u/repo", root="/a", facts=4),
            _B: _evidence(_B, remote="github.com/u/repo", root="/b", facts=9),
            _C: _evidence(_C, facts=1),
        },
        llm=llm,
    )
    result = await svc.scan()
    assert result.engine == "ok" and result.truncated is False
    by_kind = {p.judged_by: p for p in result.proposals}
    assert set(by_kind) == {"remote", "engine"}
    assert by_kind["remote"].confidence == "certain"
    assert (by_kind["remote"].target, by_kind["remote"].source) == (_B, _A)  # more facts
    assert by_kind["engine"].reason == "same fact titles"
    assert (by_kind["engine"].target, by_kind["engine"].source) == (_A, _C)  # more facts
    assert (_A, _B) not in llm.calls  # the provable pair skipped the engine


@pytest.mark.acceptance(
    spec="007-memory", scenario="merge scan degrades cleanly without an internal engine"
)
async def test_no_model_scan_is_the_acceptance_degradation():
    llm = _FakeLlm()
    svc = _service(
        {
            _A: _evidence(_A, remote="github.com/u/repo"),
            _B: _evidence(_B, remote="github.com/u/repo"),
            _C: _evidence(_C),
        },
        llm=llm,
        model=None,
    )
    result = await svc.scan()
    assert result.engine == "no_model"
    assert [p.judged_by for p in result.proposals] == ["remote"]
    assert llm.calls == []


# ----- direction heuristic -----


async def test_direction_prefers_locally_resolvable_root():
    svc = _service(
        {
            _A: _evidence(_A, remote="r", root="/gone", facts=100),
            _B: _evidence(_B, remote="r", root="/alive", facts=1),
        },
        root_exists=lambda p: p == "/alive",
    )
    p = (await svc.scan()).proposals[0]
    assert (p.target, p.source) == (_B, _A)  # live root wins over fact count


async def test_direction_falls_back_to_fact_count_then_name():
    svc = _service(
        {
            _A: _evidence(_A, remote="r", facts=1),
            _B: _evidence(_B, remote="r", facts=9),
        }
    )
    p = (await svc.scan()).proposals[0]
    assert (p.target, p.source) == (_B, _A)  # more facts wins

    svc = _service({_A: _evidence(_A, remote="r"), _B: _evidence(_B, remote="r")})
    p = (await svc.scan()).proposals[0]
    assert (p.target, p.source) == (_A, _B)  # tie → lexically smaller name


# ----- merge validation -----


@pytest.mark.parametrize(
    ("source", "target", "hint"),
    [
        ("global", _A, "global"),
        (_A, "global", "global"),
        (_A, _A, "same store"),
        ("not-a-store", _A, "not a project store"),
        (_A, "project-short", "not a project store"),
    ],
)
async def test_merge_rejects_invalid_pairs_before_any_side_effect(source, target, hint):
    svc = _service({})
    with pytest.raises(MemoryStoreMergeInvalid) as exc:
        await svc.merge(source=source, target=target)
    assert hint.split()[0] in str(exc.value)
