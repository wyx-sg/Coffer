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
    "code": "SECRET_MISSING",
    "message": "secret not found in the secret store: mcp/jira/token",
    "details": {}
  }
}
```

`details` is empty unless the error has structured context: `reason` (a short
machine-readable cause), `feature` (for `FEATURE_DISABLED`), or route-specific fields such
as `doc_type`.

A code not listed in the daemon's status table falls back to HTTP `500`. The tables below
give the status each code is actually sent with.

## Request and framework errors

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `UNAUTHENTICATED` | 401 | The `X-Coffer-Token` header is missing or wrong. | Read the current token from `~/.coffer/daemon.json`; it changes on every daemon start and when you rotate it on **Settings › Security**. |
| `DAEMON_NOT_READY` | 503 | The daemon has no active token yet; it is still starting. | Retry after a moment. |
| `HOST_NOT_ALLOWED` | 403 | The request's `Host` header does not name `127.0.0.1`, `localhost` or `[::1]` with the daemon's port. Defends against DNS rebinding. | Call `127.0.0.1:<port>` or `localhost:<port>` directly, not through a proxy or another hostname. |
| `ORIGIN_NOT_ALLOWED` | 403 | The request carries an `Origin` that is not one of Coffer's own: the daemon's web origin, the desktop app, or an opted-in dev origin. Defends against requests from other sites. | Open the UI from the daemon or the desktop app. To serve it from a dev origin, start the daemon with `COFFER_DEV_CORS=1` or list the origin in `COFFER_CORS_ORIGINS`. |
| `BAD_REQUEST` | 400 | A route rejected the request (for example an invalid `X-Coffer-Actor` value or malformed JSON on `/mcp`). | Read `message`; fix the request. |
| `CURSOR_INVALID` | 400 | A `cursor` sent to a paged list (the audit log, the MCP invocation log, an agent's native sessions, the chat conversations) does not decode, or was issued for another list or with other filters. | Drop `cursor` to read the first page again, or send the `next_cursor` the same list and filters returned. |
| `NOT_FOUND` | 404 | No such route or object, raised by a route rather than a domain error. | Check the path; the daemon serves its live route list at `/api/v1/openapi.json` to a caller with the token. |
| `FORBIDDEN` | 403 | The route refuses the operation. | Read `message`. |
| `CONFIG_INVALID` | 422 | The request body or query failed validation, or a resource's config is invalid. The submitted values are not echoed back. | Compare the body with the route's schema at `/api/v1/openapi.json` (send the token). |
| `INTERNAL_ERROR` | 500 | An unexpected failure. The full traceback is in the daemon log under the response's trace id. | Run `grep <trace-id> ~/.coffer/logs/daemon.log`, or run `coffer log daemon --errors`. |
| `HTTP_<status>` | as named | A bare HTTP error with a status that has no named code. | Read `message`. |

## Resources and scope

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `RESOURCE_NOT_FOUND` | 404 | Nothing answers to the uid or name you gave. | Check the name on the kind's page; names are unique only within a kind. |
| `RESOURCE_ALREADY_EXISTS` | 409 | A resource of that kind already has that name. | Pick another name, or edit the existing resource. |
| `UNKNOWN_KIND` | 400 | The kind is not one this daemon registers. | Use a registered kind, such as `mcp_server`, `skill` or `agent`. |
| `GENERIC_CREATE_NOT_ALLOWED` | 409 | This kind cannot be created or updated through the generic `/resources` endpoints. | Use the kind's own endpoint or its page in the web UI. |
| `NAME_IMMUTABLE` | 409 | The resource's kind fixes its name once registered, because agents quote it: an MCP server's name prefixes its tool names, and a skill's name is its folder. An agent's name is its type and cannot change at all. The message names what a re-registration resets. | Delete the MCP server or skill and register it again under the new name. |
| `SCOPE_INVALID` | 422 | A reach (activation scope) payload is invalid, or the kind has no reach. | Send an agent allow-list, or set the reach from the page of a kind that supports it. See [reach](/architecture/resource-framework#reach). |
| `RESOURCE_PROTECTED` | 409 | The resource is managed by Coffer itself (for example a skill Coffer generates) and cannot be taken over or deleted. | Leave it; Coffer maintains it. |
| `RESOURCE_NOT_TOGGLEABLE` | 409 | The resource's kind cannot be enabled or disabled: every knowledge collection and memory partition is always served. | Delete the resource if it should no longer be served. |
| `UPKEEP_ALREADY_RUNNING` | 409 | An upkeep pass (aggregate or distil) is already running for this memory partition; clearing the derived cache while one runs gets it too. | Wait for the running pass to finish; `coffer daemon status` and the UI show it. |
| `UNKNOWN_PRUNABLE_TABLE` | 404 | A retention request named a table that has no retention policy. | Use a table listed in **Settings → Data**. |
| `ATTENTION_NOT_IGNORABLE` | 409 | The key names no attention item that can be ignored: nothing is listed under it, or the item is a failure rather than a notice. | Refresh the attention list; fix a failure instead of ignoring it. |

## Secrets

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `SECRET_MISSING` | 400 | No secret is stored under the referenced secret ref. | Store it: `coffer secret set <ref>`, or re-enter it in the resource's form. |
| `SECRET_IN_USE` | 409 | The secret cannot be deleted while a resource still references it. The message names the resources. | Detach or delete those resources first. |
| `SECRET_LOCKED` | 503 | The OS keychain is locked or unavailable, or a keychain write could not be verified. | Unlock the keychain (log in to the desktop session) and retry. |
| `SECRET_UNREADABLE` | 500 | A stored secret cannot be decrypted with the current master key. | Restore the matching master key, or re-enter the secret. See [Secret store](/guides/secret-store). |
| `MASTER_KEY_MISSING` | 503 | Encrypted secrets exist but the master key is in neither the key file nor the keychain. Raised while the daemon starts. | Restore `~/.coffer/master.key`, or re-enter your secrets. |
| `MASTER_KEY_FILE_INVALID` | 422 | A master-key file to import is missing or is not a valid key, or a `.cfk` backup's fingerprint is not its key's. | Point the import at the key backup the desktop app wrote. |
| `MASTER_KEY_PASSPHRASE_WRONG` | 422 | A passphrase-protected key backup (`.cfk`) was imported with a wrong passphrase, or none. | Type the passphrase set when the key was exported on the other Mac. |
| `MASTER_KEY_PASSPHRASE_TOO_SHORT` | 422 | A key backup was asked for with a passphrase under eight characters. Nothing was written. | Choose a longer passphrase. |
| `SECRET_BINDING_PENDING` | 409 | A secret would go to a destination, or a target, no person has approved. Nothing was sent. `details.approval_ids` names the waiting approvals. | Run `coffer approval approve <id>` and confirm in the Coffer desktop app (or approve it there directly), or reject it with `coffer approval reject <id>` or in **Settings › Security** (**Review**). A custom tool's call answers it in band, naming the approval ids and the same command, for the environment that waits only. Also returned by `coffer run` for a standalone secret nobody has allowed it to use; see [Secrets → Allow `coffer run` to use it](/guides/secrets#allow-coffer-run-to-use-it). |
| `SECRET_BINDING_REJECTED` | 409 | A person refused this secret for this destination and target, and nothing waits. Nothing was sent. `details.approval_ids` names the refused approvals. | Change the destination to put the question afresh (for `coffer run`, ask again with **Allow `coffer run`…** on the secret). See [Secrets → Approvals](/guides/secrets#approvals). |
| `APPROVAL_NOT_FOUND` | 404 | No approval has that id. | List them with `coffer approval list` or in **Settings › Security** (**Review**). |
| `APPROVAL_NOT_PENDING` | 409 | The approval was already approved, rejected or superseded. | Nothing to do; a new change raises a new approval. |
| `PRESENCE_GRANT_INVALID` | 403 | A reveal, key backup, key import or approval came without a valid presence grant: missing, expired, already used, for another operation or target, or not signed by the desktop app. | Do it in the Coffer desktop app, which runs the presence check and signs the grant. |
| `APPROVAL_TARGET_CHANGED` | 409 | The approval now names another target than the one the person was shown: its destination moved between the presence prompt and the approve request. Nothing was approved; the grant was pinned to the old target. | Review the approval again (`coffer approval show <id>`) and approve it afresh if you recognise the new target. |
| `DESKTOP_REQUEST_NOT_FOUND` | 404 | No desktop request has that id: a command line request to the desktop app (approve, reveal, key backup, update) that never existed or has expired (requests last two minutes; a key backup's, ten). | Run the command again; keep the desktop app open while it waits. |
| `SECRET_NAME_INVALID` | 422 | A new standalone secret's ref is not `secret/<32 hex>`, or its label is over 64 characters or its description over 200. | Mint the secret with `coffer secret set --name "Orders DB"` and let Coffer choose the id; shorten the label or description. |
| `SECRET_NOT_FOUND` | 404 | `coffer run` named a standalone secret the store does not hold. Only `secret/<id>` values can be resolved this way; a resource's secret never can. | Check the id with `coffer secret list`, or mint the secret with `coffer secret set --name "<name>"`. |

## MCP servers and the gateway

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `UPSTREAM_UNAVAILABLE` | 503 | The upstream MCP server could not be reached, is disabled, or does not support the method. | Run `coffer mcp test <name>`; check the server's command or URL and its secrets. |
| `UPSTREAM_TIMEOUT` | 504 | The upstream MCP server did not answer in time. | Check the server; retry. |
| `TOOL_DISABLED` | 403 | The tool, resource or prompt is switched off on its server, the server is outside the calling agent's reach, or the name is not recognised. | Enable it on the **Tools** tab of the server's page, or widen the server's reach. |
| `INVALID_PREFIX` | 400 | A name is not in Coffer's namespaced form (`<server>__<tool>`, `coffer://<server>/<uri>`). | Use the name exactly as `tools/list` or `coffer__search_tools` returned it. See [MCP tools](/reference/mcp-tools#upstream-names). |

