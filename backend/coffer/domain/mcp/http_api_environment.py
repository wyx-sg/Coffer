"""A custom-tool group's environments: where the same tools are sent.

Spec mcp-gateway "Keep a custom-tool group's environments in the group" and
"Choose a custom tool's environment on every call"; design
align-cli-with-ui-and-add-tool-environments D4-D6.

An environment holds everything that differs between copies of one API — the
base URL, header rows (plain or a stored secret), non-sensitive variables, a
switch and a timeout — so a group keeps ONE set of tools. Each call names its
environment through the reserved argument :data:`ENVIRONMENT_ARG`; nothing
keeps a "current" one.

``key`` is the environment's binding key: fixed at creation (its first name),
kept across renames, and ``""`` only for the environment a group from before
environments is lifted into, so that environment's secret bindings keep the
slot (the bare header name) they were approved under.

Pure: Pydantic and the standard library only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from coffer.domain.auth_scheme import AuthScheme, check_schemes
from coffer.domain.mcp.custom_tool_env_errors import (
    CustomToolEnvironmentDisabled,
    CustomToolEnvironmentRequired,
    CustomToolEnvironmentUnknown,
)
from coffer.domain.mcp.http_api_headers import HEADER_NAME_RE, check_headers, looks_like_secret

#: The argument every custom tool is advertised with, naming the environment.
ENVIRONMENT_ARG = "coffer_environment"
#: The name a group from before environments gets for its one environment.
LIFTED_ENVIRONMENT = "default"
ENV_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$")
VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
#: ``{env:NAME}`` in a tool's template.
ENV_HOLE = re.compile(r"\{env:([A-Za-z_][A-Za-z0-9_]{0,63})\}")


def env_vars_in(text: str) -> set[str]:
    return set(ENV_HOLE.findall(text))


class HttpApiEnvironment(BaseModel):
    """One place a group's tools are sent."""

    name: str
    #: The binding key (see the module docstring); defaults to the name.
    key: str = ""
    description: str = Field(default="", max_length=2000)
    enabled: bool = True
    base_url: HttpUrl
    headers: dict[str, str] = Field(default_factory=dict)
    #: ``{header name: ref}`` — headers whose credential is a stored secret.
    secret_refs: dict[str, str] = Field(default_factory=dict)
    #: ``{header name: scheme}`` — a secret header sent as ``<scheme> <secret>``.
    auth_schemes: dict[str, AuthScheme] = Field(default_factory=dict)
    #: Non-sensitive text a tool's template uses as ``{env:NAME}``.
    variables: dict[str, str] = Field(default_factory=dict)
    #: ``None`` uses the group's timeout.
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)

    @model_validator(mode="before")
    @classmethod
    def _key_defaults_to_name(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("key") is None and "name" in data:
            return {**data, "key": data["name"]}
        return data

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not ENV_NAME_RE.match(v):
            raise ValueError(
                f"environment name {v!r} must be 1-40 letters, digits, '_', '.' or '-', "
                "starting with a letter or digit"
            )
        return v

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        if v and not ENV_NAME_RE.match(v):
            raise ValueError(f"environment key {v!r} is not valid")
        return v

    @field_validator("base_url")
    @classmethod
    def _scheme(cls, v: HttpUrl) -> HttpUrl:
        if v.scheme not in ("http", "https"):
            raise ValueError("the base URL must be http or https")
        if v.query or v.fragment:
            raise ValueError("the base URL may not carry a query or a fragment")
        if "{" in str(v) or "%7B" in str(v).upper():
            raise ValueError("the base URL may not hold a variable or an argument")
        return v

    @field_validator("headers")
    @classmethod
    def _headers(cls, v: dict[str, str]) -> dict[str, str]:
        return check_headers(v, allow_holes=False)

    @field_validator("secret_refs")
    @classmethod
    def _secret_header_names(cls, v: dict[str, str]) -> dict[str, str]:
        for name in v:
            if not HEADER_NAME_RE.match(name):
                raise ValueError(f"{name!r} is not a valid header name")
        return v

    @field_validator("variables")
    @classmethod
    def _variables(cls, v: dict[str, str]) -> dict[str, str]:
        for name, value in v.items():
            if not VAR_NAME_RE.match(name):
                raise ValueError(f"variable name {name!r} must be letters, digits and '_'")
            if any(c in value for c in "{}\r\n"):
                raise ValueError(f"variable {name!r} may not hold braces or line breaks")
            if len(value) > 2000:
                raise ValueError(f"variable {name!r} is longer than 2000 characters")
            if looks_like_secret(value):
                raise ValueError(
                    f"variable {name!r} looks like a secret; bind a stored secret to a header "
                    "instead (variables are not protected)"
                )
        return v

    @model_validator(mode="after")
    def _consistent(self) -> HttpApiEnvironment:
        seen = [n.lower() for n in (*self.headers, *self.secret_refs)]
        if len(seen) != len(set(seen)):
            raise ValueError(f"a header may appear once in environment {self.name!r}")
        check_schemes(self.auth_schemes, self.secret_refs)
        return self

    def slot(self, header: str) -> str:
        """The secret boundary's slot for one of this environment's headers."""
        return header if self.key == "" else f"{self.key}:{header}"

    def slot_refs(self) -> dict[str, str]:
        return {self.slot(h): ref for h, ref in self.secret_refs.items()}

    def header_of(self, slot: str) -> str:
        return slot if self.key == "" else slot.split(":", 1)[1]


def lift_legacy(data: Mapping[str, Any]) -> dict[str, Any]:
    """A group stored before environments, as one environment ``default``.

    Its key is ``""`` so its bindings keep their slot; the top-level fields
    are dropped from the result."""
    out = dict(data)
    if out.get("environments"):
        for key in ("base_url", "headers", "auth_schemes"):
            out.pop(key, None)
        return out
    base_url = out.pop("base_url", None)
    env = {
        "name": LIFTED_ENVIRONMENT,
        "key": "",
        "base_url": base_url,
        "headers": out.pop("headers", None) or {},
        "secret_refs": out.get("secret_refs") or {},
        "auth_schemes": out.pop("auth_schemes", None) or {},
    }
    out["environments"] = [env] if base_url is not None else []
    return out


def select_environment(
    environments: list[HttpApiEnvironment], group: str, arguments: Mapping[str, Any] | None
) -> tuple[HttpApiEnvironment, dict[str, Any]]:
    """The environment a call names, and its arguments without the selector.

    Refuses an unknown or switched-off environment, and a missing choice when
    more than one environment is on; a group with one environment on uses it.
    """
    args = dict(arguments or {})
    chosen = args.pop(ENVIRONMENT_ARG, None)
    enabled = [e for e in environments if e.enabled]
    if chosen is None or chosen == "":
        if len(enabled) == 1:
            return enabled[0], args
        raise CustomToolEnvironmentRequired(group, [e.name for e in enabled])
    if not isinstance(chosen, str):
        raise CustomToolEnvironmentUnknown(group, str(chosen), [e.name for e in enabled])
    env = next((e for e in environments if e.name == chosen), None)
    if env is None:
        raise CustomToolEnvironmentUnknown(group, chosen, [e.name for e in enabled])
    if not env.enabled:
        raise CustomToolEnvironmentDisabled(group, chosen)
    return env, args


def advertised_schema(
    schema: Mapping[str, Any], environments: list[HttpApiEnvironment]
) -> dict[str, Any]:
    """A tool's argument schema as the gateway lists it: plus the environment
    choice, required once more than one environment is on."""
    enabled = [e.name for e in environments if e.enabled]
    props = dict(schema.get("properties") or {})
    props[ENVIRONMENT_ARG] = {
        "type": "string",
        "enum": enabled,
        "description": (
            "Which of this API's environments to call (Coffer reads it and never "
            "sends it upstream): " + ", ".join(enabled)
        ),
    }
    required = list(schema.get("required") or [])
    if len(enabled) > 1 and ENVIRONMENT_ARG not in required:
        required.append(ENVIRONMENT_ARG)
    out = {**schema, "type": "object", "properties": props}
    if required:
        out["required"] = required
    return out


__all__ = [
    "ENVIRONMENT_ARG",
    "ENV_HOLE",
    "ENV_NAME_RE",
    "LIFTED_ENVIRONMENT",
    "VAR_NAME_RE",
    "HttpApiEnvironment",
    "advertised_schema",
    "env_vars_in",
    "lift_legacy",
    "select_environment",
]
