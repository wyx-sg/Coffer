"""``coffer provider`` and ``coffer model`` — the Model providers page.

Spec provider-switching "Offer every connection operation over REST and in the
web UI". A connection is named by its name or uid. A key
given inline (``secret_value``) should come on stdin (``--data -``), never as an
argument a shell history keeps.
"""

from __future__ import annotations

from coffer.surfaces.cli._route_command import RouteCommand, mount

P = {"uid": "provider"}
_UI = "Model providers · "

SPECS = [
    RouteCommand(
        "provider list",
        "GET",
        "/providers",
        _UI + "list",
        "Model provider connections.",
        columns=("name", "protocol", "base_url", "enabled"),
    ),
    RouteCommand(
        "provider show",
        "GET",
        "/providers/{uid}",
        _UI + "open a connection",
        "One connection.",
        names=P,
    ),
    RouteCommand(
        "provider add",
        "POST",
        "/providers",
        _UI + "Add connection",
        "Add a connection. Body: name, protocol, base_url, secret_ref | secret_value, "
        "models, description, local_runtime.",
        body=True,
        pending=True,
    ),
    RouteCommand(
        "provider update",
        "PATCH",
        "/providers/{uid}",
        _UI + "edit a connection",
        "Change a connection. Body: base_url, protocol, secret_ref | secret_value, "
        "models, description.",
        names=P,
        body=True,
        pending=True,
    ),
    RouteCommand(
        "provider delete-preview",
        "GET",
        "/providers/{uid}/delete-preview",
        _UI + "Delete… (what it affects)",
        "What deleting a connection would change.",
        names=P,
    ),
    RouteCommand(
        "provider delete",
        "DELETE",
        "/providers/{uid}",
        _UI + "Delete",
        "Delete a connection.",
        names=P,
    ),
    RouteCommand(
        "provider prices",
        "POST",
        "/providers/{uid}/prices",
        _UI + "model prices",
        "Prices of the given models on this connection. Body: models.",
        names=P,
        body=True,
    ),
    RouteCommand(
        "provider transcribe-default",
        "POST",
        "/providers/{uid}/transcribe-default",
        _UI + "Use for transcription",
        "Make this connection the transcription default.",
        names=P,
    ),
    RouteCommand(
        "provider detect-local",
        "POST",
        "/providers/detect-local",
        _UI + "Add · detect a local runtime",
        "Find a local model runtime (Ollama, LM Studio). Body: base_url.",
        body=True,
    ),
    RouteCommand(
        "provider price-list show",
        "GET",
        "/providers/price-list",
        "Settings · Usage · price list",
        "The bundled model price list and its age.",
    ),
    RouteCommand(
        "provider price-list refresh",
        "PUT",
        "/providers/price-list",
        "Settings · Usage · Refresh prices",
        "Refresh the price list. Body: refresh (--set refresh=true).",
        body=True,
    ),
    RouteCommand(
        "provider switch preview",
        "POST",
        "/providers/model-switch/preview",
        "Agents · switch model · review",
        "What switching an agent type's model would write. Body: agent_type, "
        "connection_uid, model, tier_models, native_model, clear_native_model.",
        body=True,
    ),
    RouteCommand(
        "provider switch apply",
        "POST",
        "/providers/model-switch/apply",
        "Agents · switch model · Switch",
        "Switch an agent type's model. Body as for preview, plus seen.",
        body=True,
    ),
    RouteCommand(
        "model list",
        "POST",
        "/models/list-models",
        _UI + "Add · list models",
        "Ask an endpoint which models it serves. Body: provider, base_url, secret_ref | "
        "secret_value.",
        body=True,
    ),
    RouteCommand(
        "model test",
        "POST",
        "/models/test-connection",
        _UI + "Add · Test",
        "Send one request to a model. Body: provider, base_url, model, secret_ref | secret_value.",
        body=True,
    ),
]

mount(SPECS)
