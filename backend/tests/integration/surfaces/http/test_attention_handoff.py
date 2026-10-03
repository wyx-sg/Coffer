"""An attention item's hand-off on the wire: every item carries a prompt, the
item's own when it has one (spec resource-framework "Report what needs a person
across every kind")."""

from __future__ import annotations

import pytest

from coffer.application.attention import (
    AttentionAction,
    AttentionItem,
    AttentionReport,
    Severity,
)
from coffer.surfaces.http.reconcile_schemas import attention_out

PROMPT = "Please install `uvx` on this machine.\n\n- Needed by the MCP server fetch."


def _item(uid: str, handoff: str | None) -> AttentionItem:
    return AttentionItem(
        kind="mcp_server",
        uid=uid,
        title=uid,
        reason_code="mcp_missing_launcher",
        reason="Its launcher uvx isn't found on this machine.",
        severity=Severity.ERROR,
        action=AttentionAction("test", "POST", f"/api/v1/resources/mcp_server/{uid}/test"),
        handoff=handoff,
    )


@pytest.mark.acceptance(spec="resource-framework", scenario="every item carries a hand-off prompt")
def test_every_item_carries_a_hand_off_prompt() -> None:
    report = AttentionReport(
        items=(_item("fetch", PROMPT), _item("plain", None)), counts_by_kind={"mcp_server": 2}
    )
    fetch, plain = attention_out(report).model_dump(mode="json")["items"]
    assert fetch["handoff"] == {"prompt": PROMPT}
    assert plain["handoff"]["prompt"] and plain["handoff"]["prompt"] != PROMPT
