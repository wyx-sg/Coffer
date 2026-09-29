"""The reconciler's pure diff: pairing by key, equality including parameters."""

from __future__ import annotations

import pytest

from coffer.domain.reconcile import Item, Op, Subject, change_id, diff

_S = Subject("agent", "u1", "Work")


def _item(key: str, **params: object) -> Item:
    return Item(key=key, subject=_S, params=params, file=f"/f/{key}")


def test_equal_parameters_are_no_difference() -> None:
    assert diff("t", [_item("a", command="/bin/shim")], [_item("a", command="/bin/shim")]) == []


def test_a_changed_parameter_is_a_modification_not_presence() -> None:
    """The PR #413 rule: an entry that is there, with an argument Coffer no
    longer writes, is drift."""
    (d,) = diff(
        "t",
        [_item("a", command="coffer memory context --agent-uid u1")],
        [_item("a", command="coffer memory context --agent u1")],
    )
    assert d.op is Op.MODIFY
    assert d.changed_params == ("command",)
    assert d.desired is not None and d.observed is not None


def test_missing_and_unwanted_items_are_add_and_remove_in_stated_order() -> None:
    out = diff("t", [_item("b", x=1), _item("a", x=1)], [_item("c", x=1), _item("a", x=1)])
    assert [(d.key, d.op) for d in out] == [("b", Op.ADD), ("c", Op.REMOVE)]
    assert out[0].id == change_id("t", "b") == "t:b"
    assert out[0].file == "/f/b" and out[1].file == "/f/c"
    assert out[1].subject == _S


def test_changed_params_of_an_addition_lists_every_wanted_param() -> None:
    (d,) = diff("t", [_item("a", command="x", args=["--agent-uid", "u1"])], [])
    assert d.changed_params == ("args", "command")


def test_a_key_stated_twice_is_a_target_bug() -> None:
    with pytest.raises(ValueError, match="twice"):
        diff("t", [_item("a"), _item("a")], [])
    with pytest.raises(ValueError, match="observed"):
        diff("t", [], [_item("a"), _item("a")])
