---
title: Error codes
description: Every error code the Coffer daemon returns, with its HTTP status, meaning and usual fix, plus chat turn errors, MCP errors and CLI exit codes.
---

# Error codes

This page lists every error code Coffer can return: the management API's error codes with
their HTTP statuses, the codes a chat turn can fail with, the JSON-RPC errors the MCP
gateway returns, and the exit codes of the `coffer` CLI and the MCP shim. Use it to look up
a code you saw in a response, a log line or the web UI.

## The error envelope

Every management API error has the same body, and every error response carries an
`X-Coffer-Trace` header you can search the daemon log for:

```json
{
  "error": {
    "code": "CREDENTIAL_MISSING",
    "message": "credential not found in the credential store: mcp/jira/token",
    "details": {}
  }
}
```

`details` is empty unless the error has structured context: `reason` (a short
machine-readable cause), `feature` (for `FEATURE_DISABLED`), or route-specific fields such
as `doc_type`. See the [REST API reference](/reference/rest-api#errors).

A code not listed in the daemon's status table falls back to HTTP `500`. The tables below
give the status each code is actually sent with.

## Request and framework errors

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `UNAUTHENTICATED` | 401 | The `X-Coffer-Token` header is missing or wrong. | Read the current token from `~/.coffer/daemon.json`; it changes on every daemon start and on `coffer daemon rotate-token`. |
| `DAEMON_NOT_READY` | 503 | The daemon has no active token yet; it is still starting. | Retry after a moment. |
| `HOST_NOT_LOOPBACK` | 421 | The request's `Host` header does not name a loopback address. Defends against DNS rebinding. | Call `127.0.0.1` or `localhost` directly, not through a proxy or another hostname. |
| `BAD_REQUEST` | 400 | A route rejected the request (for example an invalid `X-Coffer-Actor` value or malformed JSON on `/mcp`). | Read `message`; fix the request. |
| `NOT_FOUND` | 404 | No such route or object, raised by a route rather than a domain error. | Check the path against the [REST API reference](/reference/rest-api). |
| `FORBIDDEN` | 403 | The route refuses the operation. | Read `message`. |
| `CONFIG_INVALID` | 422 | The request body or query failed validation, or a resource's config is invalid. The submitted values are not echoed back. | Compare the body with the route's schema at `/api/v1/openapi.json`. |
| `INTERNAL_ERROR` | 500 | An unexpected failure. The full traceback is in the daemon log under the response's trace id. | Run `grep <trace-id> ~/.coffer/logs/daemon.log`, or ask your agent to call `coffer__diagnose`. |
| `HTTP_<status>` | as named | A bare HTTP error with a status that has no named code. | Read `message`. |

## Resources and scope

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `RESOURCE_NOT_FOUND` | 404 | Nothing answers to the uid or name you gave. | Check the name with `coffer resource list`; names are unique only within a kind. |
| `RESOURCE_ALREADY_EXISTS` | 409 | A resource of that kind already has that name. | Pick another name, or edit the existing resource. |
| `UNKNOWN_KIND` | 400 | The kind is not one this daemon registers. | Use a kind from `coffer resource list`, such as `mcp_server`, `skill` or `agent`. |
| `GENERIC_CREATE_NOT_ALLOWED` | 409 | This kind cannot be created or updated through the generic `/resources` endpoints. | Use the kind's own endpoint or command (for example `coffer agent add`, `coffer provider add`). |
| `SCOPE_INVALID` | 422 | A reach (activation scope) payload is invalid, or the kind has no reach. | Send an agent allow-list, or use `coffer scope set` on a kind that supports it. See [reach](/architecture/resource-framework#reach). |
| `RESOURCE_PROTECTED` | 409 | The resource is managed by Coffer itself (for example a skill Coffer generates) and cannot be taken over or deleted. | Leave it; Coffer maintains it. |
| `UPKEEP_ALREADY_RUNNING` | 409 | An upkeep pass (memory organising, knowledge curation) is already running for this target. | Wait for the running pass; the UI shows it. |
| `UNKNOWN_PRUNABLE_TABLE` | 404 | A retention request named a table that has no retention policy. | List valid tables with `coffer retention list`. |

## Credentials

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `CREDENTIAL_MISSING` | 400 | No secret is stored under the referenced credential ref. | Store it: `coffer credentials set <ref>`, or re-enter it in the resource's form. |
| `CREDENTIAL_IN_USE` | 409 | The credential cannot be deleted while a resource still references it. The message names the resources. | Detach or delete those resources first. |
| `CREDENTIAL_LOCKED` | 503 | The OS keychain is locked or unavailable, or a keychain write could not be verified. | Unlock the keychain (log in to the desktop session) and retry. |
| `CREDENTIAL_UNREADABLE` | 500 | A stored secret cannot be decrypted with the current master key. | Restore the matching master key, or re-enter the secret. See [Credentials](/guides/credentials). |
| `MASTER_KEY_MISSING` | 503 | Encrypted credentials exist but the master key is in neither the key file nor the keychain. Raised while the daemon starts. | Restore `master.key` beside the database (or import it with `coffer sync key import`), or re-enter your secrets. |
| `MASTER_KEY_FILE_INVALID` | 422 | A master-key file to import is missing or is not a valid key. | Point the import at the exported key file. |

## MCP servers and the gateway

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `UPSTREAM_UNAVAILABLE` | 503 | The upstream MCP server could not be reached, is disabled, or does not support the method. | Run `coffer mcp test <name>`; check the server's command or URL and its credentials. |
| `UPSTREAM_TIMEOUT` | 504 | The upstream MCP server did not answer in time. | Check the server; retry. |
| `TOOL_DISABLED` | 403 | The tool, resource or prompt is switched off on its server, the server is outside the calling agent's reach, or the name is not recognised. | Enable it with `coffer mcp tool enable`, or widen the server's reach. |
| `INVALID_PREFIX` | 400 | A name is not in Coffer's namespaced form (`<server>__<tool>`, `coffer://<server>/<uri>`). | Use the name exactly as `tools/list` or `coffer__search_tools` returned it. See [MCP tools](/reference/mcp-tools#upstream-names). |

## Agents and agent workspaces

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `AGENT_CONFIG_DIR_REGISTERED` | 409 | An agent is already registered for this config directory. | Use the existing agent, or register a different config dir. |
| `AGENT_CONFIG_DIR_MISSING` | 409 | The agent's config directory does not exist on this machine. Raised while applying a synced agent. | Install the agent on this machine, or ignore it here. |
| `PRIVILEGED_PATH` | 422 | The path is a system location Coffer refuses to manage. | Choose a path in your home directory. |
| `SKILL_DIR_NOT_WRITABLE` | 422 | The agent's skills directory is missing, not a directory, or not writable. `details.reason` says which. | Create the directory or fix its permissions. |
| `CONFIG_FILE_NOT_ALLOWED` | 404 | The config-file key is not one Coffer edits for this agent type. | Use a key from `coffer agent config ls <agent>`. |
| `CONFIG_FILE_FORMAT_INVALID` | 422 | The new content is malformed JSON or TOML. The file on disk is unchanged. | Fix the syntax and save again. |
| `CONFIG_FILE_STALE` | 409 | The config file changed on disk after you read it. | Reload the file and reapply your edit. |
| `AGENT_CONFIG_PARSE_ERROR` | 422 | An agent config file on disk cannot be parsed. | Repair the file in your editor. |
| `SHIM_NOT_FOUND` | 422 | The `coffer-mcp-shim` binary could not be found on `PATH` or in the bundled location. | Reinstall Coffer so `~/.coffer/bin` holds the shim. See [Install](/start/install). |
| `MCP_INSTALL_UNSUPPORTED` | 422 | This agent type has no place to install Coffer's MCP entry. | Connect the client by hand; see [Connect a client](/guides/connect-a-client). |
| `MCP_ENTRY_NOT_FOUND` | 404 | No MCP entry with that name exists in the agent's config files. | Refresh the agent's MCP list. |
| `MCP_ENTRY_PROTECTED` | 422 | The entry is Coffer's own gateway entry. | Use the install and uninstall actions instead of editing it. |
| `MCP_ENTRY_SOURCE_AMBIGUOUS` | 422 | The entry exists in more than one config file. | Name the source file. |
| `ADOPT_SECRET_UNRESOLVED` | 422 | Adopting an MCP entry found secret-like environment keys with no credential mapping. | Map each listed key to a credential ref when adopting. |
| `PLUGIN_NOT_FOUND` | 404 | No installed plugin has that identifier. | Refresh the plugin list. |
| `PLUGIN_TOGGLE_UNSUPPORTED` | 422 | This agent type's plugins cannot be enabled or disabled through Coffer. | Use the agent's own tooling. |
| `PLUGIN_UNINSTALL_UNSUPPORTED` | 422 | This agent type's plugins must be uninstalled with the agent's own tooling. | Use the agent's own tooling. |
| `PLUGIN_UNINSTALL_FAILED` | 422 | The agent's own uninstall command failed. | Read `message`; run the uninstall yourself. |
| `FS_PATH_NOT_BROWSABLE` | 400 | A folder-picker path is missing, not a directory, or unreadable. | Pick another folder. |
| `FS_PATH_NOT_OPENABLE` | 400 | An open or reveal target is not absolute, does not exist, or the launch failed. | Check the path and the preferred editor setting. |

## Skills

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `SKILL_INVALID` | 422 | The skill folder is not a valid skill (for example a missing or malformed `SKILL.md`). | Fix the folder and import again. |
| `TARGET_CONFLICT` | 409 | Delivering a skill would overwrite something at the target path that Coffer did not put there. | Move the conflicting file or folder, then run `coffer skill verify --fix`. |
| `SKILL_FILE_STALE` | 409 | A skill file changed on disk after you read it. | Reload and reapply your edit. |
| `SKILL_OUT_OF_SCOPE` | 422 | The agent is outside the skill's reach, so the skill cannot be enabled for it. | Widen the skill's reach first. |
| `UNMANAGED_SKILL_NOT_FOUND` | 404 | No skill by that name was found in the agent's own skills folders. | Refresh the agent's skills list. |
| `UNMANAGED_SKILL_INVALID` | 422 | An agent's own skill cannot be adopted because its folder is invalid. | Fix its `SKILL.md`, then adopt. |

## Knowledge

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `KNOWLEDGE_COLLECTION_NOT_FOUND` | 404 | No collection by that name is visible to the caller. | List collections with `coffer knowledge collections`. |
| `KNOWLEDGE_COLLECTION_EXISTS` | 409 | A collection with that name already exists. | Choose another name. |
| `KNOWLEDGE_FILE_NOT_FOUND` | 404 | No document at that path. | Browse the collection with `coffer knowledge ls <collection>`. |
| `KNOWLEDGE_PATH_UNSAFE` | 400 | The path escapes the knowledge root, names a hidden entry, or cannot name a document. | Use a relative path to a Markdown document inside the collection. |
| `KNOWLEDGE_UPLOAD_TOO_LARGE` | 413 | The upload exceeds the size limit named in the message. | Split the document or upload a smaller file. |
| `INGEST_REJECTED` | 400 | The upload cannot be converted. `details.reason` is `unsupported_type`, `scanned_pdf` (a PDF with no text layer) or `empty_conversion`; `details.doc_type` names the type. | Convert to a supported format; run OCR on a scanned PDF. |
| `KNOWLEDGE_TOPIC_REFERENCES_FILE` | 400 | A curated document refers to another knowledge file by its file name. | Name the subject instead of the file. |
| `KNOWLEDGE_CURATION_BOUND` | 400 | A curation pass tried to write more files than one pass may. | Submit smaller material. |
| `KNOWLEDGE_ERROR` | 400 | Any other knowledge-layer refusal. | Read `message`. |
| `ENGINE_UNAVAILABLE` | 503 | A binary or converter the operation needs (ripgrep, or a document converter backend) is unavailable. | Reinstall Coffer; the bundled binaries include them. |
| `GREP_PATTERN_INVALID` | 400 | ripgrep rejected a pattern. | Fix the pattern. |

## Memory

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `MEMORY_NOTE_NOT_FOUND` | 404 | No note with that slug in the partition. | List notes on the partition's page. |
| `MEMORY_RAW_ENTRY_NOT_FOUND` | 404 | No raw entry with that id in the partition. | Refresh; the entry may have been distilled and removed. |
| `MEMORY_FILE_NOT_FOUND` | 404 | No readable file at that path inside the partition. | Browse the partition's files. |
| `MEMORY_UNSAFE_PATH` | 400 | A path segment is hidden, all dots, or otherwise unsafe. | Use a path inside the partition. |
| `MEMORY_UNREADABLE` | 422 | An agent's native memory file cannot be parsed. | Repair the file the message names. |
| `MEMORY_DELIVERY_UNSUPPORTED` | 422 | This agent type has no session-start hook Coffer can install. | None; memory reaches that agent through `coffer__recall` only. |
| `MEMORY_DELIVERY_CONFIG_INVALID` | 422 | The agent's settings or hooks file is not a JSON object Coffer can edit. | Repair the file, then install delivery again. |

## Chat and channels

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `CONVERSATION_NOT_FOUND` | 404 | No conversation with that id. | Refresh the conversation list. |
| `TURN_IN_PROGRESS` | 409 | The conversation already has a turn running. | Wait, or interrupt the running turn. |
| `UNKNOWN_AGENT` | 400 | No agent provider is registered for the conversation's agent. | Choose an agent from `GET /api/v1/agent-providers`. |
| `AGENT_CONFIG_REJECTED` | 400 | The agent rejected the conversation's config, for example an unknown model. `details.reason` is a short token such as `model_not_found`. | Pick a model the agent offers. |
| `MESSAGE_NOT_FOUND` | 404 | A resend named no user message of that conversation. | Refresh the conversation; retry the message shown there. |
| `ATTACHMENT_EXPIRED` | 410 | A message being sent again (Retry) carried a file the 30-day media sweep has since deleted; nothing was sent. | Attach the file again and send a new message. |
| `CHANNEL_NOT_PAIRED` | 409 | The channel has no paired chat to send to. | Pair it: `coffer channel pair <name>`. See [Channels](/guides/channels). |
| `CHANNEL_NOT_RUNNING` | 409 | The channel's adapter is not running (disabled or still starting). | Enable the channel and wait for it to connect. |
| `CHANNEL_SEND_FAILED` | 502 | The messaging platform refused or failed the send. | Read `message`; check the bot's token and permissions. |

## Model providers

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `PROVIDER_CREDENTIAL_SOURCE_INVALID` | 422 | A new connection must supply exactly one of a secret value or a credential ref. | Pass `--secret` or `--credential-ref`, not both. |
| `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE` | 409 | A connection's wire format cannot change while it is switched on. | Run `coffer provider use-builtin <wire>`, edit, then switch again. |
| `PROVIDER_INTERNAL_ONLY` | 409 | An `ollama` connection is for Coffer's internal engine only and cannot be switched on for an agent. | Use it as the internal-engine default instead. |
| `PROVIDER_INTERNAL_DEFAULT_TAKEN` | 409 | Another connection is already the internal-engine default. | Move the flag with `coffer provider internal-default <name>`. |
| `NO_ACTIVE_PROVIDER` | 404 | No connection is active for the requested wire format. | Switch one on with `coffer provider switch <name>`. |

## Vault sync

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `BACKUP_REMOTE_INVALID` | 422 | The sync remote's configuration cannot be used as given. | Correct the remote URL or token. See [Vault sync](/guides/vault-sync). |
| `GIT_MIRROR_FAILED` | 502 | A git operation against the remote failed. The message is redacted. | Check network access, the remote URL and the token's permissions. |
| `SYNC_BUNDLE_TOO_NEW` | 409 | The remote was written by a newer Coffer build. | Upgrade Coffer on this machine. |
| `SYNC_BUNDLE_INVALID` | 422 | The sync working tree cannot hold the vault's layout. | Point the remote at an empty repository or one Coffer wrote. |
| `SYNC_SERIALIZATION_INVALID` | 422 | A document in the sync tree is malformed. | Fix or remove the document the message names in the remote. |
| `SYNC_NOTHING_PENDING` | 409 | You confirmed or rejected, but no round is waiting at the deletion guard. | Nothing to do. |
| `SYNC_NOTHING_TO_ROLL_BACK` | 409 | There is no pre-apply snapshot to return to. | Nothing to do. |
| `SYNC_JOIN_AMBIGUOUS` | 409 | This machine synced with the remote before, but its last commit is gone from the remote's history. | Rebuild this machine from the remote, or join as new. |
| `SYNC_CANNOT_RETIRE_SELF` | 422 | You tried to retire the machine you are on. | Retire it from another machine, or clear the sync remote here. |

## Experimental features

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `FEATURE_DISABLED` | 404 | The route or resource belongs to an experimental feature that is switched off on this machine. `details.feature` names it. | `coffer daemon features enable <feature>`. See [Experimental features](/guides/experimental-features). |
| `FEATURE_UNKNOWN` | 404 | The key is not an experimental feature. | List keys with `coffer daemon features list`. |
| `FEATURE_PINNED` | 409 | `COFFER_FEATURES` pins this feature for the daemon's lifetime. | Change `COFFER_FEATURES` and restart the daemon. |

## Startup errors

These are raised while the daemon starts, before it serves requests. They appear in
`~/.coffer/logs/daemon.log` and in the output of `coffer daemon start`.

| Code | Meaning | Typical fix |
| --- | --- | --- |
| `DB_SCHEMA_TOO_NEW` | `~/.coffer/coffer.db` was migrated by a newer or different Coffer build. Mapped to HTTP 409 if it ever reaches a response. | Upgrade Coffer, or restore a pre-migration backup of the database. See [Files and directories](/reference/filesystem). |
| `MASTER_KEY_MISSING` | See [Credentials](#credentials). | |

## Chat turn errors

A chat turn that fails ends with a `turn_error` event on the conversation's event stream,
not an HTTP error. Its `code` is one of:

| Code | Meaning |
| --- | --- |
| `stream_ended` | The agent stopped responding before finishing the turn: its process died or its connection dropped. |
| `turn_timeout` | The agent produced no event for the idle window, so the turn was cancelled and the agent process stopped. The partial reply is kept. The window is set by `COFFER_TURN_IDLE_TIMEOUT_SECONDS` ([Configuration](/reference/configuration)). |
| `daemon_stopped` | Coffer stopped before the turn finished. |
| `empty_prompt` | There was no user message to send. |
| `sdk_connect_error`, `sdk_stream_error`, `sdk_error` | Claude Code could not start, its stream failed, or it reported an error. The message says which. |
| `codex_connect_error`, `codex_stream_error`, `codex_error` | The same for Codex. |
| `INTERNAL_ERROR` | An unexpected failure inside Coffer, including a queued turn that could not start. |

## MCP gateway errors

Calls through `/mcp` answer with JSON-RPC errors, not the envelope above.

| JSON-RPC code | Meaning |
| --- | --- |
| `-32600` | Invalid request: the body is not a JSON-RPC object, or has no `method`. |
| `-32000` | `TOOL_DISABLED`: the capability is switched off, outside the agent's reach, or not recognised. |
| `-32603` | Any other failure. A Coffer error carries its message; anything else is reported as `internal error: <ExceptionClass>` so no upstream content leaks. |

A built-in tool that fails returns an in-band result with `isError: true` instead; see
[MCP tools](/reference/mcp-tools#how-built-in-tools-answer).

## CLI exit codes

Every `coffer` command exits with one of these codes. HTTP errors from the daemon are
mapped by status.

| Exit code | Name | When |
| --- | --- | --- |
| `0` | OK | Success. |
| `1` | Generic | Any other failure, including `FEATURE_DISABLED` (which prints the command that switches the feature on). |
| `2` | Invalid usage | A bad argument or option combination. |
| `3` | Daemon unreachable | The daemon could not be started or stopped answering; the CLI suggests checking `~/.coffer/logs/daemon.log`. |
| `4` | Not found | The daemon answered `404`. |
| `5` | Conflict | The daemon answered `409`. |
| `6` | Invalid input | The daemon answered `400` or `422`. |
| `7` | Upstream test failed | `coffer mcp test` could not initialize the upstream server. |
| `8` | Credential issue | The error code was `CREDENTIAL_MISSING` or `CREDENTIAL_LOCKED`. |

Pass `--verbose` (`coffer -v …`) to print the full traceback and HTTP context on error.

## MCP shim exit codes

`coffer-mcp-shim` is the stdio bridge an agent launches.

| Exit code | When |
| --- | --- |
| `0` | Graceful exit: the agent closed stdin, or the shim received `SIGTERM`. |
| `1` | Uncaught fatal error. |
| `3` | The daemon was unreachable and could not be started. |

## Related

- [REST API reference](/reference/rest-api)
- [Troubleshooting](/guides/troubleshooting)
- [Observability](/architecture/observability) — trace ids, the daemon log and `coffer__diagnose`
