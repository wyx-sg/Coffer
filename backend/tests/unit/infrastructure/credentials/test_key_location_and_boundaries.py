"""Where the master key lives, and who may reach the keychain (spec credentials).

The keychain is the shared in-memory backend from ``tests.fixtures.keyring``,
reached through the real ``KeyringAdapter`` — so the adapter's own code runs
while the developer's OS keychain is never touched.
"""

from __future__ import annotations

import ast
import pathlib
import stat
import tomllib

import grimp
import pytest
from cryptography.fernet import Fernet

from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.infrastructure.credentials.master_key import KEYCHAIN_REF, MasterKeyManager
from tests.fixtures.keyring import install_in_memory_keyring

_BACKEND = pathlib.Path(__file__).resolve().parents[4]
_COFFER = _BACKEND / "coffer"
_KEYRING_ADAPTER = _COFFER / "infrastructure" / "credentials" / "keyring_adapter.py"
_CREDENTIALS_CMD = _COFFER / "surfaces" / "cli" / "credentials_cmd.py"


def _imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


@pytest.mark.acceptance(
    spec="credentials", scenario="the master key lives in the file or the keychain, never both"
)
def test_the_master_key_lives_in_the_file_or_the_keychain_never_both(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = install_in_memory_keyring(monkeypatch)
    key_path = tmp_path / "master.key"
    mgr = MasterKeyManager(key_path=key_path, keyring=KeyringAdapter())
    key = mgr.resolve(allow_create=True)
    assert key is not None
    Fernet(key)
    assert key_path.exists() and KeyringAdapter().get(KEYCHAIN_REF) is None

    mgr.relocate("keychain")
    assert mgr.location == "keychain"
    assert not key_path.exists()
    assert KeyringAdapter().get(KEYCHAIN_REF) == key.decode()

    mgr.relocate("file")
    assert mgr.location == "file"
    assert key_path.read_bytes().strip() == key
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    assert KeyringAdapter().get(KEYCHAIN_REF) is None
    assert backend._data == {}

    # A fresh resolution finds the one copy there is.
    assert (
        MasterKeyManager(key_path=key_path, keyring=KeyringAdapter()).resolve(allow_create=False)
        == key
    )


@pytest.mark.acceptance(spec="credentials", scenario="only the keyring adapter imports keyring")
def test_only_the_keyring_adapter_imports_keyring() -> None:
    importers = sorted(
        path.relative_to(_COFFER).as_posix()
        for path in _COFFER.rglob("*.py")
        if any(m == "keyring" or m.startswith("keyring.") for m in _imported_modules(path))
    )
    assert importers == [_KEYRING_ADAPTER.relative_to(_COFFER).as_posix()]


@pytest.mark.acceptance(
    spec="credentials", scenario="credential commands import no credential code"
)
def test_credential_commands_import_no_credential_code() -> None:
    modules = _imported_modules(_CREDENTIALS_CMD)
    forbidden = {
        m
        for m in modules
        if m == "keyring"
        or m.startswith("keyring.")
        or m.startswith("coffer.infrastructure.credentials")
        or m.startswith("coffer.application.credentials")
        or m == "cryptography"
        or m.startswith("cryptography.")
    }
    assert forbidden == set()
    # The only way it reaches the vault is the daemon client.
    assert "coffer.surfaces.cli._client" in modules


_FORBIDDEN_FOR_CREDENTIALS_CMD = (
    "keyring",
    "cryptography",
    "coffer.infrastructure.credentials",
    "coffer.application.credentials",
)


@pytest.mark.acceptance(
    spec="credentials", scenario="credential commands import no credential code"
)
def test_credential_commands_reach_no_credential_code_even_transitively() -> None:
    """The direct-import scan above misses a helper the command imports that
    itself imports the keyring adapter. Walk the real import graph (the same
    grimp graph ``lint-imports`` builds, with the same settings) instead."""
    graph = grimp.build_graph(
        "coffer", include_external_packages=True, exclude_type_checking_imports=True
    )
    source = "coffer.surfaces.cli.credentials_cmd"
    assert source in graph.modules

    targets = {
        module
        for module in graph.modules
        for prefix in _FORBIDDEN_FOR_CREDENTIALS_CMD
        if module == prefix or module.startswith(prefix + ".")
    }
    # Guard against a vacuous pass: the graph must actually contain what we fence.
    assert {"keyring", "coffer.infrastructure.credentials.keyring_adapter"} <= targets

    chains = {
        target: chain
        for target in sorted(targets)
        if (chain := graph.find_shortest_chain(importer=source, imported=target))
    }
    assert chains == {}
    assert graph.find_shortest_chain(importer=source, imported="coffer.surfaces.cli._client")


def test_import_linter_fences_the_cli_off_the_credentials_package_transitively() -> None:
    """``make lint-imports`` is the CI half of the same boundary; it must keep
    existing, and must not be relaxed to direct-imports-only."""
    config = tomllib.loads((_BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    contracts = {c["name"]: c for c in config["tool"]["importlinter"]["contracts"]}
    contract = contracts["CLI does not access the keychain directly"]
    assert contract["type"] == "forbidden"
    assert "coffer.surfaces.cli" in contract["source_modules"]
    assert "coffer.infrastructure.credentials" in contract["forbidden_modules"]
    assert str(contract.get("allow_indirect_imports", "False")).lower() != "true"
