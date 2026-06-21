"""TranscriptDistillationService — orchestrates reader, LLM, and insight sink."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from coffer.application.distill.ports import (
    AgentResolverPort,
    InsightSinkPort,
    LlmCompletionPort,
    ModelSelectorPort,
    TranscriptReaderPort,
)
from coffer.application.distill.prompt import build_prompt, parse_insights
from coffer.domain.distill.session import DistilledInsight, TranscriptSession


class NoModelConfiguredError(Exception):
    """Raised when no model is available to run distillation."""


@dataclass
class DistillResult:
    """Result of a single distillation run."""

    insights: list[DistilledInsight] = field(default_factory=list)
    journal_entries: list[str] = field(
        default_factory=list
    )  # journal-entry markers (empty on dry_run)


class TranscriptDistillationService:
    """Orchestrates transcript distillation: read → LLM → sink."""

    def __init__(
        self,
        *,
        reader: TranscriptReaderPort,
        llm: LlmCompletionPort,
        sink: InsightSinkPort,
        agents: AgentResolverPort,
        models: ModelSelectorPort,
        credential_resolver: Callable[[str], str],
    ) -> None:
        self._reader = reader
        self._llm = llm
        self._sink = sink
        self._agents = agents
        self._models = models
        self._credential_resolver = credential_resolver

    async def list_sessions(
        self,
        agent_name: str,
        *,
        limit: int = 100,
        offset: int = 0,
        query: str | None = None,
        project: str | None = None,
        started_after: datetime | None = None,
        started_before: datetime | None = None,
        sort: str = "last_activity_at",
        order: str = "desc",
    ) -> tuple[int, list[TranscriptSession]]:
        """Return ``(matched_total, page)`` of transcript sessions for
        *agent_name* after search + filter + sort. Backed by the reader's
        mtime-aware cache, so listing an agent with thousands of past sessions
        stays responsive."""
        agent_type_value, config_dir = await self._agents.resolve(agent_name)
        return self._reader.search_session_summaries(
            agent_type_value=agent_type_value,
            config_dir=config_dir,
            limit=limit,
            offset=offset,
            query=query,
            project=project,
            started_after=started_after,
            started_before=started_before,
            sort=sort,
            order=order,
        )

    async def distill(
        self,
        *,
        agent_name: str,
        session_id: str | None = None,
        project_path: str | None = None,
        dry_run: bool = False,
    ) -> DistillResult:
        """Distil a single transcript session into the journal lane.

        Session selection:
        - If *session_id* given: read that session directly.
        - Else if *project_path* given: pick the most-recent session for that path.
        - Else: raise ValueError (caller must supply one of the two).
        """
        agent_type_value, config_dir = await self._agents.resolve(agent_name)

        session = self._select_session(
            agent_type_value=agent_type_value,
            config_dir=config_dir,
            session_id=session_id,
            project_path=project_path,
        )

        # Resolve Coffer's internal-engine connection (the internal_default one).
        model = await self._models.get_default()
        if model is None:
            raise NoModelConfiguredError(
                "No internal connection configured. Set an LLM connection as the "
                "Coffer internal engine in Settings before distilling."
            )

        # Build prompt and call LLM
        system, user = build_prompt(session)
        raw = await self._llm.complete(
            system=system,
            user=user,
            model=model,
            credential_resolver=self._credential_resolver,
        )

        insights = parse_insights(raw)

        written: list[str] = []
        if not dry_run:
            for insight in insights:
                marker = await self._sink.record(
                    project_path=session.project_path,
                    insight=insight,
                    origin_session_id=session.session_id,
                )
                if marker is not None:
                    written.append(marker)

        return DistillResult(insights=insights, journal_entries=written)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _select_session(
        self,
        *,
        agent_type_value: str,
        config_dir: str,
        session_id: str | None,
        project_path: str | None,
    ) -> TranscriptSession:
        if session_id is not None:
            return self._reader.read_session(
                agent_type_value=agent_type_value,
                config_dir=config_dir,
                session_id=session_id,
            )

        if project_path is not None:
            all_sessions = self._reader.list_sessions(
                agent_type_value=agent_type_value, config_dir=config_dir
            )
            matching = [s for s in all_sessions if s.project_path == project_path]
            if not matching:
                raise KeyError(f"No transcript sessions found for project_path={project_path!r}")
            # Most-recent: prefer sessions with started_at, else last-listed
            with_ts = [s for s in matching if s.started_at is not None]
            if with_ts:
                return max(with_ts, key=lambda s: s.started_at)  # type: ignore[arg-type, return-value]
            return matching[-1]

        raise ValueError("Either session_id or project_path must be provided.")