## Custom tools

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `NOT_A_CUSTOM_TOOL_GROUP` | 404 | The name belongs to an MCP server of another transport, not a custom-tool group. | Manage it on the **MCP servers** page, or list groups on **Custom tools**. |
| `CUSTOM_TOOL_NOT_FOUND` | 404 | The group has no tool of that name. | Open the group on **Custom tools** to list its tools. |
| `CUSTOM_TOOL_EXISTS` | 409 | The group already has a tool of that name. | Pick another name, or edit the existing tool. |
| `OPENAPI_UNREADABLE` | 422 | The OpenAPI document could not be fetched, parsed or read: not JSON or YAML (`details.line` and `details.column` say where it broke), not OpenAPI 3.x, larger than 5 MiB, or a URL on a loopback, private or link-local host. | Fix the document, or import a spec on a private host as a file. |
| `OPENAPI_UNREACHABLE` | 502 | The OpenAPI URL did not answer: its host name does not resolve, the connection was refused, or it timed out. `details.reason` is `dns`, `refused`, `timeout` or `unreachable`, and `details.handoff.prompt` is a prompt for your agent. | Check the URL, your network, VPN or proxy, or import the spec as a file. |
| `NOT_IMPORTED_FROM_OPENAPI` | 409 | Re-import was asked of a group whose tools were all added by hand. | Nothing to re-import; add tools by hand. |
| `OPENAPI_FILE_NEEDED` | 422 | The group was imported from a file, and re-import needs that file again. | Re-import from the group's page and give the file. |
| `CUSTOM_TOOL_ARGUMENTS_INVALID` | 422 | The call's arguments break the tool's JSON Schema. `details.errors` lists every failure as `{path, keyword, message}`. Nothing was sent upstream. On MCP the same list is an in-band tool error. | Fix each argument named; see [Custom tools → Arguments are checked before any request](/guides/custom-tools#arguments-are-checked-before-any-request). |
| `CUSTOM_TOOL_ENVIRONMENT_REQUIRED` | 422 | The group has more than one enabled environment and the call named none. `details.environments` lists the enabled ones. Nothing was sent. | Pass `coffer_environment` (on the command line, `--env`). See [Custom tools → Choosing the environment of a call](/guides/custom-tools#choosing-the-environment-of-a-call). |
| `CUSTOM_TOOL_ENVIRONMENT_UNKNOWN` | 422 | The call named an environment the group does not have. `details.environments` lists the enabled ones. Nothing was sent. | Use one of the names listed, exactly as `coffer custom-tool env list` prints it. |
| `CUSTOM_TOOL_ENVIRONMENT_DISABLED` | 422 | The call named an environment that is switched off. Nothing was sent. | Switch it on (`coffer custom-tool env enable`, or its switch under **Environments**), or call another. |
| `CUSTOM_TOOL_REQUEST_INVALID` | 422 | A preview (`--dry-run`) could not build the tool's request in the chosen environment: the tool uses an `{env:NAME}` that environment does not define, or its body template does not produce JSON. `details` names the group and environment. Nothing was sent. | Define the variable in that environment (`coffer custom-tool env set-var`), or fix the tool's template. |
| `CUSTOM_TOOL_ENVIRONMENT_NOT_FOUND` | 404 | A management request named an environment the group does not have. | List them with `coffer custom-tool env list` or on the group's page. |
| `CUSTOM_TOOL_ENVIRONMENT_EXISTS` | 409 | The group already has an environment of that name. | Pick another name, or change the existing environment. |
| `CUSTOM_TOOL_LAST_ENVIRONMENT` | 409 | Deleting the environment would leave the group with none. | Add another environment first, or delete the group. |

## Required CLIs

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `CLI_NOT_KNOWN` | 404 | No managed skill requires that command and no command-line tool was added under that name. | List the known commands on the **CLIs** page. |
| `CLI_TOOL_EXISTS` | 409 | A command-line tool with that name was already added. | Edit it on the **CLIs** page, or remove it first. |
| `CLI_TOOL_INVALID` | 400 | The command name, minimum version or login check is not valid. | Use a plain command name or an absolute path; read `message` for the field. |
| `CLI_TOOL_NOT_DECLARED` | 404 | That command-line tool was not added by hand, so it cannot be edited or removed. | A command a skill requires is changed in the skill, not here. |

## Agents and agent workspaces

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `AGENT_TYPE_REGISTERED` | 409 | An agent of this type is already registered. A machine has one agent per type, named by it. The message names the existing agent's uid. | Use the existing agent. To point it at another directory, change its config directory on the agent's page. |
| `AGENT_CONFIG_DIR_REGISTERED` | 409 | An agent is already registered for this config directory. | Use the existing agent, or choose a different config directory. |
| `AGENT_CONFIG_DIR_MISSING` | 409 | The agent's config directory does not exist on this machine. Raised while applying a synced agent. | Install the agent on this machine, or ignore it here. |
| `PRIVILEGED_PATH` | 422 | The path is a system location Coffer refuses to manage. | Choose a path in your home directory. |
| `SKILL_DIR_NOT_WRITABLE` | 422 | The agent's skills directory is missing, not a directory, or not writable. `details.reason` says which. | Create the directory or fix its permissions. |
| `CONFIG_FILE_NOT_ALLOWED` | 404 | The config-file key is not one Coffer edits for this agent type. | Use a key the agent's detail page lists (for example `settings` or `instructions`); the page names the files. |
| `CONFIG_FILE_FORMAT_INVALID` | 422 | The new content is malformed JSON or TOML. The file on disk is unchanged. | Fix the syntax and save again. |
| `CONFIG_FILE_STALE` | 409 | The config file changed on disk after you read it. | Reload the file and reapply your edit. |
| `AGENT_CONFIG_PARSE_ERROR` | 422 | An agent config file on disk cannot be parsed. | Repair the file in your editor. |
| `SHIM_NOT_FOUND` | 422 | The `coffer-mcp-shim` binary could not be found on `PATH` or in the bundled location. | Reinstall Coffer so `~/.coffer/bin` holds the shim. See [Install](/start/install). |
| `MCP_INSTALL_UNSUPPORTED` | 422 | This agent type has no place to install Coffer's MCP entry. | Connect the client by hand; see [Connect a client](/guides/connect-a-client). |
| `MCP_ENTRY_NOT_FOUND` | 404 | No MCP entry with that name exists in the agent's config files. | Refresh the agent's MCP list. |
| `MCP_ENTRY_PROTECTED` | 422 | The entry is Coffer's own gateway entry. | Use the install and uninstall actions instead of editing it. |
| `MCP_ENTRY_SOURCE_AMBIGUOUS` | 422 | The entry exists in more than one config file. | Name the source file. |
| `ADOPT_SECRET_UNRESOLVED` | 422 | Adopting an MCP entry found secret-like environment keys with no secret mapping. | Map each listed key to a secret ref when adopting. |
| `ADOPT_SECRET_REF_EXISTS` | 409 | Adopting an MCP entry mapped a secret key to a ref that already holds a value, or to a standalone `secret/<id>`. Adopting only creates refs. Nothing was written. | Map the key to a new ref, or delete the existing secret first if nothing uses it. |
| `PLUGIN_NOT_FOUND` | 404 | No installed plugin has that identifier. | Refresh the plugin list. |
| `PLUGIN_TOGGLE_UNSUPPORTED` | 422 | This agent type's plugins cannot be enabled or disabled through Coffer. | Use the agent's own tooling. |
| `PLUGIN_UNINSTALL_UNSUPPORTED` | 422 | This agent type's plugins must be uninstalled with the agent's own tooling. | Use the agent's own tooling. |
| `PLUGIN_UNINSTALL_FAILED` | 422 | The agent's own uninstall command failed. | Read `message`; run the uninstall yourself. |
| `FS_PATH_NOT_BROWSABLE` | 400 | A folder-picker path is missing, not a directory, or unreadable. | Pick another folder. |
| `FS_PATH_NOT_OPENABLE` | 400 | An open or reveal target is not absolute, does not exist, or the launch failed. | Check the path and the preferred editor setting. |
| `FS_TERMINAL_INVALID` | 400 | A request to open an agent session in a terminal cannot become a command: an unknown agent, a session id with characters other than letters, digits and dashes, a relative directory, both or neither of `resume` and `prompt`, or a terminal template without `{command}`. Nothing was started. | Fix the field `message` names; check the preferred terminal setting. |
| `FS_TERMINAL_FAILED` | 502 | The terminal could not be started: the launcher is not installed, would not start, or the host has no terminal to use. | Read `message`; pick another terminal in the preferred terminal setting. |
| `AGENT_TYPE_UNSUPPORTED` | 400 | This agent type has no native sessions Coffer can list, rename or delete. | None for this agent; open its sessions in the agent itself. |
| `NATIVE_SESSION_NOT_FOUND` | 404 | The agent lists no session with that id. Nothing changed. | Refresh the Sessions tab; the session may already be deleted. |
| `NATIVE_SESSION_INVALID` | 400 | The session id is not shaped like one, the new title is empty, or the agent refused the operation as malformed. Nothing changed. | Read `message`; pick a session from the list and give a non-empty title. |
| `NATIVE_SESSION_BUSY` | 409 | Another process has the session open for writing (a Codex App window, a terminal), so the agent refuses to rename or delete it. Nothing changed. | Close the session where it is open, then try again. |

## Skills

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `SKILL_INVALID` | 422 | The skill folder is not a valid skill (for example a missing or malformed `SKILL.md`). | Fix the folder and import again. |
| `UNMANAGED_SKILL_NOT_FOUND` | 404 | No skill by that name was found in the agent's own skills folders. | Refresh the agent's skills list. |
| `UNMANAGED_SKILL_INVALID` | 422 | An agent's own skill cannot be adopted because its folder is invalid. | Fix its `SKILL.md`, then adopt. |
| `SKILL_STAGING_NOT_FOUND` | 404 | Nothing is staged under that id: the import or update preview was confirmed, cancelled or expired (stages last an hour and do not survive a restart). | Stage the source again. |
| `SKILL_ORPHAN_NOT_FOUND` | 404 | No folder by that name in the skills store is outside your library. | Refresh the skills page. |
| `SKILL_COPY_NOT_OURS` | 409 | Deleting the skill found an agent's copy that is not Coffer's link, so the whole delete was refused and nothing changed. `details` name the folder and the agent. | Restore that copy from the master first, or delete the folder yourself. |
| `SKILL_COPY_NOT_DIFFERING` | 409 | Compare or resolve was asked for an agent's copy that is not a folder in the way of Coffer's link. | Nothing to compare; the agent already has the link, or nothing. |
| `SKILL_NOT_FROM_GIT` | 409 | The skill was not added from a Git repository, so it has no source to update from. | Re-add it from its repository with `--force` to replace it. |
| `SKILL_SOURCE_UNREACHABLE` | 502 | git could not fetch the skill's repository, resolve its ref or find its folder. The message is git's own, with any credential removed; with git missing, `details.handoff` is a prompt for your agent. | Check the repository URL, the ref and your access to it. |
| `SKILL_UPDATE_NOT_PENDING` | 409 | No update is waiting for the skill: "I merged it" named a commit that is not the update, or the update hand-off was asked for while the skill is up to date. | Check for updates; hand off or record only the update the skill offers. |

## Knowledge

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `KNOWLEDGE_COLLECTION_NOT_FOUND` | 404 | No collection by that name is visible to the caller. | Pick a collection from the Knowledge page. |
| `KNOWLEDGE_COLLECTION_EXISTS` | 409 | A collection with that name already exists. | Choose another name. |
| `KNOWLEDGE_FILE_NOT_FOUND` | 404 | No document at that path. | Browse the collection's folder on the Knowledge page. |
| `KNOWLEDGE_PATH_UNSAFE` | 400 | The path escapes the knowledge root, names a hidden entry, or cannot name a document. | Use a relative path to a Markdown document inside the collection. |
| `KNOWLEDGE_UPLOAD_TOO_LARGE` | 413 | The upload exceeds the size limit named in the message. | Split the document or upload a smaller file. |
| `INGEST_REJECTED` | 400 | The upload cannot be converted. `details.reason` is `unsupported_type`, `scanned_pdf` (a PDF with no text layer) or `empty_conversion`; `details.doc_type` names the type. | Convert to a supported format; run OCR on a scanned PDF. |
| `KNOWLEDGE_HISTORY_UNAVAILABLE` | 503 | Knowledge history is not recorded on this machine, usually because git is not installed. Writes still work. | Install git; history starts with the next write. |
| `KNOWLEDGE_NOT_A_DELETE` | 400 | The change you asked to restore deleted no document or collection. | Undo restores only a delete; restore an earlier version of a document from its **History** tab instead. |
| `KNOWLEDGE_RESTORE_CONFLICT` | 409 | Putting the deleted document back would overwrite the file now at its path. `details` name the version and the document; nothing was written. | Move or rename the file at that path, then restore again. |
| `KNOWLEDGE_ERROR` | 400 | Any other knowledge-layer refusal. | Read `message`. |
| `ENGINE_UNAVAILABLE` | 503 | A binary or converter the operation needs (ripgrep, or a document converter backend) is unavailable. | Reinstall Coffer; the bundled binaries include them. |

## Memory

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `MEMORY_NOTE_NOT_FOUND` | 404 | No note with that slug in the partition. | List notes on the partition's page. |
| `MEMORY_RAW_ENTRY_NOT_FOUND` | 404 | No raw entry with that id in the partition. | Refresh; the entry may have become a note and been removed. |
| `MEMORY_UNSAFE_PATH` | 400 | A path segment is hidden, all dots, or otherwise unsafe. | Use a path inside the partition. |
| `MEMORY_UNREADABLE` | 422 | An agent's native memory file cannot be parsed. | Repair the file the message names. |
| `MEMORY_DELIVERY_UNSUPPORTED` | 422 | This agent type has no memory hook Coffer can install. | None; that agent reads memory notes from the memory root the `coffer-guide` skill names, with its own file tools. |
| `MEMORY_DELIVERY_CONFIG_INVALID` | 422 | The agent's settings or hooks file is not a JSON object Coffer can edit. | Repair the file, then install delivery again. |

## Chat and channels

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `CONVERSATION_NOT_FOUND` | 404 | No conversation with that id. | Refresh the conversation list. |
| `UNKNOWN_AGENT` | 400 | No agent provider is registered for the conversation's agent. | Choose an agent from `GET /api/v1/agent-providers`. |
| `SESSION_IN_USE` | 409 | A turn would resume a session that is open in a terminal outside Coffer. Channels show this as a reply instead; the message is not retried. | Continue in that terminal, or send `/thread` to start a new conversation. |
| `AGENT_CONFIG_REJECTED` | 400 | The agent rejected the conversation's config, for example an unknown model, or no agent of that type is managed by Coffer. `details.reason` is a short token such as `model_not_found` or `agent_not_managed`. | Pick a model the agent offers, or add the agent on the Agents page. |
| `QUESTION_CLOSED` | 409 | An answer to a question the agent asked that is no longer waiting: it was already answered (the first answer wins), cancelled, or its turn ended. Nothing changed. | Refresh the conversation; the card shows the answer that was taken. |
| `QUESTION_ANSWER_INVALID` | 422 | An answer that does not fit its question: an option the question does not offer, several options on a single-choice question, or no answer at all. | Choose from the options, or type an answer. |
| `CHANNEL_NOT_PAIRED` | 409 | The channel has no paired chat to send to. | Pair it from the channel's page. See [Channels](/guides/channels). |
| `CHANNEL_PERSON_NOT_FOUND` | 404 | No paired person on the channel matches the one named. | List the people on the channel's page and use one of their ids. |
| `CHANNEL_NOT_RUNNING` | 409 | The channel's adapter is not running (disabled or still starting). | Enable the channel and wait for it to connect. |
| `CHANNEL_SEND_FAILED` | 502 | The messaging platform refused or failed the send. | Read `message`; check the bot's token and permissions. |

## Model providers

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `PROVIDER_SECRET_SOURCE_INVALID` | 422 | A new connection must supply exactly one of a secret value or a secret ref. | Pass `--secret` or `--secret-ref`, not both. |
| `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE` | 409 | A connection's wire format cannot change while an agent runs on it. | Switch each agent running on it back to its own login with **Change model**, edit, then switch again. |
| `PROVIDER_DOES_NOT_REACH_AGENT` | 409 | A connection cannot be switched on for an agent it does not reach: the connection is switched off, or the connection's scope does not name the agent. | Switch the connection on, or add the agent to its scope, then switch again. |
| `PROVIDER_PROTOCOL_RETIRED` | 422 | The `ollama` protocol is no longer offered: a connection cannot be created on it, edited onto it, or switched on for an agent. | Add a local Ollama runtime on its Anthropic or OpenAI wire instead, and delete the old connection. |
| `PROVIDER_TRANSCRIBE_DEFAULT_TAKEN` | 409 | Another connection is already the speech-to-text default. | Move the flag in **Settings › General → Speech to text**. |

## The vault

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `VAULT_FILE_STALE` | 409 | The file changed on disk since you read it (an edit in your editor, another save), so the write was refused rather than overwrite it. A restore is refused the same way when the file changed since its history was read. | Reload, then save again with the new fingerprint; for a restore, reopen the **History** tab and try again. |
| `VAULT_FILE_INVALID` | 422 | The write would leave a vault file that fails validation. Nothing was written. | Fix what the message names. |
| `VAULT_PATH_INVALID` | 400 | The path is not a vault file or folder history can be read for, or it is under `secret/`. | Use a vault-relative path such as `skills/pdf/`. |
| `VAULT_VERSION_NOT_FOUND` | 404 | The version is not in this file's history. | Pick one from the file's **History** tab. |
| `VAULT_GIT_FAILED` | 500 | A git operation on the vault repository failed. | Read the message and the daemon log. |

## Vault sync

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `SYNC_NO_REMOTE` | 409 | No sync remote is configured. | Set one on the **Sync** page (the **Remote** tab). See [Vault sync](/guides/vault-sync). |
| `SYNC_NO_PLAINTEXT_FOUND` | 409 | Push anyway was asked for, but the last round did not stop on a plaintext secret. | Nothing to override; run **Sync now**. See [Vault sync](/guides/vault-sync#when-a-round-finds-a-plaintext-secret). |
| `SYNC_PLAINTEXT_NOT_LISTED` | 404 | A plaintext finding's lines were asked for at a place the last round did not find. | Open a place from the Sync page's own list. |
| `SYNC_REMOTE_INVALID` | 422 | The URL or branch would be read by git as an option, or is not a name git accepts. | Correct the URL or branch. |
| `SYNC_REMOTE_FAILED` | 502 | A git operation against the remote failed. The message is redacted. | Check network access, the remote URL and the token's permissions. |
| `SYNC_NOTHING_STOPPED` | 409 | You answered a conflict, a hold or a join choice, but no round is waiting for that answer. | Nothing to do. |
| `SYNC_CONFLICT_MARKERS_LEFT` | 422 | The hand-merged copy still has conflict markers; the message names the line. | Remove them, save, then mark the file resolved. |
| `SYNC_SECRET_NOT_EDITABLE` | 422 | An encrypted secret in a stopped round or a join was opened in the editor, handed to an agent or answered as edited. | Keep this Mac's version or take the other's. |
| `SYNC_ROUND_NOT_FOUND` | 404 | No round with that id. | Pick one from the **Sync** page's history. |
| `SYNC_ROUND_FILE_NOT_LISTED` | 404 | The round did not apply or push that file. | Open a file from the round's own **Applied here** or **Pushed** list. |
| `SYNC_ROUND_DIFF_UNAVAILABLE` | 409 | The commits this round's diff is read from are no longer in the vault. | None; the round's file list is still accurate, only the line-by-line view is gone. |
| `SYNC_NOTHING_TO_ROLL_BACK` | 409 | The round applied nothing, or is itself a rollback. | Nothing to do. |
| `SYNC_MACHINE_NOT_FOUND` | 404 | No machine with that id shares this vault. | List them on the **Sync** page. |
| `SYNC_MACHINE_NAME_INVALID` | 422 | The machine name is empty or too long. | Choose another name. |
| `SYNC_CANNOT_RETIRE_SELF` | 422 | You tried to retire the machine you are on. | Retire it from another machine, or stop syncing here. |
| `SYNC_NOTHING_TO_RESTORE` | 409 | Undo was asked for a stopped sync or a retired machine, but nothing is kept, or another remote was set since. | Nothing to do; set the remote up again or join again. |
| `SYNC_REMOTE_EXISTS` | 409 | Stop syncing was undone while a remote is set. | Stop syncing first, or leave the remote as it is. |
| `SYNC_VAULT_TARGET_INVALID` | 422 | The folder to move the vault to is not an absolute path, is inside or around the current vault, or its parent cannot be written. | Choose another folder. |
| `SYNC_VAULT_TARGET_IN_CLOUD` | 422 | The folder to move the vault to is itself inside a folder another tool synchronises. | Choose a folder outside iCloud Drive, Dropbox and Syncthing. |
| `SYNC_VAULT_TARGET_NOT_EMPTY` | 409 | The folder to move the vault to already holds files. | Choose an empty or absent folder. |
| `SYNC_VAULT_MOVE_FAILED` | 500 | The move or the check of the vault at its new place failed; the vault is back where it was. | Read the daemon log for the cause, then try again. |

## The daemon

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `PORT_OUT_OF_RANGE` | 422 | The port is outside 1024-65535, so the daemon could never bind it. `details` carry the port and the range. | Choose a port in the range. |
| `PORT_IN_USE` | 409 | Another program holds the port. `details.holder` names it and its pid when Coffer can tell. | Stop that program, or choose another port. |

## Experimental features

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `FEATURE_DISABLED` | 404 | The route or resource belongs to an experimental feature that is switched off on this machine. `details.feature` names it. | Switch it on in **Settings → Features**. See [Experimental features](/guides/experimental-features). |
| `FEATURE_UNKNOWN` | 404 | The key is not an experimental feature. The keys are `knowledge`, `memory`, `sync` and `models`. | Use one of those four keys. |
| `FEATURE_PINNED` | 409 | `COFFER_FEATURES` pins this feature for the daemon's lifetime. | Change `COFFER_FEATURES` and restart the daemon. |

## Startup errors

These are raised while the daemon starts, before it serves requests. They appear in
`~/.coffer/logs/daemon.log` and in the output of `coffer daemon start`.

| Code | HTTP | Meaning | Typical fix |
| --- | --- | --- | --- |
| `DB_SCHEMA_TOO_NEW` | 409 | `~/.coffer/runs.db` was migrated by a newer or different Coffer build. The status applies if it ever reaches a response. | Upgrade Coffer, or restore a pre-migration backup of the database. See [Files and directories](/reference/filesystem). |
| `GIT_MISSING` | 500 | The vault needs `git` and none was found. A route that needs git answers with it too. | Install git the way that fits the machine; the error's `details.handoff` is a prompt for your agent. |
| `GIT_NEEDED` | 503 | The daemon is waiting for git: none was found, or it is older than 2.40. Every route that needs the vault answers with it; `details.reason` is `git_missing` or `git_too_old`, with `found`, `needed` and `handoff`. | Install or update git (the prompt in `details.handoff`), then press **Check again**. See [Coffer needs git](/guides/troubleshooting#coffer-needs-git). |

`MASTER_KEY_MISSING` can stop a start as well; see [Secrets](#secrets). A missing `git`, or one
older than 2.40, does not stop the daemon: it starts and waits for git, answering `GIT_NEEDED`.

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
[MCP tools](/reference/mcp-tools#how-built-in-tools-answer). So does a custom tool refused before any
request: its text starts with the code (`CUSTOM_TOOL_ARGUMENTS_INVALID` with one line per field,
`CUSTOM_TOOL_ENVIRONMENT_*`, `SECRET_MISSING`, or `SECRET_BINDING_PENDING` with the approval ids and
`next: coffer approval approve <id>`).

## CLI exit codes

Every `coffer` command exits with one of these codes. HTTP errors from the daemon are
mapped by status, and the daemon's error code passes through unchanged. With `--json`, a failure
is printed on standard error as `{"error": {"code", "message", "details"}, "exit_code"}`.

| Exit code | Name | When |
| --- | --- | --- |
| `0` | OK | Success. |
| `1` | Generic | Any other failure, including `FEATURE_DISABLED` (switch the feature on in **Settings → Features**). |
| `2` | Invalid usage | A bad argument or option combination. |
| `3` | Daemon unreachable | The daemon could not be started or stopped answering; the CLI suggests checking `~/.coffer/logs/daemon.log`. |
| `4` | Not found | The daemon answered `404`. |
| `5` | Conflict | The daemon answered `409`. |
| `6` | Invalid input | The daemon answered `400` or `422`, or the command's own input did not parse (`CLI_INVALID_INPUT`). A custom-tool test whose arguments break the schema exits here, with one error per field. |
| `7` | Upstream test failed | `coffer mcp test` could not initialize the upstream server, or a custom-tool test (`coffer custom-tool tool test`, `test-draft`, `test-unsaved`) reached an API that failed or answered with an error status. |
| `8` | Secret issue | The error code was `SECRET_MISSING`, `SECRET_LOCKED`, `SECRET_UNREADABLE` or `SECRET_BINDING_REJECTED`. |
| `9` | Waiting for approval | The change was saved but a secret in it waits for a person's approval (`SECRET_BINDING_PENDING`). The command printed the approval ids and `next: coffer approval approve <id>…` (with `--json`, `{"status": "pending_approval", "approval_ids", "next"}`). Do not retry: run that command, which asks the person in the desktop app, or approve it in the app. See [Secrets → On the command line](/guides/secrets#on-the-command-line). |
| `10` | Waiting for git | The daemon is running but waits for git: none was found, or it is older than 2.40. The command printed why and a prompt for your agent before sending anything. See [Coffer needs git](/guides/troubleshooting#coffer-needs-git). |
| `11` | Presence not confirmed | A step handed to the desktop app's presence check (`coffer approval approve`, `coffer secret reveal`, `coffer secret backup-key`) was cancelled, failed or timed out, or the daemon refused the grant (`PRESENCE_GRANT_INVALID`). Every approval stays pending. |
| `12` | Desktop app unavailable | The step needs the desktop app, which is not running and could not be started here (no app, not a Mac, or `--no-launch`): `CLI_APP_UNAVAILABLE`. Nothing was approved. Open the app and run the command again. |
| `13` | Wait timed out | A wait ended before the operation finished: `coffer sync wait` ran past its `--timeout` (`CLI_WAIT_TIMEOUT`). The round may still be running; check `coffer sync status`. |

### Codes the command line sets

Besides the daemon's codes, which pass through unchanged, a command names these failures it decides itself:

| Code | Exit code | Meaning |
| --- | --- | --- |
| `CLI_INVALID_INPUT` | `6` | The command's own input is not valid: `--data` or `--args` is not JSON, `@file` cannot be read, `--set` is not `key=value`, or a flag's value is malformed. Nothing was sent. |
| `CLI_APP_UNAVAILABLE` | `12` | The desktop app is not running and could not be started. |
| `CLI_WAIT_TIMEOUT` | `13` | `coffer sync wait` ran past its `--timeout` before the operation finished. |
| `CLI_DESKTOP_REQUEST_FAILED` | `1` | The desktop app could not carry out an update request (`coffer app update …`). |

Pass `--verbose` (`coffer -v …`) to add the request behind a refusal — method, path and status, never a header — as a line on standard error, or as a `request` object beside `error` with `--json`; an unexpected error also prints its traceback.

## MCP shim exit codes

`coffer-mcp-shim` is the stdio bridge an agent launches.

| Exit code | When |
| --- | --- |
| `0` | Graceful exit: the agent closed stdin, or the shim received `SIGTERM`. |
| `1` | Uncaught fatal error. |
| `3` | The daemon was unreachable and could not be started. |

## Related

- [Troubleshooting](/guides/troubleshooting)
- [Observability](/architecture/observability) — trace ids, the daemon log and `coffer log`
