"""``coffer channel`` and ``coffer conversation`` — the Channels and Conversations pages.

Spec channels "Manage channels from the Channels page" and
chat "Show every agent's sessions on the Conversations page". Creating,
changing and deleting a channel is a resource (``coffer resource``); these are
a channel's own actions.
"""

from __future__ import annotations

from coffer.surfaces.cli._route_command import RouteCommand, mount

C = {"uid": "channel"}
_UI = "Channels · "

SPECS = [
    RouteCommand(
        "channel status",
        "GET",
        "/channels/{uid}/status",
        _UI + "a channel's state",
        "Whether the channel is connected, and what waits.",
        names=C,
    ),
    RouteCommand(
        "channel restart",
        "POST",
        "/channels/{uid}/restart",
        _UI + "Restart",
        "Reconnect the channel.",
        names=C,
    ),
    RouteCommand(
        "channel notify",
        "POST",
        "/channels/{uid}/notify",
        _UI + "Send a test message",
        "Send a message through the channel. Body: text, chat_id.",
        names=C,
        body=True,
    ),
    RouteCommand(
        "channel pairing start",
        "POST",
        "/channels/{uid}/pairing-code",
        _UI + "People · Add a person (pairing code)",
        "Issue a pairing code a person sends to the bot.",
        names=C,
        body=True,
    ),
    RouteCommand(
        "channel pairing cancel",
        "DELETE",
        "/channels/{uid}/pairing-code",
        _UI + "People · cancel the code",
        "Withdraw the pairing code.",
        names=C,
    ),
    RouteCommand(
        "channel person remove",
        "DELETE",
        "/channels/{uid}/people/{sender_id}",
        _UI + "People · Remove",
        "Remove a paired person.",
        names=C,
    ),
    RouteCommand(
        "channel check-credentials",
        "POST",
        "/channels/validate-credentials",
        _UI + "Add · check the credentials",
        "Check a platform's credentials before saving. Body: platform, bot_token | "
        "app_id + app_secret, channel_uid.",
        body=True,
    ),
    RouteCommand(
        "conversation rename",
        "PATCH",
        "/chat/conversations/{id}",
        "Conversations · Rename",
        "Rename a conversation. Body: title.",
        body=True,
    ),
    RouteCommand(
        "conversation interrupt",
        "POST",
        "/chat/conversations/{id}/interrupt",
        "Conversations · Stop",
        "Stop the turn in progress.",
    ),
    RouteCommand(
        "conversation delete",
        "DELETE",
        "/chat/conversations/{id}",
        "Conversations · Delete",
        "Delete a conversation.",
    ),
]

mount(SPECS)
