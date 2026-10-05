"""``coffer attention``, ``coffer usage`` and ``coffer proxy`` — Overview, Usage and the proxy.

Spec web-ui "Show what needs the user and each area's health on Overview",
provider-switching's usage and proxy requirements. The audit, MCP and daemon logs are
``coffer log``.
"""

from __future__ import annotations

from coffer.surfaces.cli._route_command import Q, RouteCommand, mount

SPECS = [
    RouteCommand(
        "attention list",
        "GET",
        "/attention",
        "Overview · needs you",
        "What needs you, each with its fix or its hand-off prompt.",
    ),
    RouteCommand(
        "attention ignore",
        "PUT",
        "/attention/ignored/{key}",
        "Overview · Ignore",
        "Stop listing an informational item.",
    ),
    RouteCommand(
        "attention unignore",
        "DELETE",
        "/attention/ignored/{key}",
        "Overview · ignored · Show again",
        "List an ignored item again.",
    ),
    RouteCommand(
        "usage summary",
        "GET",
        "/usage/summary",
        "Usage",
        "Model usage and cost over a range, grouped.",
        query=(
            Q("range", "24h, 7d, 30d…"),
            Q("from"),
            Q("to"),
            Q("group_by", "model, agent, connection, day"),
            Q("agent_type"),
            Q("connection_uid"),
        ),
    ),
    RouteCommand(
        "proxy status",
        "GET",
        "/proxy/status",
        "Model providers · local proxy",
        "The local model proxy's state.",
    ),
    RouteCommand(
        "proxy hint",
        "GET",
        "/proxy/tokens/{agent_uid}/hint",
        "Agents · proxy key",
        "The tail of an agent's proxy key.",
    ),
    RouteCommand(
        "proxy rotate",
        "POST",
        "/proxy/tokens/{agent_uid}/rotate",
        "Agents · Rotate proxy key",
        "Mint a new proxy key for an agent.",
    ),
]

mount(SPECS)
