"""Unit tests for the official MCP Registry entry mapper (ADR-029).

Pure domain logic — exercises the registryType→command inference, argument
assembly, env-var/secret extraction, http/remote handling, and the defensive
parsing of a preview API whose fields are all optional.
"""

from __future__ import annotations

from coffer.domain.mcp.registry import map_registry_entry


def _entry(server: dict) -> dict:  # type: ignore[type-arg]
    return {"server": server}


def test_npm_stdio_package_infers_npx_and_pins_version() -> None:
    s = map_registry_entry(
        _entry(
            {
                "name": "com.example/fs",
                "description": "files",
                "version": "0.1.3",
                "packages": [
                    {
                        "registryType": "npm",
                        "identifier": "remote-fs-mcp",
                        "version": "0.1.3",
                        "transport": {"type": "stdio"},
                        "runtimeArguments": [{"value": "-y", "type": "positional"}],
                        "environmentVariables": [
                            {"name": "GCS_BUCKET", "isRequired": True},
                            {"name": "GCS_KEY", "isSecret": True},
                        ],
                    }
                ],
            }
        )
    )
    assert s is not None and s.installable
    assert s.registry_type == "npm"
    assert s.draft is not None
    assert s.draft.transport_type == "stdio"
    assert s.draft.command == "npx"
    assert s.draft.args == ("-y", "remote-fs-mcp@0.1.3")
    assert {e.key: e.is_secret for e in s.draft.env} == {"GCS_BUCKET": False, "GCS_KEY": True}
    assert next(e for e in s.draft.env if e.key == "GCS_BUCKET").required is True


def test_npm_inserts_yes_flag_when_missing() -> None:
    s = map_registry_entry(
        _entry(
            {
                "name": "x/y",
                "packages": [
                    {"registryType": "npm", "identifier": "p", "transport": {"type": "stdio"}}
                ],
            }
        )
    )
    assert s and s.draft and s.draft.command == "npx"
    assert s.draft.args[0] == "-y"  # synthesized when the registry omits it
    assert s.draft.args[-1] == "p"  # no version → bare identifier


def test_pypi_infers_uvx_and_appends_package_arguments() -> None:
    s = map_registry_entry(
        _entry(
            {
                "name": "io.github.u/medium",
                "packages": [
                    {
                        "registryType": "pypi",
                        "identifier": "medium-ops",
                        "version": "0.1.0",
                        "transport": {"type": "stdio"},
                        "packageArguments": [
                            {"value": "mcp", "type": "positional"},
                            {"value": "serve", "type": "positional"},
                        ],
                    }
                ],
            }
        )
    )
    assert s and s.draft
    assert s.draft.command == "uvx"
    # uvx: bare identifier (no pin) then the program's own args.
    assert s.draft.args == ("medium-ops", "mcp", "serve")


def test_oci_infers_docker_run_flags() -> None:
    s = map_registry_entry(
        _entry(
            {
                "name": "x/spotdb",
                "packages": [
                    {
                        "registryType": "oci",
                        "identifier": "docker.io/x/spotdb:0.1.0",
                        "transport": {"type": "stdio"},
                    }
                ],
            }
        )
    )
    assert s and s.draft
    assert s.draft.command == "docker"
    assert s.draft.args == ("run", "-i", "--rm", "docker.io/x/spotdb:0.1.0")


def test_runtime_hint_overrides_inference() -> None:
    s = map_registry_entry(
        _entry(
            {
                "name": "x/y",
                "packages": [
                    {
                        "registryType": "pypi",
                        "identifier": "p",
                        "runtimeHint": "uvx",
                        "transport": {"type": "stdio"},
                    }
                ],
            }
        )
    )
    assert s and s.draft and s.draft.command == "uvx"


def test_cargo_and_mcpb_are_not_installable() -> None:
    for rtype in ("cargo", "mcpb", "unknownthing"):
        s = map_registry_entry(
            _entry(
                {
                    "name": f"x/{rtype}",
                    "packages": [
                        {"registryType": rtype, "identifier": "p", "transport": {"type": "stdio"}}
                    ],
                }
            )
        )
        assert s is not None
        assert s.installable is False
        assert s.draft is None


def test_unresolved_template_arguments_are_skipped() -> None:
    s = map_registry_entry(
        _entry(
            {
                "name": "x/y",
                "packages": [
                    {
                        "registryType": "npm",
                        "identifier": "p",
                        "transport": {"type": "stdio"},
                        "packageArguments": [
                            {"value": "--port", "type": "named", "name": "--port"},
                            {"value": "{port}", "type": "positional"},  # template → dropped
                            {"value": "ok", "type": "positional"},
                        ],
                    }
                ],
            }
        )
    )
    assert s and s.draft
    assert "{port}" not in s.draft.args
    assert "ok" in s.draft.args


def test_streamable_http_package_maps_to_http_draft() -> None:
    s = map_registry_entry(
        _entry(
            {
                "name": "x/hosted",
                "packages": [
                    {
                        "registryType": "npm",
                        "identifier": "p",
                        "transport": {"type": "streamable-http", "url": "https://h.example/mcp"},
                    }
                ],
            }
        )
    )
    assert s and s.draft
    assert s.draft.transport_type == "http"
    assert s.draft.url == "https://h.example/mcp"
    assert s.transport_type == "http"


