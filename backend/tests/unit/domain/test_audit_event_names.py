"""Every audit event name the backend records is an ``AuditEventType`` member.

The audit log is queried by event name (the Activity page filters on it, the
retention sweep keys on it), so a name typed as a free string in one route is
invisible to every consumer that reads the enum. This scans the package source
for ``.record(...)`` calls and refuses a string literal where the event type
goes, and resolves module-level ``_EVENT_*`` style constants to check they are
enum-derived too.
"""

from __future__ import annotations

import ast
from pathlib import Path

from coffer.domain.audit import AuditEventType

_PACKAGE = Path(__file__).resolve().parents[3] / "coffer"


def _event_arg(call: ast.Call) -> ast.expr | None:
    """The expression passed as the event type to a ``.record(...)`` call."""
    for kw in call.keywords:
        if kw.arg == "event_type":
            return kw.value
    return call.args[0] if call.args else None


def _module_constants(tree: ast.Module) -> dict[str, ast.expr]:
    out: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                out[target.id] = node.value
    return out


def _is_enum_value(expr: ast.expr) -> bool:
    """``AuditEventType.X`` or ``AuditEventType.X.value``."""
    if isinstance(expr, ast.Attribute) and expr.attr == "value":
        expr = expr.value
    return (
        isinstance(expr, ast.Attribute)
        and isinstance(expr.value, ast.Name)
        and expr.value.id == AuditEventType.__name__
        and expr.attr in AuditEventType.__members__
    )


def _record_calls() -> list[tuple[Path, ast.Call, dict[str, ast.expr]]]:
    found: list[tuple[Path, ast.Call, dict[str, ast.expr]]] = []
    for path in sorted(_PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _module_constants(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "record"
            ):
                found.append((path, node, constants))
    return found


def test_scan_finds_the_audit_call_sites() -> None:
    """Guard the guard: an empty scan would make the assertions below vacuous."""
    assert len(_record_calls()) > 20


def test_no_record_call_passes_a_string_literal_event_type() -> None:
    offenders: list[str] = []
    for path, call, constants in _record_calls():
        arg = _event_arg(call)
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            offenders.append(f"{path.relative_to(_PACKAGE)}:{call.lineno} {arg.value!r}")
        elif isinstance(arg, ast.Name) and arg.id in constants:
            value = constants[arg.id]
            if not _is_enum_value(value):
                rendered = ast.unparse(value)
                offenders.append(
                    f"{path.relative_to(_PACKAGE)}:{call.lineno} {arg.id} = {rendered}"
                )
    assert not offenders, "audit event names must be AuditEventType members:\n" + "\n".join(
        offenders
    )


def test_memory_route_events_are_enum_members() -> None:
    assert AuditEventType("memory_organised") is AuditEventType.MEMORY_ORGANISED
    assert AuditEventType("memory_override_set") is AuditEventType.MEMORY_OVERRIDE_SET
    assert AuditEventType("memory_override_cleared") is AuditEventType.MEMORY_OVERRIDE_CLEARED


def test_event_values_are_unique_snake_case() -> None:
    values = [m.value for m in AuditEventType]
    assert len(values) == len(set(values))
    assert all(v == v.lower() and " " not in v for v in values)
