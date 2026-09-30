"""The hand-off that puts SeaTalk's WebSocket SDK where Coffer loads it from
(spec channels/seatalk "Load the websocket client library from an
operator-supplied directory").

Coffer cannot ship the SDK and cannot fetch it either: it comes from SeaTalk's
Open Platform behind the person's own login. So the download stays with the
person, and everything after it — finding the archive, unpacking the package
into the directory Coffer imports from, checking it landed — is written up for
their agent. The facts are the directory (``$COFFER_SEATALK_SDK_DIR`` when that
chose it) and the documentation page; ``domain/handoff.py`` adds the rules
every hand-off carries, the one that leaves logins to the person included.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.domain.handoff import Handoff, render_handoff

#: The package the SDK archive carries, and what Coffer imports.
SDK_PACKAGE = "seatalk_oapi_sdk"


@dataclass(frozen=True)
class SdkLocation:
    """Where the daemon imports the SDK from."""

    directory: str
    #: ``$COFFER_SEATALK_SDK_DIR`` chose the directory, not Coffer's default.
    from_env: bool = False


def seatalk_sdk_handoff(channel: str, location: SdkLocation, docs_url: str) -> str:
    """The prompt for a SeaTalk channel whose websocket reports ``sdk_missing``."""
    target = f"{location.directory.rstrip('/')}/{SDK_PACKAGE}/"
    chosen_by = (
        "chosen by $COFFER_SEATALK_SDK_DIR in the daemon's environment"
        if location.from_env
        else "Coffer's default location"
    )
    return render_handoff(
        Handoff(
            task=(
                "Please put SeaTalk's WebSocket SDK where Coffer loads it from, so my "
                f"SeaTalk channel {channel} can receive messages."
            ),
            facts=(
                f"Coffer imports the Python package `{SDK_PACKAGE}` from {location.directory} "
                f"({chosen_by}); it is not there yet.",
                "The SDK is not on public PyPI. I download its archive myself from the SeaTalk "
                f"Open Platform ({docs_url}), because that needs my login.",
                "Coffer keeps retrying on its own, so no daemon restart is needed.",
            ),
            steps=(
                "If I have not downloaded the archive yet, tell me so and wait; then find it "
                "where downloads land (usually ~/Downloads), and ask me if you cannot.",
                f"Unpack it so that the package directory is {target} — the directory that "
                f"holds `{SDK_PACKAGE}`'s `__init__.py` — creating {location.directory} if "
                "needed. Do not pip-install it and do not change any other directory.",
                f"Check that {target}__init__.py exists, then run `coffer channel show "
                f"{channel}`: within a few seconds its inbound line should read "
                "websocket (connected).",
                "When it does, tell me to press Retry on the channel's page if it still shows "
                "the SDK as missing.",
            ),
        )
    )


__all__ = ["SDK_PACKAGE", "SdkLocation", "seatalk_sdk_handoff"]