def test_remote_only_server_maps_to_http_with_secret_headers() -> None:
    s = map_registry_entry(
        _entry(
            {
                "name": "x/remote",
                "remotes": [
                    {
                        "type": "streamable-http",
                        "url": "https://api.example/mcp",
                        "headers": [
                            {"name": "Authorization", "isSecret": True, "isRequired": True}
                        ],
                    }
                ],
            }
        )
    )
    assert s and s.draft
    assert s.draft.transport_type == "http"
    assert s.draft.url == "https://api.example/mcp"
    assert s.draft.env[0].key == "Authorization"
    assert s.draft.env[0].is_secret is True


def test_homepage_prefers_website_then_repository() -> None:
    s = map_registry_entry(_entry({"name": "x/y", "repository": {"url": "https://github.com/x/y"}}))
    assert s and s.homepage == "https://github.com/x/y"
    s2 = map_registry_entry(
        _entry({"name": "x/y", "websiteUrl": "https://w", "repository": {"url": "https://gh"}})
    )
    assert s2 and s2.homepage == "https://w"


def test_entry_without_name_is_dropped() -> None:
    assert map_registry_entry({"server": {"description": "no name"}}) is None
    assert map_registry_entry({"server": {"name": ""}}) is None
    assert map_registry_entry("garbage") is None
    assert map_registry_entry({}) is None


def test_malformed_packages_do_not_crash_and_yield_no_draft() -> None:
    s = map_registry_entry(
        _entry({"name": "x/y", "packages": ["not-a-dict", 5], "remotes": "nope"})
    )
    assert s is not None
    assert s.installable is False
    assert s.draft is None
    assert s.description == ""  # missing description tolerated


def test_bare_server_object_without_wrapper() -> None:
    # Some shapes don't nest under "server"; tolerate a bare server dict.
    s = map_registry_entry({"name": "x/y", "description": "bare"})
    assert s is not None and s.name == "x/y" and s.description == "bare"


def test_docker_forwards_env_as_e_flags() -> None:
    s = map_registry_entry(
        _entry(
            {
                "name": "x/db",
                "packages": [
                    {
                        "registryType": "oci",
                        "identifier": "docker.io/x/db:1.0",
                        "transport": {"type": "stdio"},
                        "environmentVariables": [
                            {"name": "DB_URL", "isRequired": True},
                            {"name": "DB_KEY", "isSecret": True},
                        ],
                    }
                ],
            }
        )
    )
    assert s and s.draft and s.draft.command == "docker"
    # Each declared env var is forwarded into the container via `-e <key>`.
    assert s.draft.args == (
        "run",
        "-i",
        "--rm",
        "-e",
        "DB_URL",
        "-e",
        "DB_KEY",
        "docker.io/x/db:1.0",
    )


def test_nuget_infers_dnx() -> None:
    s = map_registry_entry(
        _entry(
            {
                "name": "x/y",
                "packages": [
                    {
                        "registryType": "nuget",
                        "identifier": "Some.Mcp",
                        "transport": {"type": "stdio"},
                    }
                ],
            }
        )
    )
    assert s and s.draft and s.draft.command == "dnx"
    assert s.draft.args == ("Some.Mcp",)


def test_named_argument_value_dedup() -> None:
    s = map_registry_entry(
        _entry(
            {
                "name": "x/y",
                "packages": [
                    {
                        "registryType": "npm",
                        "identifier": "p",
                        "transport": {"type": "stdio"},
                        "packageArguments": [
                            {"type": "named", "name": "--port", "value": "8080"},
                            {"type": "named", "name": "--verbose", "value": "--verbose"},
                        ],
                    }
                ],
            }
        )
    )
    assert s and s.draft
    assert "--port" in s.draft.args and "8080" in s.draft.args
    # A named arg whose value duplicates its name yields a single token, not two.
    assert s.draft.args.count("--verbose") == 1


def test_package_takes_precedence_over_remote() -> None:
    s = map_registry_entry(
        _entry(
            {
                "name": "x/y",
                "packages": [
                    {"registryType": "npm", "identifier": "p", "transport": {"type": "stdio"}}
                ],
                "remotes": [{"type": "streamable-http", "url": "https://r"}],
            }
        )
    )
    assert s and s.draft
    assert s.draft.transport_type == "stdio"  # the installable package wins
    assert s.registry_type == "npm"


def test_noninstallable_package_falls_back_to_remote_nulling_registry_type() -> None:
    s = map_registry_entry(
        _entry(
            {
                "name": "x/y",
                "packages": [
                    {"registryType": "cargo", "identifier": "p", "transport": {"type": "stdio"}}
                ],
                "remotes": [{"type": "streamable-http", "url": "https://r"}],
            }
        )
    )
    assert s and s.draft
    assert s.draft.transport_type == "http" and s.draft.url == "https://r"
    assert s.installable is True
    assert s.registry_type is None  # the draft came from the remote, not the cargo package
