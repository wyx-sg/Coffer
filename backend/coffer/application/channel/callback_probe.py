"""Reachability self-test for a SeaTalk channel's public callback URL.

Signs a SeaTalk ``event_verification`` envelope with the channel's signing
secret and POSTs it to the public callback URL, expecting the listener to echo
the challenge. A correct echo proves the whole path works: public URL → tunnel →
loopback listener → signature check → handshake. The listener already answers
``event_verification`` after verifying the signature, so no special-casing is
needed on the receiving end.

Limitation: the probe both signs and verifies with Coffer's stored secret, so it
confirms the path and handshake — not that the secret matches SeaTalk's. A
secret mismatch only surfaces on the first real SeaTalk event.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass

import httpx

from coffer.domain.channel.signing import seatalk_signature

_PROBE_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class CallbackTestResult:
    ok: bool
    detail: str


async def probe_seatalk_callback(
    *, client: httpx.AsyncClient, url: str, signing_secret: str
) -> CallbackTestResult:
    """Round-trip a signed verification handshake through the public URL."""
    challenge = secrets.token_hex(16)
    body = json.dumps(
        {"event_type": "event_verification", "event": {"seatalk_challenge": challenge}}
    ).encode("utf-8")
    signature = seatalk_signature(body, signing_secret)
    try:
        response = await client.post(
            url,
            content=body,
            headers={"Content-Type": "application/json", "Signature": signature},
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as e:
        return CallbackTestResult(
            ok=False,
            detail=(
                f"could not reach {url} ({type(e).__name__}); is the tunnel running and "
                "pointed at the callback listener?"
            ),
        )
    if response.status_code != 200:
        return CallbackTestResult(
            ok=False,
            detail=(
                f"the callback URL returned HTTP {response.status_code}; expected 200 from the "
                "Coffer listener (check the tunnel target and the channel's signing secret)"
            ),
        )
    try:
        echoed = response.json().get("seatalk_challenge")
    except ValueError:
        return CallbackTestResult(
            ok=False, detail="the callback URL returned a non-JSON response; it is not the listener"
        )
    if echoed != challenge:
        return CallbackTestResult(
            ok=False, detail="the verification challenge did not echo back; the path is misrouted"
        )
    return CallbackTestResult(ok=True, detail="reachable — public URL → tunnel → listener verified")
