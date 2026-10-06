"""The target's REST surface a suite creates and removes its ``qa-`` objects through.

Every create goes through the journal, so whatever a case makes is deleted at
the end of the run even when the case fails halfway.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from e2e.installed._common.http import DaemonClient, Reply
from e2e.installed._common.journal import ResourceJournal

MCP_SERVER = "mcp_server"
SECRET = "secret"


class CofferApi:
    def __init__(self, client: DaemonClient, journal: ResourceJournal) -> None:
        self.client = client
        self.journal = journal

    # --- existence (for the journal's reservation) --------------------------------

    async def exists(self, kind: str, name: str) -> bool:
        if kind == MCP_SERVER:
            return bool(await self._servers_named(name))
        if kind == SECRET:
            return any(row.get("label") == name for row in await self.secrets())
        raise ValueError(f"unknown kind {kind}")

    async def _servers_named(self, name: str) -> list[dict[str, Any]]:
        reply = await self.client.request("GET", f"/api/v1/resources?kind={MCP_SERVER}")
        if reply.status != 200:
            raise RuntimeError(f"cannot list MCP servers: HTTP {reply.status}")
        return [r for r in reply.json.get("resources", []) if r.get("name") == name]

    async def secrets(self) -> list[dict[str, Any]]:
        reply = await self.client.request("GET", "/api/v1/secrets")
        if reply.status != 200:
            raise RuntimeError(f"cannot list secrets: HTTP {reply.status}")
        return list(reply.json.get("refs", []))

    async def qa_leftovers(self) -> dict[str, list[str]]:
        """Every ``qa-`` MCP server and secret label still on the target."""
        reply = await self.client.request("GET", f"/api/v1/resources?kind={MCP_SERVER}")
        servers = [
            r["name"]
            for r in reply.json.get("resources", [])
            if r.get("name", "").startswith("qa-")
        ]
        labels = [
            s["label"] for s in await self.secrets() if (s.get("label") or "").startswith("qa-")
        ]
        return {"mcp_servers": servers, "secrets": labels}

    # --- creation ---------------------------------------------------------------

    def _delete_resource(self, uid: str) -> Any:
        async def delete() -> int:
            reply = await self.client.request("DELETE", f"/api/v1/resources/{uid}", timeout=60)
            return reply.status

        return delete

    async def register_server(self, name: str, transport: dict[str, Any], **config: Any) -> Reply:
        """``POST /api/v1/resources`` for an MCP server; journaled when created."""
        self.journal.check_name(name)
        body = {"kind": MCP_SERVER, "name": name, "config": {"transport": transport, **config}}
        reply = await self.client.request("POST", "/api/v1/resources", body)
        if reply.status == 201:
            uid = reply.json["uid"]
            self.journal.created(MCP_SERVER, name, uid, self._delete_resource(uid))
        return reply

    async def create_group(self, body: dict[str, Any]) -> Reply:
        """``POST /api/v1/custom-tools``; a group is an MCP server resource."""
        self.journal.check_name(body["name"])
        reply = await self.client.request("POST", "/api/v1/custom-tools", body)
        if reply.status == 201:
            uid = reply.json["uid"]
            self.journal.created(MCP_SERVER, body["name"], uid, self._delete_resource(uid))
        return reply

    async def create_secret(self, label: str, value: str, description: str) -> Reply:
        """A standalone secret holding a fake value; its minted ref is journaled."""
        self.journal.check_name(label)
        body = {"label": label, "value": value, "description": description}
        reply = await self.client.request("POST", "/api/v1/secrets", body)
        if reply.status == 201:
            ref = reply.json["ref"]

            async def delete() -> int:
                path = f"/api/v1/secrets/{quote(ref, safe='/')}"
                return (await self.client.request("DELETE", path)).status

            self.journal.created(SECRET, label, ref, delete)
        return reply

    async def delete_resource(self, uid: str) -> Reply:
        """A case deleting its own server mid-run (the journal records it)."""
        reply = await self.client.request("DELETE", f"/api/v1/resources/{uid}", timeout=60)
        self.journal.deleted(uid, reply.status)
        return reply
