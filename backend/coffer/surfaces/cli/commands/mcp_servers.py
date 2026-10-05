"""``coffer mcp`` — the MCP servers page and a server's tabs.

Spec mcp-gateway "Manage MCP servers as resources". A server is named by its
name or uid. Registering and changing one goes through the kind-agnostic
resource routes the page uses, so the kind's validation, the secret probe,
audit and the approval of a new secret destination come with it.
"""

from __future__ import annotations

from coffer.surfaces.cli._route_command import Q, RouteCommand, mount

M = {"uid": "mcp_server"}
_UI = "MCP servers · "
_S = "/resources/mcp_server/{uid}"

SPECS = [
    RouteCommand(
        "mcp add",
        "POST",
        "/resources",
        _UI + "Add server",
        "Register a server. Body: kind=mcp_server, name, description, config.transport "
        "(stdio: command, args, env, secret_refs, cwd; http: url, headers, secret_refs, "
        "auth_schemes).",
        body=True,
        pending=True,
    ),
    RouteCommand(
        "mcp test-config",
        "POST",
        "/resources/mcp_server/test-config",
        _UI + "Add server · Test",
        "Test a config before adding it; nothing is saved. Body: transport, "
        "secret_values, spawn_timeout_seconds, request_timeout_seconds.",
        body=True,
    ),
    RouteCommand(
        "mcp status",
        "GET",
        _S + "/status",
        _UI + "a server's state",
        "Why a server is in its state, and what to do.",
        names=M,
    ),
    RouteCommand(
        "mcp tools",
        "GET",
        _S + "/capabilities",
        _UI + "Tools tab",
        "The server's tools, resources and prompts with their switches.",
        names=M,
        query=(Q("saved", "Read the saved list without connecting", flag=True),),
    ),
    RouteCommand(
        "mcp tiering",
        "GET",
        _S + "/tiering",
        _UI + "Tools tab · listed and unlisted",
        "Which tools agents see listed and which they find by search.",
        names=M,
    ),
    RouteCommand(
        "mcp exposure",
        "PATCH",
        _S + "/tools/{tool}/exposure",
        _UI + "Tools tab · how a tool is exposed",
        "Choose how one tool is exposed. Body: mode (auto | always | search).",
        names=M,
        body=True,
    ),
    RouteCommand(
        "mcp exposure-all",
        "PATCH",
        _S + "/tools/exposure",
        _UI + "Tools tab · expose several",
        "Choose how several tools are exposed. Body: tools, mode.",
        names=M,
        body=True,
    ),
    RouteCommand(
        "mcp tool enable",
        "POST",
        _S + "/capabilities/{capability_type}/enable",
        _UI + "Tools tab · switch on",
        "Switch capabilities on. Body: capability_key (a list of keys).",
        names=M,
        body=True,
        args={"capability_type": "tool, prompt or resource"},
    ),
    RouteCommand(
        "mcp tool disable",
        "POST",
        _S + "/capabilities/{capability_type}/disable",
        _UI + "Tools tab · switch off",
        "Switch capabilities off. Body: capability_key (a list of keys).",
        names=M,
        body=True,
        args={"capability_type": "tool, prompt or resource"},
    ),
    RouteCommand(
        "mcp calls",
        "GET",
        _S + "/invocations/summary",
        _UI + "Overview · calls",
        "One server's calls and errors since a moment, per agent and per tool.",
        names=M,
        query=(Q("since", "ISO time; 24 hours ago by default"),),
    ),
    RouteCommand(
        "mcp server-log",
        "GET",
        _S + "/log",
        _UI + "Log tab",
        "The newest lines of the server's own log.",
        names=M,
        query=(Q("limit", kind=int),),
    ),
    RouteCommand(
        "mcp builtin",
        "GET",
        "/mcp/builtin",
        _UI + "the built-in coffer server",
        "Coffer's own built-in tools.",
    ),
]

mount(SPECS)
