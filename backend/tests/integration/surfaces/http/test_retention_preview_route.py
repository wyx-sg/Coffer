"""GET /api/v1/retention/policies/{table}/preview — what a shorter window would delete."""

from datetime import UTC, datetime, timedelta

import pytest

from coffer.infrastructure.persistence.engine import session_maker
from coffer.infrastructure.persistence.models import AuditLogModel

from .test_retention_routes import _client


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a shorter period is previewed before it is saved"
)
@pytest.mark.asyncio
async def test_preview_counts_what_a_shorter_window_would_delete(tmp_path):
    """The shortening confirmation's numbers: every row and the rows it would delete."""
    c, engine = await _client(tmp_path)
    now = datetime.now(tz=UTC)
    async with session_maker(engine)() as s:
        for age in (1, 3, 10, 40):
            s.add(
                AuditLogModel(
                    timestamp=now - timedelta(days=age),
                    event_type="resource_created",
                    resource_kind="mcp_server",
                    resource_name=f"r{age}",
                    actor="cli",
                    details_json=None,
                )
            )
        await s.commit()
    async with c:
        url = "/api/v1/retention/policies/audit_log/preview"
        r = await c.get(url, params={"days": 7})
        assert r.status_code == 200
        assert r.json() == {
            "table_name": "audit_log",
            "days": 7,
            "total_rows": 4,
            "rows_to_delete": 2,
        }
        # Counting deletes nothing, and a window outside 1..3650 is refused.
        assert (await c.get(url, params={"days": 7})).json()["total_rows"] == 4
        assert (await c.get(url, params={"days": 0})).status_code == 422
        unknown = await c.get("/api/v1/retention/policies/nope/preview", params={"days": 7})
        assert unknown.status_code >= 400
    await engine.dispose()
