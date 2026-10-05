---
title: Editing the vault by hand
description: Coffer's configuration and content are plain files in a git repository at ~/.coffer/vault — edit them in any editor, see what Coffer made of the edit, and read any version with git or have your agent bring one back.
---

# Editing the vault by hand

Everything Coffer keeps that you would want on another machine — MCP servers, skills, knowledge, providers, channels, their settings — is a plain file in `~/.coffer/vault`, and that directory is a git repository from the first time Coffer runs. This page is for anyone who wants to change those files directly, with an editor, a shell or an agent's own file tools, and to know what Coffer does with the change and how to undo it.

## What is in the vault

```text
~/.coffer/vault/
├── resources/<kind>/<name>.json        one file per MCP server, skill, channel, provider, knowledge collection
├── state/mcp-preferences/<server>.json the tools, prompts and resources you switched off on a server
├── state/channel-peers/<channel>.json  who is paired with a channel
├── state/settings/internal-engine.json speech-to-text model and upkeep settings
├── knowledge/<collection>/…            knowledge documents (Markdown)
├── skills/<name>/…                     skill folders (SKILL.md and the rest)
├── secret/<ref>.enc                    encrypted secrets (never edit these)
└── machines/<id>.json                  one descriptor per machine that syncs
```

Agents are not here: an agent's configuration is a fact about one machine, so it lives in `~/.coffer/local/resources/agent/`. Neither is reach (which agents may use a resource on this machine), which is in `~/.coffer/local/reach.json`. See [Files and directories](/reference/filesystem).

## Edit a file

Open it in any editor and save. A resource file is JSON:

```json
{
  "uid": "5f0c1e9a2b7d4c3e8a6f9b0d1c2e3f4a",
  "kind": "mcp_server",
  "format_version": 1,
  "name": "jira",
  "description": "Company Jira",
  "config": {
    "transport": {
      "type": "stdio",
      "command": "${HOME}/.local/bin/jira-mcp",
      "args": ["--verbose"]
    }
  }
}
```

Some rules to know:

- **Keep the `uid`.** It is the resource's identity. You can rename the file or move it within its kind's folder and it stays the same resource. A file you create with no `uid` gets one: Coffer writes it into the file in its own commit. A copy of a file with the same `uid` is refused and flagged; the original stays in effect.
- **`name` is a label**, but some kinds fix it once agents can see it (an MCP server's name is part of its tool names). Change a name through Coffer when it refuses a rename.
- **Unknown top-level fields are kept.** A field beside `uid`, `kind`, `name` and `config` that this build does not know is reported as a warning, never dropped, so a field a newer Coffer added survives your edit.
- **`config` holds only the settings the kind has.** A key the kind does not declare (a typo, or a setting Coffer has retired) is refused: the edit is not committed, the problem names the key, and the last valid version stays in effect. The same goes for a name the kind does not allow (an MCP server's name is at most 24 characters and has no `__`; a skill's name uses lowercase letters, digits and hyphens), and for a `title` on an MCP server, agent, skill, knowledge collection or memory partition, which have none.
- **`${HOME}`** stands for your home directory, so the same file works on every machine.
- **Never edit `secret/`.** The files are ciphertext; use the Secrets page (**Add secret**).

Knowledge documents and skill folders are ordinary files: edit, add, move and delete them as you would any Markdown.

## What happens when you save

Coffer notices the change, waits until the file has been quiet for a second (so an editor's burst of saves is one change), and checks it with the same rules an edit made through the web UI meets.

- **A valid edit is committed** as a version written by `disk` ("Edited on disk" in the UI), recorded in the audit log as `vault_file_edited` by a person, and takes effect: the reconciler re-projects what changed into your agents.
- **An invalid edit is not applied.** It stays in the file, uncommitted, and the last valid version stays in effect. It is flagged on the attention list and listed by:

  ```sh
  coffer vault problems
  ```

  Fix the file and save again, or restore the last version (below).

Coffer also scans the vault every minute and at startup, so an edit made while the daemon was stopped is picked up when it starts. What decides is the file's content, never its modification time.

While you are editing a file, Coffer does not overwrite it: a write Coffer itself makes to the same file is refused as stale (`VAULT_FILE_STALE`) rather than lost, and a sync round that would change it waits for you.

## History and restore

Every accepted change to the vault is a version with the time, who wrote it (you, edited on disk, an agent, Coffer or sync) and on which machine. Any file or folder has a history. Secrets have no readable history and cannot be restored.

In the web UI, a knowledge document's **⋯** menu and a skill's **⋯** menu (not the built-in skill's) have **History…**. It shows where the file sits in the vault, copies `git -C ~/.coffer/vault log -p -- <path>`, reveals the file, and hands the restore to your agent: **Hand off to &lt;Agent&gt; to restore**, with an optional time. Coffer builds the prompt — the file, the time, that the vault is a git repository whose history is never rewritten, and that the agent writes the earlier content back as one new commit — and shows no version list, diff or Restore button of its own.

For any other file, read the history with git itself and put an old version back by saving its content into the file, or ask your agent to:

```sh
cd ~/.coffer/vault
git log --oneline -- resources/mcp_server/jira.json
git diff <version> -- resources/mcp_server/jira.json
git show <version>:resources/mcp_server/jira.json > resources/mcp_server/jira.json
```

Coffer validates the saved file and records it as a **new** version, so nothing is rewritten in place and you can restore the restore. Make changes by editing files and let Coffer commit them: its commits carry the trailers that name the writer, and it validates what it commits. An agent that commits a restore itself names `Coffer-Writer: agent`, `Coffer-Operation: restore` and `Coffer-Restored-From: <commit>`, which is what the hand-off's prompt asks for.

## Related

- [Persistence](/architecture/persistence) for the writer model and the five storage classes
- [Vault sync](/guides/vault-sync) for carrying the vault to other machines
- [Skills](/guides/skills) · [Knowledge](/guides/knowledge) · [Files and directories](/reference/filesystem)
- Decision record: [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md)
