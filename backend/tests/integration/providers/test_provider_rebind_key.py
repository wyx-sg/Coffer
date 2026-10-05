"""A connection's key can be re-pointed at another stored secret (spec provider-switching).

``PATCH {secret_ref}`` moves the connection's ``secret_ref`` and touches no vault
entry; ``secret_value`` still rotates the current one; the two never travel together.
"""

from __future__ import annotations

import pathlib

import pytest

from tests.integration.providers.test_provider_requirements import (
    _anthropic,
    _daemon,
    _new,
    env,  # noqa: F401  (fixture)
)


@pytest.mark.acceptance(spec="provider-switching", scenario="use another stored secret")
def test_a_patch_can_use_another_stored_secret(env: pathlib.Path) -> None:  # noqa: F811
    with _daemon() as c:
        mine = _new(c, _anthropic("mine", secret="sk-mine"))
        other = _new(c, _anthropic("other", secret="sk-other"))
        mine_ref = c.get(f"/api/v1/providers/{mine}").json()["secret_ref"]
        other_ref = c.get(f"/api/v1/providers/{other}").json()["secret_ref"]
        assert mine_ref != other_ref

        r = c.patch(f"/api/v1/providers/{mine}", json={"secret_ref": other_ref})
        assert r.status_code == 200, r.text
        assert r.json()["secret_ref"] == other_ref
        assert c.get(f"/api/v1/providers/{mine}").json()["secret_ref"] == other_ref
        # The old entry is not deleted by the move; the other connection is untouched.
        assert c.get(f"/api/v1/providers/{other}").json()["secret_ref"] == other_ref

        # Both fields at once is refused with nothing changed.
        both = c.patch(
            f"/api/v1/providers/{mine}", json={"secret_ref": mine_ref, "secret_value": "sk-new"}
        )
        assert both.status_code == 422, both.text
        assert c.get(f"/api/v1/providers/{mine}").json()["secret_ref"] == other_ref


def test_a_patch_to_a_ref_nothing_is_stored_under_is_refused(env: pathlib.Path) -> None:  # noqa: F811
    with _daemon() as c:
        mine = _new(c, _anthropic("mine"))
        before = c.get(f"/api/v1/providers/{mine}").json()["secret_ref"]
        r = c.patch(f"/api/v1/providers/{mine}", json={"secret_ref": "secret/does-not-exist"})
        assert r.status_code >= 400, r.text
        assert c.get(f"/api/v1/providers/{mine}").json()["secret_ref"] == before
