"""The join report an ``awaiting_join`` round carries, as the history stores
it (spec vault-sync "Report a join before applying it").

Split out of ``sync_remote_repo.py`` for the file-size tier.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from coffer.domain.sync.convergence import JoinKind, JoinPreview


def _opt(value: Any) -> str | None:
    return str(value) if value else None


def report_to_json(report: JoinPreview) -> dict[str, Any]:
    return {
        "joining": report.joining,
        "kind": report.kind.value if report.kind else None,
        "ambiguous": report.ambiguous,
        "base": report.base,
        "last_converged_on": (
            report.last_converged_on.isoformat() if report.last_converged_on else None
        ),
        "remote_changed": report.remote_changed,
        "vault_documents": report.vault_documents,
    }


def report_from_json(raw: Any) -> JoinPreview | None:
    if not isinstance(raw, dict):
        return None
    try:
        day = raw.get("last_converged_on")
        changed = raw.get("remote_changed")
        documents = raw.get("vault_documents")
        return JoinPreview(
            joining=bool(raw.get("joining", True)),
            kind=JoinKind(raw["kind"]) if raw.get("kind") else None,
            ambiguous=bool(raw.get("ambiguous", False)),
            base=_opt(raw.get("base")),
            last_converged_on=date.fromisoformat(day) if day else None,
            remote_changed=int(changed) if changed is not None else None,
            vault_documents=int(documents) if documents is not None else None,
        )
    except (ValueError, TypeError):
        return None
