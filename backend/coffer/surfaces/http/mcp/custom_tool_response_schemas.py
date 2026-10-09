"""Wire models of a custom-tool group's response settings (spec mcp-gateway
"Judge a custom tool's answer by its group's response rules").

The same shapes are read and written; the domain models in
``domain/mcp/http_api_response`` check them when a group or tool is saved.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ResponseValueSourceName = Literal["status", "header", "json"]
ResponseMessageSourceName = Literal["header", "json"]


class CustomToolResponseField(BaseModel):
    """Where a rule reads the API's own error message."""

    source: ResponseMessageSourceName
    #: A response header's name, or a JSON Pointer into the body (``/msg``).
    name: str


class CustomToolResponseRule(BaseModel):
    """One value of the answer and the values that mean success."""

    source: ResponseValueSourceName
    #: A response header's name, or a JSON Pointer (``/code``); empty for status.
    name: str = ""
    #: The values that mean success, compared as text (``0``, ``true``, ``OK``).
    ok_values: list[str]
    #: What an answer without the value means.
    missing: Literal["ok", "error"] = "ok"
    message: CustomToolResponseField | None = None


class CustomToolResponse(BaseModel):
    """A group's response settings."""

    #: Response headers reported beside the built-in request and trace ids.
    diagnostic_headers: list[str] = Field(default_factory=list)
    #: The rules every tool's answer is judged by (a tool may set its own).
    rules: list[CustomToolResponseRule] = Field(default_factory=list)


class CustomToolRuleFailureOut(BaseModel):
    """The first rule a test's answer broke."""

    rule: CustomToolResponseRule
    #: The value read, masked and cut; ``null`` when the answer lacked it.
    value: str | None
    #: The API's own error text, masked and cut; ``null`` when there is none.
    message: str | None
    #: One line saying what broke, as the agent's tool result says it.
    summary: str


__all__ = [
    "CustomToolResponse",
    "CustomToolResponseField",
    "CustomToolResponseRule",
    "CustomToolRuleFailureOut",
]
