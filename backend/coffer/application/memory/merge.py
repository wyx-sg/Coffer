"""AI-assisted merge of same-project memory stores (spec 007, FR-056-059).

Two layers:

- ``scan()`` proposes same-project pairs: a deterministic tier (both roots
  locally readable and normalizing to the SAME origin remote) needs no LLM;
  every other pair is judged by Coffer's internal engine through the
  memory-local ``LlmCompletionPort`` (one one-shot completion per pair, strict
  JSON verdict, malformed → skip). No internal engine → ``engine="no_model"``
  and deterministic proposals only. The scan never mutates anything.
- ``merge()`` executes one confirmed pair through the existing additive
  consolidation machinery (``StoreConsolidator.merge`` — journal dedupe,
  collision suffixing, label/root carry-over, FR-058 aliases, reconcile,
  retire), records the audit entry, then optionally runs the FR-033 reorg
  pass on the survivor (FR-059) — merge success never depends on it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from itertools import combinations

from coffer.application.audit_service import AuditService
from coffer.application.memory.consolidate import MergeOutcome, StoreConsolidator
from coffer.application.memory.merge_prompt import (
    MERGE_JUDGE_SYSTEM,
    StoreEvidence,
    build_pair_prompt,
    parse_verdict,
)
from coffer.application.memory.organizer_ports import LlmCompletionPort, ModelSelectorPort
from coffer.application.memory.scope import GLOBAL_STORE_NAME, KIND_MEMORY, is_valid_store_name
from coffer.domain.errors import MemoryStoreMergeInvalid
from coffer.domain.resource import ResourceRef

_logger = logging.getLogger("coffer.memory.merge")

#: Upper bound on engine-judged pairs per scan (FR-056) — a runaway store list
#: must not turn one click into hundreds of LLM calls.
MAX_ENGINE_PAIRS = 50
#: Concurrent in-flight engine judgments within one scan.
ENGINE_CONCURRENCY = 4

#: Signature of the evidence gatherer: store name → evidence.
EvidenceFn = Callable[[str], Awaitable[StoreEvidence]]
#: Store names of every per-project memory store.
ListProjectStoresFn = Callable[[], Awaitable[list[str]]]
#: Whether a recorded project root is present on THIS machine.
RootExistsFn = Callable[[str], bool]
#: Runs the FR-033 reorg pass on a store, returning its status string.
ReorgFn = Callable[[str], Awaitable[str]]


@dataclass(frozen=True)
class MergeProposal:
    """One scan proposal: merge ``source`` away into ``target``."""

    source: str
    target: str
    confidence: str  # certain | high | medium | low
    judged_by: str  # remote | engine
    reason: str
    source_evidence: StoreEvidence
    target_evidence: StoreEvidence


@dataclass(frozen=True)
class MergeScanResult:
    engine: str  # ok | no_model
    truncated: bool
    proposals: list[MergeProposal]


@dataclass(frozen=True)
class MergeResult:
    outcome: MergeOutcome
    reorg_status: str


class StoreMergeService:
    """Scan for and execute same-project store merges (FR-056-059)."""

    def __init__(
        self,
        *,
        list_project_stores: ListProjectStoresFn,
        evidence: EvidenceFn,
        root_exists: RootExistsFn,
        llm: LlmCompletionPort,
        models: ModelSelectorPort,
        credential_resolver: Callable[[str], str],
        consolidator: StoreConsolidator,
        reorg: ReorgFn,
        audit: AuditService,
    ) -> None:
        self._list_project_stores = list_project_stores
        self._evidence = evidence
        self._root_exists = root_exists
        self._llm = llm
        self._models = models
        self._credential_resolver = credential_resolver
        self._consolidator = consolidator
        self._reorg = reorg
        self._audit = audit

    # ----- scan (FR-056) -----

    async def scan(self) -> MergeScanResult:
        names = sorted(await self._list_project_stores())
        gathered = await asyncio.gather(*(self._evidence(name) for name in names))
        evidence = dict(zip(names, gathered, strict=True))
        proposals: list[MergeProposal] = []
        engine_pairs: list[tuple[StoreEvidence, StoreEvidence]] = []
        for a, b in combinations(names, 2):
            ea, eb = evidence[a], evidence[b]
            if ea.remote and eb.remote and ea.remote == eb.remote:
                proposals.append(
                    self._proposal(
                        ea,
                        eb,
                        confidence="certain",
                        judged_by="remote",
                        reason=f"both roots point at the same origin remote ({ea.remote})",
                    )
                )
            else:
                engine_pairs.append((ea, eb))
        model = await self._models.get_default()
        if model is None:
            return MergeScanResult(engine="no_model", truncated=False, proposals=proposals)
        truncated = len(engine_pairs) > MAX_ENGINE_PAIRS
        # Judge pairs concurrently (bounded) — 50 sequential LLM round-trips
        # inside one HTTP request would take minutes. Order stays deterministic.
        sem = asyncio.Semaphore(ENGINE_CONCURRENCY)

        async def judge_bounded(ea: StoreEvidence, eb: StoreEvidence) -> str | None:
            async with sem:
                return await self._judge(ea, eb, model)

        capped = engine_pairs[:MAX_ENGINE_PAIRS]
        raw_verdicts = await asyncio.gather(*(judge_bounded(ea, eb) for ea, eb in capped))
        for (ea, eb), verdict_raw in zip(capped, raw_verdicts, strict=True):
            if verdict_raw is None:
                continue
            verdict = parse_verdict(verdict_raw)
            if verdict is None or not verdict.same_project:
                continue
            proposals.append(
                self._proposal(
                    ea,
                    eb,
                    confidence=verdict.confidence,
                    judged_by="engine",
                    reason=verdict.reason,
                )
            )
        return MergeScanResult(engine="ok", truncated=truncated, proposals=proposals)

    async def _judge(self, ea: StoreEvidence, eb: StoreEvidence, model: object) -> str | None:
        """One one-shot judgment; any transport/LLM error skips the pair."""
        try:
            return await self._llm.complete(
                system=MERGE_JUDGE_SYSTEM,
                user=build_pair_prompt(ea, eb),
                model=model,  # type: ignore[arg-type]
                credential_resolver=self._credential_resolver,
            )
        except Exception:
            _logger.exception("merge_scan.judge.failed a=%s b=%s", ea.store, eb.store)
            return None

    def _proposal(
        self,
        ea: StoreEvidence,
        eb: StoreEvidence,
        *,
        confidence: str,
        judged_by: str,
        reason: str,
    ) -> MergeProposal:
        """Suggested direction (FR-056): a locally-resolvable root survives,
        then the higher fact count, then the lexically smaller name."""
        a_live = bool(ea.root and self._root_exists(ea.root))
        b_live = bool(eb.root and self._root_exists(eb.root))
        if a_live != b_live:
            target, source = (ea, eb) if a_live else (eb, ea)
        elif ea.facts != eb.facts:
            target, source = (ea, eb) if ea.facts > eb.facts else (eb, ea)
        else:
            target, source = (ea, eb) if ea.store < eb.store else (eb, ea)
        return MergeProposal(
            source=source.store,
            target=target.store,
            confidence=confidence,
            judged_by=judged_by,
            reason=reason,
            source_evidence=source,
            target_evidence=target,
        )

    # ----- merge (FR-057/FR-059) -----

    async def merge(
        self, *, source: str, target: str, organize: bool = True, actor: str = "user"
    ) -> MergeResult:
        self._validate_pair(source, target)
        outcome = await self._consolidator.merge(source, target, actor=actor)
        await self._audit.record(
            "memory_stores_merged",
            ref=ResourceRef(KIND_MEMORY, target),
            actor=actor,
            details={
                "source": source,
                "target": target,
                "merged_files": outcome.merged_files,
                "label_moved": outcome.label_moved,
                "root_moved": outcome.root_moved,
                "aliases": len(outcome.aliases),
            },
        )
        reorg_status = "skipped"
        if organize:
            try:
                reorg_status = await self._reorg(target)
            except Exception as exc:  # FR-059: polish never fails the merge
                _logger.exception("merge.reorg.failed target=%s", target)
                reorg_status = f"error: {exc}"
        return MergeResult(outcome=outcome, reorg_status=reorg_status)

    @staticmethod
    def _validate_pair(source: str, target: str) -> None:
        for name in (source, target):
            if name == GLOBAL_STORE_NAME:
                raise MemoryStoreMergeInvalid("the global store is never mergeable")
            if not is_valid_store_name(name):
                raise MemoryStoreMergeInvalid(f"not a project store name: {name!r}")
        if source == target:
            raise MemoryStoreMergeInvalid("source and target are the same store")
