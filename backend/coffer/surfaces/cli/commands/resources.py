"""``coffer resource`` and each kind's lifecycle verbs, over the kind-agnostic routes.

Spec resource-framework "Address every resource by an immutable uid through
one kind-agnostic surface". Every page switches, renames, reaches and deletes
its resources through ``/api/v1/resources/{uid}``; these commands are the same
calls, under ``coffer resource`` for any kind and under each kind's own group
(``coffer mcp enable github``) where a person looks for them. A resource is
named by its name or its uid.
"""

from __future__ import annotations

from coffer.surfaces.cli._route_command import Q, RouteCommand, mount

#: Group -> (resource kind, the page, the noun).
KINDS = {
    "mcp": ("mcp_server", "MCP servers", "server"),
    "channel": ("channel", "Channels", "channel"),
    "knowledge": ("knowledge", "Knowledge", "collection"),
    "memory": ("memory", "Memory", "partition"),
    "skill": ("skill", "Skills", "skill"),
}

SPECS: list[RouteCommand] = [
    RouteCommand(
        "resource list",
        "GET",
        "/resources",
        "every page · its list",
        "Resources of every kind, or of one.",
        query=(
            Q("kind", "mcp_server, agent, skill, knowledge, memory, provider, channel"),
            Q("name"),
        ),
        columns=("kind", "name", "enabled", "uid"),
    ),
    RouteCommand(
        "resource show", "GET", "/resources/{uid}", "every page · open one", "One resource by uid."
    ),
    RouteCommand(
        "resource add",
        "POST",
        "/resources",
        "every page · Add",
        "Register a resource. Body: kind, name, config, description.",
        body=True,
        pending=True,
    ),
    RouteCommand(
        "resource update",
        "PATCH",
        "/resources/{uid}",
        "every page · edit",
        "Change a resource. Body: name, description, config.",
        body=True,
        pending=True,
    ),
    RouteCommand(
        "resource delete",
        "DELETE",
        "/resources/{uid}",
        "every page · Delete",
        "Delete a resource (the kind's cleanup runs first).",
    ),
    RouteCommand(
        "resource enable",
        "POST",
        "/resources/{uid}/enable",
        "every page · switch on",
        "Switch a resource on.",
    ),
    RouteCommand(
        "resource disable",
        "POST",
        "/resources/{uid}/disable",
        "every page · switch off",
        "Switch a resource off.",
    ),
    RouteCommand(
        "resource reach show",
        "GET",
        "/resources/{uid}/scope",
        "every page · Reach",
        "Which agents a resource reaches.",
    ),
    RouteCommand(
        "resource reach set",
        "PUT",
        "/resources/{uid}/scope",
        "every page · set Reach",
        "Set the agents a resource reaches. Body: scope ({agents: [uid…]} or null for "
        "every agent).",
        body=True,
    ),
]

for group, (kind, page, noun) in KINDS.items():
    named = {"uid": kind}
    SPECS += [
        RouteCommand(
            f"{group} list",
            "GET",
            "/resources",
            f"{page} · list",
            f"Every {noun}.",
            fixed_query={"kind": kind},
            columns=("name", "enabled", "description", "uid"),
        ),
        RouteCommand(
            f"{group} show",
            "GET",
            "/resources/{uid}",
            f"{page} · open a {noun}",
            f"One {noun}: its config, reach and state.",
            names=named,
        ),
        RouteCommand(
            f"{group} update",
            "PATCH",
            "/resources/{uid}",
            f"{page} · edit a {noun}",
            f"Change a {noun}. Body: name, description, config.",
            names=named,
            body=True,
            pending=True,
        ),
    ]
    if kind != "skill":  # a skill's delete is its own route (``coffer skill delete``)
        SPECS.append(
            RouteCommand(
                f"{group} delete",
                "DELETE",
                "/resources/{uid}",
                f"{page} · Delete",
                f"Delete a {noun}.",
                names=named,
            )
        )
    if kind not in ("knowledge", "memory"):
        SPECS += [
            RouteCommand(
                f"{group} enable",
                "POST",
                "/resources/{uid}/enable",
                f"{page} · switch on",
                f"Switch a {noun} on.",
                names=named,
            ),
            RouteCommand(
                f"{group} disable",
                "POST",
                "/resources/{uid}/disable",
                f"{page} · switch off",
                f"Switch a {noun} off.",
                names=named,
            ),
            RouteCommand(
                f"{group} reach",
                "PUT",
                "/resources/{uid}/scope",
                f"{page} · Reach",
                f"Set the agents a {noun} reaches. Body: scope ({{agents: [uid…]}} or null).",
                names=named,
                body=True,
            ),
        ]
    if kind in ("channel",):
        SPECS.append(
            RouteCommand(
                f"{group} add",
                "POST",
                "/resources",
                f"{page} · Add",
                f"Add a {noun}. Body: name, description, config.",
                body=True,
                fixed_body={"kind": kind},
                pending=True,
            )
        )

# A skill's list and page are its own routes (``coffer skill list`` / ``show``).
SPECS = [s for s in SPECS if s.command not in ("skill list", "skill show")]

mount(SPECS)
