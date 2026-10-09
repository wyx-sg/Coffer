"""Commands that predate the registry, recorded with the routes they call.

Spec resource-framework "Offer every management operation on the command
line": the registry must name every command that stands for a UI operation,
including the ones written before it existed.
"""

from __future__ import annotations

from coffer.surfaces.cli.registry import record

record("cli list", "GET", "/clis", "CLIs · list")
record("daemon status", "GET", "/daemon/status", "Settings · Daemon · status")
record("daemon status", "GET", "/upkeep/runs", "Settings · Daemon · passes in flight")
record("log audit", "GET", "/audit", "Activity · Audit")
record("log mcp", "GET", "/mcp/invocations", "Activity · MCP calls")
record("log call", "GET", "/mcp/invocations/{invocation_id}", "Activity · tool call drawer")
record("log mcp", "GET", "/resources/mcp_server/{uid}/invocations", "MCP servers · Calls tab")
record("log daemon", "GET", "/daemon/logs", "Activity · Daemon log")
record("mcp test", "POST", "/resources/mcp_server/{uid}/test", "MCP servers · Test")
record("mcp test", "POST", "/resources/mcp_server/{uid}/refresh", "MCP servers · Refresh tools")
record("secret list", "GET", "/secrets", "Secrets · list")
record("secret set", "POST", "/secrets", "Secrets · Add / Replace value")
record("vault problems", "GET", "/vault/problems", "no page: hand edits the vault refused")
