"""``coffer settings`` — the Settings modal, tab by tab.

Spec web-ui "Open Settings as a modal from the sidebar footer" and the specs
owning each setting. Turning approvals OFF is itself an approval (``coffer
approval approve``); turning them on needs nobody.
"""

from __future__ import annotations

from coffer.surfaces.cli._route_command import Q, RouteCommand, mount

_UI = "Settings · "

SPECS = [
    RouteCommand(
        "settings approvals show",
        "GET",
        "/settings/secret-boundary",
        _UI + "Secrets · approvals",
        "Whether a new secret destination waits for approval.",
    ),
    RouteCommand(
        "settings approvals set",
        "PUT",
        "/settings/secret-boundary",
        _UI + "Secrets · approvals",
        "Switch approvals. Body: require_approval. Off waits for an approval itself.",
        body=True,
        pending=True,
    ),
    RouteCommand(
        "settings secrets show",
        "GET",
        "/settings/secrets",
        _UI + "Secrets · storage",
        "Where the master key is kept.",
    ),
    RouteCommand(
        "settings secrets set",
        "PUT",
        "/settings/secrets",
        _UI + "Secrets · storage",
        "Move the master key. Body: master_key_storage.",
        body=True,
    ),
    RouteCommand(
        "settings features",
        "GET",
        "/daemon/features",
        _UI + "Experimental",
        "The experimental features and whether each is on.",
    ),
    RouteCommand(
        "settings feature set",
        "PUT",
        "/daemon/features/{key}",
        _UI + "Experimental",
        "Switch a feature. Body: enabled.",
        body=True,
    ),
    RouteCommand(
        "settings feature reset",
        "DELETE",
        "/daemon/features/{key}",
        _UI + "Experimental · back to default",
        "Forget this machine's choice.",
    ),
    RouteCommand(
        "settings engine show",
        "GET",
        "/internal-engine-config",
        _UI + "Engine",
        "The engine's transcription model and upkeep passes.",
    ),
    RouteCommand(
        "settings engine transcribe-model",
        "PUT",
        "/internal-engine-config/transcribe-model",
        _UI + "Engine · transcription",
        "Choose the transcription model. Body: model.",
        body=True,
    ),
    RouteCommand(
        "settings engine upkeep",
        "PUT",
        "/internal-engine-config/upkeep",
        _UI + "Engine · upkeep",
        "Switch or schedule an upkeep pass. Body: pass, enabled, interval_s, use_default_interval.",
        body=True,
    ),
    RouteCommand(
        "settings retention list",
        "GET",
        "/retention/policies",
        _UI + "Data · retention",
        "How long each log is kept.",
    ),
    RouteCommand(
        "settings retention set",
        "PATCH",
        "/retention/policies/{table_name}",
        _UI + "Data · retention",
        "Set how long a log is kept. Body: retention_days.",
        body=True,
    ),
    RouteCommand(
        "settings retention preview",
        "GET",
        "/retention/policies/{table_name}/preview",
        _UI + "Data · retention · preview",
        "What a shorter period would delete.",
        query=(Q("days", kind=int),),
    ),
    RouteCommand(
        "settings retention prune",
        "POST",
        "/retention/prune",
        _UI + "Data · Prune now",
        "Prune every log to its period now.",
        body=True,
    ),
    RouteCommand(
        "settings storage show",
        "GET",
        "/storage",
        _UI + "Data · storage",
        "What Coffer stores and how much.",
    ),
    RouteCommand(
        "settings storage clear-cache",
        "POST",
        "/storage/cache/clear",
        _UI + "Data · Clear cache",
        "Delete caches Coffer can rebuild.",
    ),
]

mount(SPECS)
