"""What this build is allowed to claim about itself: the Keychain access group.

A signed release is stamped with the access group of Coffer's Team ID
(``<TEAMID>.coffer``) by the release pipeline, which also signs the binary with
the ``keychain-access-groups`` entitlement for it. A build from source carries
``None`` and therefore keeps the master key in the development fallback (the
``0600`` file, or the legacy login-keychain item when opted in), which the
daemon reports as a development build (spec credentials "Keep the master key
behind a storage port chosen by the build").

Deliberately a constant in the code and not a setting: an environment variable
or config key that chose the backend would be something an agent could write
to move a release's key back into a file.
"""

from __future__ import annotations

import sys

#: Replaced by the release pipeline in a signed build; ``None`` everywhere else.
KEYCHAIN_ACCESS_GROUP: str | None = None


def keychain_access_group() -> str | None:
    """The access group to keep the master key in, or None for a development build."""
    # Only a frozen release can carry the entitlement the group needs; a source
    # checkout that edited the constant still could not use it.
    return KEYCHAIN_ACCESS_GROUP if getattr(sys, "frozen", False) else None
