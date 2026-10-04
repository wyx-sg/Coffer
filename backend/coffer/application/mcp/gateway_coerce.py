"""SDK result coercion for the gateway's invocation handlers.

Split out of ``gateway_handlers`` to keep that module within its file-size
budget; ``gateway_handlers`` re-exports the three coercers it builds its
capability specs from.
"""

from __future__ import annotations

from typing import Any

from coffer.domain.errors import UpstreamUnavailable


def _coerce_result(sdk_result: Any, method: str) -> dict[str, Any]:
    """Convert an mcp SDK result object to a JSON-friendly dict.

    Raises UpstreamUnavailable when the result is neither a Pydantic model
    nor a dict — previously the tools/call path returned ``{"content": []}``
    which silently masked SDK contract drift. ``method`` only
    flavours the error message.

    A single implementation behind the three thin wrappers below,
    which used to be byte-identical except for that message.
    """
    if hasattr(sdk_result, "model_dump"):
        dumped: dict[str, Any] = sdk_result.model_dump(
            exclude_none=True, mode="json", by_alias=True
        )
        return dumped
    if isinstance(sdk_result, dict):
        return sdk_result
    raise UpstreamUnavailable(f"upstream returned unparseable {method} result")


def coerce_call_result(sdk_result: Any) -> dict[str, Any]:
    return _coerce_result(sdk_result, "tools/call")


def coerce_read_result(sdk_result: Any) -> dict[str, Any]:
    return _coerce_result(sdk_result, "resources/read")


def coerce_prompt_result(sdk_result: Any) -> dict[str, Any]:
    return _coerce_result(sdk_result, "prompts/get")
