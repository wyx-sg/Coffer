"""A rename reaches the other machine as a rename (spec vault-sync).

This is the regression test for the failure that motivated
[Resource Identity Is an Immutable `uid`](../../../../docs/decisions/resource-identity-is-an-immutable-uid.md).

While a resource's identity was its NAME, the bundle laid documents out at
``resources/<kind>/<name>.yaml``, so renaming one on machine A published a
deletion beside an addition. The receiving machine could not tell that from a
delete-and-create, and ran the real ``ResourceService.delete``: the row's
cascade took its kind-owned state with it, and the orphaned-credential release
took the secret nothing else cited. Whether the addition that followed could
then be applied depended on whether the NEW name sorted before or after the old
one in the path-ordered apply loop — so the same user action was lossless or
destructive according to the first letter of the name they chose.

Both orderings are exercised, because only one of them used to fail and a test
that picked the lucky one would have gone green over the bug.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.resource import ResourceRef
from coffer.domain.scope import Scope
from tests.integration.sync.harness import VaultMachine, settle, two_machines

pytestmark = pytest.mark.timeout(120)

CRED = "mcp_server/renamed/key"


async def _publish_one(tmp_path: pathlib.Path, name: str) -> tuple[VaultMachine, VaultMachine]:
    """Two machines that already agree on one credential-citing resource."""
    a, b = await two_machines(tmp_path, shared_key=True)
    a.set_credential(CRED, "s3cret")
    await a.register("mcp_server", name, {"value": "v", "credential_ref": CRED})
    await settle(a, b)
    assert await b.resource_names("mcp_server") == [name]
    assert b.has_credential(CRED), "precondition: the secret reached the other machine"
    return a, b


async def _rename(machine: VaultMachine, kind: str, name: str, new_name: str) -> None:
    await machine.resources.rename(ResourceRef(kind, name), new_name, "test")


@pytest.mark.acceptance(spec="vault-sync", scenario="a rename travels as a rename")
@pytest.mark.parametrize(
    ("before", "after"),
    [
        # The new document sorts AFTER the old one, so the apply loop reaches
        # the deletion FIRST. This is the ordering that used to destroy the
        # credential and leave the resource unimportable forever.
        ("aaa", "zzz"),
        # The mirror image, which used to survive by luck alone: the addition
        # landed first, so for one moment two rows cited the same secret and
        # the release found a citation and stood down.
        ("zzz", "aaa"),
    ],
)
async def test_a_rename_travels_as_a_rename(tmp_path: pathlib.Path, before: str, after: str):
    a, b = await _publish_one(tmp_path, before)

    await _rename(a, "mcp_server", before, after)
    await settle(a, b)

    assert await b.resource_names("mcp_server") == [after]
    assert b.has_credential(CRED), "renaming a resource must not delete its secret elsewhere"


@pytest.mark.acceptance(spec="vault-sync", scenario="a rename travels as a rename")
async def test_a_rename_leaves_the_other_machines_reach_alone(tmp_path: pathlib.Path):
    """Reach is machine-local, and a rename is not a decision about it.

    The receiving machine had narrowed the resource to one agent. A rename
    arriving as delete-plus-create dropped that narrowing on the floor and
    re-created the row at the framework default — unscoped, active for every
    agent — which is the silent WIDENING the reach design exists to prevent.
    """
    a, b = await _publish_one(tmp_path, "aaa")
    await b.set_scope("mcp_server", "aaa", Scope(agents=["codex"]))
    await b.set_enabled("mcp_server", "aaa", False)

    await _rename(a, "mcp_server", "aaa", "zzz")
    await settle(a, b)

    enabled, scope = await b.reach("mcp_server", "zzz")
    assert scope == Scope(agents=["codex"])
    assert enabled is False
