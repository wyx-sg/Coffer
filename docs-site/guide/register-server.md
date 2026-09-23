# Register a Server

Once the daemon is running, you can register upstream MCP servers with the `coffer mcp add` command. Registered servers are immediately available to any connected client through the shim.

## Quickstart

Register your first MCP server — using `@modelcontextprotocol/server-filesystem` as the example:

```bash
coffer mcp add filesystem \
  --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"

coffer mcp list                   # → filesystem  | stdio | enabled
coffer mcp tool list filesystem   # → read_file, write_file, list_directory, …
```

- `coffer mcp add` registers the server and stores its transport configuration. The `--stdio` flag tells Coffer to launch the server as a subprocess using the given command.
- `coffer mcp list` shows all registered servers and their current status.
- `coffer mcp tool list <name>` queries the live server and lists the tools it exposes.

The server name (`filesystem` in this example) becomes the namespace prefix that clients use to call its tools — for example, `filesystem__read_file`. Registering a second server adds its tools under its own prefix, so names never collide.

## HTTP servers and credentials

Pass `--http` instead of `--stdio` for a server reached over HTTP. When a server needs a secret, store the secret first and hand `mcp add` its **reference**:

```bash
printf 'ghp_xxxxxxxxxxxx' | coffer credentials set github-token
coffer mcp add github --http https://api.github.com/mcp \
  --credential "Authorization=github-token"
```

`--credential ENV_OR_HEADER=CREDENTIAL_REF` is repeatable. It names the environment variable (stdio) or header (HTTP) the secret goes into; Coffer resolves the value only when it connects, and only the reference is stored with the server. To rotate the secret later, run `coffer credentials set github-token` again — the server keeps pointing at the same reference. See [Credentials](./credentials).

## Inspect and maintain a server

```bash
coffer mcp show filesystem          # status plus the discovered tools, resources and prompts
coffer mcp test filesystem          # health-test the upstream
coffer mcp refresh filesystem       # re-discover after an upstream upgrade
coffer mcp remove filesystem        # delete the registration
```

Registration does not start anything; discovery happens the first time a client or command asks for the server's capabilities.

## Turn individual capabilities off

Every tool, resource and prompt a server exposes is enabled when first discovered. Switch off the ones you don't want an agent to see:

```bash
coffer mcp tool disable filesystem write_file
coffer mcp tool enable filesystem write_file
```

`coffer mcp resource …` and `coffer mcp prompt …` take the same `list`, `enable` and `disable` subcommands. A disabled tool disappears from every client's next tool list, and a call to it fails with `TOOL_DISABLED`. Your choices survive daemon restarts and upstream upgrades. If a client still shows a disabled tool, it cached its tool list — restart it or use its "reload MCP servers" option.

## See what was called

```bash
coffer mcp invocations filesystem              # latest 20 calls
coffer mcp invocations filesystem --status error --since 2026-09-01T00:00:00Z
```

Each entry records the target, time, duration and outcome — never the call's arguments or results. Entries are kept for 30 days by default; `coffer retention` changes that, and the [Activity](./activity) page shows the same log in the app.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Server registered but no capabilities | The upstream failed to start | Read its stderr in `~/.coffer/logs/upstream/<name>.log`. |
| The app shows the server as `missing <runner>` | The launcher (e.g. `uvx`, `npx`) is not installed on this machine | Install the named command; Coffer does not install it for you. |
| `CREDENTIAL_LOCKED` | The OS keychain holding the master key is locked | Unlock the keychain. See [Credentials](./credentials). |

[Connect a client →](/guide/connect-client)
