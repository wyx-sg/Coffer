"""Assemble the SessionStart rules bundle injected into a managed agent (Slice 6).

On SessionStart, Coffer's hook asks the daemon for the *additional context* to
inject: the project's + global rules (from the memory stores), plus two seeded
built-in rules that teach the agent to use Coffer's shared memory tools. The
bundle is runtime-only — nothing is written to the agent's native files.

Collaborators are injected as plain callables so this module imports nothing
from the agent kind (Contract 5: ``application/memory`` must not depend on
``application/agent``). The session-context HTTP route constructs the assembler
from the memory service + scope resolver via DI.

FR-049 (rules injection) + FR-050 (seeded built-in rules).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from coffer.domain.memory.scope import ResolvedScope

_logger = logging.getLogger(__name__)

#: SessionStart bundles are capped by the external hook contract (≤10k chars).
_MAX_BUNDLE_CHARS = 10_000

#: FR-050 seeded built-in rules — always appended so a fresh project still gets
#: Coffer's memory affordances even with no user rules recorded yet.
SEEDED_RESUME_RULE = (
    'When the user asks to continue prior work ("continue", "where were we", '
    '"resume"), call `coffer__resume()` to pull the saved working-state handoff '
    "for this project + branch before starting."
)
SEEDED_SOFTSTEER_RULE = (
    "Prefer `coffer__remember` to record durable facts and `coffer__recall` to "
    "retrieve them; Coffer is the shared memory store across your agents — don't "
    "rely on the agent's own native memory."
)

_ResolveScopesFn = Callable[[str | None], Awaitable[list[ResolvedScope]]]
_GetRulesFn = Callable[[str], Awaitable[str | None]]
_StoreNameFn = Callable[[ResolvedScope], str]


class RulesBundleAssembler:
    """Builds the SessionStart additional-context markdown for an agent's cwd."""

    def __init__(
        self,
        *,
        resolve_recall_scopes: _ResolveScopesFn,
        get_rules: _GetRulesFn,
        store_name_for: _StoreNameFn,
    ) -> None:
        self._resolve_recall_scopes = resolve_recall_scopes
        self._get_rules = get_rules
        self._store_name_for = store_name_for

    async def assemble_session_context(self, *, cwd: str | None) -> str:
        """Return the markdown bundle: project rules, global rules, seeded rules.

        Never raises: any failure (scope unresolved, store read error) degrades to
        whatever rules resolved so far plus the seeded rules — the hook must never
        block the agent's session.
        """
        project_rules: str | None = None
        global_rules: str | None = None
        try:
            scopes = await self._resolve_recall_scopes(cwd)
        except Exception:
            _logger.debug("rules_bundle.resolve_scopes.failed", exc_info=True)
            scopes = []

        for scope in scopes:
            try:
                rules = await self._get_rules(self._store_name_for(scope))
            except Exception:
                _logger.debug("rules_bundle.get_rules.failed", exc_info=True)
                continue
            if rules is None or not rules.strip():
                continue
            if scope.is_global:
                global_rules = rules.strip()
            else:
                project_rules = rules.strip()

        return self._render(project_rules, global_rules)

    @staticmethod
    def _render(project_rules: str | None, global_rules: str | None) -> str:
        parts: list[str] = ["# Project rules (via Coffer)"]
        if project_rules:
            parts.append("## Project\n\n" + project_rules)
        if global_rules:
            parts.append("## Global\n\n" + global_rules)
        # User rules are truncated FIRST so the seeded rules are never lost.
        body = "\n\n".join(parts)
        seeded = "## Coffer built-in\n\n- " + SEEDED_RESUME_RULE + "\n- " + SEEDED_SOFTSTEER_RULE
        budget = _MAX_BUNDLE_CHARS - len(seeded) - 2  # 2 for the joining "\n\n"
        if len(body) > budget:
            body = body[: max(0, budget)]
        return body + "\n\n" + seeded
