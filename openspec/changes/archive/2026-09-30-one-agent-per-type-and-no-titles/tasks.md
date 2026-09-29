## 1. Resource framework

- [x] 1.1 `Kind.name_from_config` and `Kind.titled`; `register` refuses a name other than the derived one and a title on an untitled kind; `set_title` refuses it too
- [x] 1.2 `NameImmutable` says a derived name is the type; the "set a title instead" hint is gone
- [x] 1.3 The sync applier ignores a title an older document carries for an untitled kind
- [x] 1.4 Rename the title requirement and update its citations

## 2. Agents

- [x] 2.1 The agent kind derives its name from the type, fixes it and carries no title
- [x] 2.2 `AgentService.register(agent_type, config_dir, create_config_dir)`: one per type (`AGENT_TYPE_REGISTERED`), no name or description; `find_by_type`, `resolve`
- [x] 2.3 `AutoDetectService.types()` per type, `discover()` at most one candidate per type, `installed_never_run` addable, the env-var directory as `other_config_dir`
- [x] 2.4 Routes: `AgentCreate {type, config_dir}`, `AgentPatch` without description, `AgentOut` without title/description and with `display_name`, `GET /agents/types`, reshaped candidates; the standard directory created for `installed_never_run`
- [x] 2.5 `resolve_agent_path` on every agent router: the type stands for the uid
- [x] 2.6 CLI: `coffer agent add <type> [--config-dir]`, `edit <type>` without name/title/description, list/show by type and display name; the resolver normalises `claude_code`; `coffer scan` agent rows
- [x] 2.7 Attention and reconcile subjects label an agent by its product name
- [x] 2.8 The model catalogue and chat turns answer from the type's one agent (docstrings and citations)

## 3. MCP servers and skills

- [x] 3.1 `mcp_server` and `skill` kinds carry no title; `SkillOut` loses `title`; MCP attention uses the name
- [x] 3.2 CLI: no `--title` on `coffer mcp add|edit` or `coffer skill add`; `coffer skill edit` removed and listed in `check_removed_commands.py`

## 4. Migration

- [x] 4.1 `0108`: collapse agents to one per type (connected → enabled → most recently used → standard directory → oldest), re-point reach lists and channel defaults, drop the duplicates' skill bindings, rename to the type, clear agent descriptions and the three kinds' titles, log each dropped agent
- [x] 4.2 Migration tests and `HEAD_REVISION`

## 5. Contracts, frontend, tests, docs

- [x] 5.1 `make contracts`
- [x] 5.2 Frontend compile and test fixes: add/edit agent forms without name, title, description; no title editor on MCP server and skill pages
- [x] 5.3 Backend tests updated and acceptance markers for the new and changed scenarios
- [x] 5.4 Docs: agents, MCP servers and skills guides; CLI, REST and error-code references; architecture pages; the two ADRs rewritten
- [x] 5.5 `make verify`
