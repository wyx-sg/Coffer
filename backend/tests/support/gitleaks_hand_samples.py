"""Hand-written samples for the bundled gitleaks rules.

``regex_samples`` builds a sample for nearly every rule. A rule it cannot
build one for needs context it cannot invent (a YAML block, an XML attribute,
a placeholder an allowlist drops), so it is written here, adapted from the
``tps``/``fps`` of the upstream rule (gitleaks v8.30.1,
``cmd/generate/config/rules/*.go``).

Every secret is assembled at runtime from seeded random pieces and short
literals, so no line of this file matches a gitleaks rule.
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass

_ALNUM = string.ascii_letters + string.digits
_HEX = "0123456789abcdef"
_TOKEN = _ALNUM + "-_"


def rand(rule_id: str, n: int, alphabet: str = _ALNUM) -> str:
    """``n`` seeded characters; distinct per rule and per length."""
    rng = random.Random(f"{rule_id}:{n}")
    return "".join(rng.choice(alphabet) for _ in range(n))


@dataclass(frozen=True)
class Hand:
    """A path, a text the rule must find, and one it must not."""

    path: str
    positive: str
    negative: str


def _airtable() -> Hand:
    rid = "airtable-personnal-access-token"
    head = "airtable_token = " + "pa" + "t"
    return Hand(
        "",
        head + rand(rid, 14) + "." + rand(rid, 64, _HEX),
        head + rand(rid, 13) + "." + rand(rid, 64, _HEX),
    )


def _curl_header() -> Hand:
    rid = "curl-auth-header"
    cmd = "curl -H 'Authorization: " + "Bearer "
    return Hand("", cmd + rand(rid, 32, _HEX) + "'", cmd + rand(rid, 7, _HEX) + "'")


def _curl_user() -> Hand:
    rid = "curl-auth-user"
    user, password = "elastic", rand(rid, 16)
    return Hand(
        "",
        f"curl --cacert ca.crt -u {user}:{password} https://localhost:9200",
        # Upstream's placeholder false positive.
        "curl -i -u 'test:" + "test'",
    )


def _facebook() -> Hand:
    rid = "facebook-access-token"
    head = "facebook " + rand(rid, 15, string.digits) + "|"
    return Hand(
        "",
        head + rand(rid, 27, _TOKEN),
        head + rand(rid, 26, _TOKEN),
    )


def _kubernetes() -> Hand:
    rid = "kubernetes-secret-yaml"
    doc = "apiVersion: v1\nkind: Secret\ndata:\n  password: "
    return Hand("secret.yaml", doc + rand(rid, 24), doc + "YmFy" + "Cg==")


def _nuget() -> Hand:
    rid = "nuget-config-password"
    head = '<add key="ClearText' + 'Password" value="'
    return Hand(
        "Nuget.config",
        head + rand(rid, 18) + '" />',
        head + "abc" + '" />',
    )


def _sidekiq_url() -> Hand:
    rid = "sidekiq-sensitive-url"
    host = "@enterprise.contribsys" + ".com/"
    return Hand(
        "",
        "https://" + rand(rid, 8, _HEX) + ":" + rand(rid, 8, _HEX) + host,
        "https://" + rand(rid, 7, _HEX) + ":" + rand(rid, 8, _HEX) + host,
    )


def _slack_config() -> Hand:
    rid = "slack-config-access-token"
    head = '"access_token": "' + "xoxe." + "xoxp-1-"
    return Hand(
        "",
        head + rand(rid, 163) + '"',
        head + rand(rid, 162) + '"',
    )


def _slack_webhook() -> Hand:
    rid = "slack-webhook-url"
    head = "https://hooks.slack" + ".com/services/"
    return Hand("", head + rand(rid, 44), head + rand(rid, 42))


HAND: dict[str, Hand] = {
    "airtable-personnal-access-token": _airtable(),
    "curl-auth-header": _curl_header(),
    "curl-auth-user": _curl_user(),
    "facebook-access-token": _facebook(),
    "kubernetes-secret-yaml": _kubernetes(),
    "nuget-config-password": _nuget(),
    "sidekiq-sensitive-url": _sidekiq_url(),
    "slack-config-access-token": _slack_config(),
    "slack-webhook-url": _slack_webhook(),
}
