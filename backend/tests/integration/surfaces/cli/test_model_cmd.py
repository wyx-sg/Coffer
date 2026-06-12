"""Integration tests for `coffer model` CLI commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from coffer.surfaces.cli.main import app

_runner = CliRunner()


# ---------------------------------------------------------------------------
# model add
# ---------------------------------------------------------------------------


def test_model_add(in_proc_chat_daemon):
    result = _runner.invoke(
        app,
        [
            "model",
            "add",
            "--provider",
            "anthropic",
            "--model",
            "claude-sonnet-4-6",
            "--name",
            "My Claude",
            "--credential-ref",
            "my-key",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "added model" in result.output


def test_model_add_invalid_provider(in_proc_chat_daemon):
    """Missing credential_ref for anthropic → 400 → exit code 6."""
    result = _runner.invoke(
        app,
        [
            "model",
            "add",
            "--provider",
            "anthropic",
            "--model",
            "claude-sonnet-4-6",
            "--name",
            "Bad Model",
            # No --credential-ref
        ],
    )
    assert result.exit_code == 6, result.output


# ---------------------------------------------------------------------------
# model list
# ---------------------------------------------------------------------------


def test_model_list_empty(in_proc_chat_daemon):
    result = _runner.invoke(app, ["model", "list"])
    assert result.exit_code == 0, result.output


def test_model_list_shows_added_model(in_proc_chat_daemon):
    _runner.invoke(
        app,
        [
            "model",
            "add",
            "--provider",
            "anthropic",
            "--model",
            "claude-sonnet-4-6",
            "--name",
            "TestModel",
            "--credential-ref",
            "k1",
        ],
    )
    result = _runner.invoke(app, ["model", "list"])
    assert result.exit_code == 0, result.output
    assert "TestModel" in result.output


def test_model_list_json(in_proc_chat_daemon):
    """--json flag must emit parseable machine-readable output."""
    _runner.invoke(
        app,
        [
            "model",
            "add",
            "--provider",
            "anthropic",
            "--model",
            "claude-sonnet-4-6",
            "--name",
            "JsonModel",
            "--credential-ref",
            "k2",
        ],
    )
    result = _runner.invoke(app, ["model", "list", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "models" in data
    assert any(m["display_name"] == "JsonModel" for m in data["models"])


# ---------------------------------------------------------------------------
# model edit
# ---------------------------------------------------------------------------


def test_model_edit(in_proc_chat_daemon):
    add_result = _runner.invoke(
        app,
        [
            "model",
            "add",
            "--provider",
            "anthropic",
            "--model",
            "claude-sonnet-4-6",
            "--name",
            "EditMe",
            "--credential-ref",
            "k3",
        ],
    )
    assert add_result.exit_code == 0, add_result.output

    # Get the model id from --json list
    list_result = _runner.invoke(app, ["model", "list", "--json"])
    data = json.loads(list_result.output)
    model_id = data["models"][0]["id"]

    result = _runner.invoke(app, ["model", "edit", model_id, "--name", "EditedName"])
    assert result.exit_code == 0, result.output
    assert "updated" in result.output

    # Verify rename
    list_result2 = _runner.invoke(app, ["model", "list", "--json"])
    data2 = json.loads(list_result2.output)
    assert any(m["display_name"] == "EditedName" for m in data2["models"])


def test_model_edit_not_found(in_proc_chat_daemon):
    result = _runner.invoke(app, ["model", "edit", "no-such-id", "--name", "x"])
    assert result.exit_code == 4, result.output


def test_model_edit_no_options(in_proc_chat_daemon):
    """Calling edit with no fields should exit 6."""
    result = _runner.invoke(app, ["model", "edit", "some-id"])
    assert result.exit_code == 6, result.output


# ---------------------------------------------------------------------------
# model rm
# ---------------------------------------------------------------------------


def test_model_rm(in_proc_chat_daemon):
    _runner.invoke(
        app,
        [
            "model",
            "add",
            "--provider",
            "anthropic",
            "--model",
            "claude-sonnet-4-6",
            "--name",
            "RmMe",
            "--credential-ref",
            "k4",
        ],
    )
    list_result = _runner.invoke(app, ["model", "list", "--json"])
    model_id = json.loads(list_result.output)["models"][0]["id"]

    result = _runner.invoke(app, ["model", "rm", model_id])
    assert result.exit_code == 0, result.output
    assert "removed" in result.output

    # List should now be empty
    list_result2 = _runner.invoke(app, ["model", "list", "--json"])
    data2 = json.loads(list_result2.output)
    assert data2["models"] == []


def test_model_rm_not_found(in_proc_chat_daemon):
    result = _runner.invoke(app, ["model", "rm", "no-such-id"])
    assert result.exit_code == 4, result.output


# ---------------------------------------------------------------------------
# Full round-trip: add → list → edit → rm
# ---------------------------------------------------------------------------


def test_model_crud_roundtrip(in_proc_chat_daemon):
    # Add (ollama requires base_url but no credential_ref)
    r = _runner.invoke(
        app,
        [
            "model",
            "add",
            "--provider",
            "ollama",
            "--model",
            "llama3",
            "--name",
            "Llama3",
            "--base-url",
            "http://localhost:11434",
        ],
    )
    assert r.exit_code == 0, r.output

    # List JSON
    r = _runner.invoke(app, ["model", "list", "--json"])
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert len(data["models"]) == 1
    model_id = data["models"][0]["id"]
    assert data["models"][0]["provider"] == "ollama"

    # Edit
    r = _runner.invoke(app, ["model", "edit", model_id, "--name", "Renamed Llama"])
    assert r.exit_code == 0, r.output

    # Verify
    r = _runner.invoke(app, ["model", "list", "--json"])
    data = json.loads(r.output)
    assert data["models"][0]["display_name"] == "Renamed Llama"

    # Remove
    r = _runner.invoke(app, ["model", "rm", model_id])
    assert r.exit_code == 0, r.output

    # Verify empty
    r = _runner.invoke(app, ["model", "list", "--json"])
    data = json.loads(r.output)
    assert data["models"] == []
