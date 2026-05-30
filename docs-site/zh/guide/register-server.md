# 注册服务器

守护进程启动后，你可以用 `coffer mcp add` 命令注册上游 MCP 服务器。注册完成后，通过 shim 接入的所有客户端都能立即使用这些服务器。

## 快速上手

注册你的第一个 MCP 服务器 —— 以 `@modelcontextprotocol/server-filesystem` 为例：

```bash
coffer mcp add filesystem \
  --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"

coffer mcp list                   # → filesystem  | stdio | enabled
coffer mcp tool list filesystem   # → read_file, write_file, list_directory, …
```

- `coffer mcp add` 注册服务器并存储其传输配置。`--stdio` 标志告诉 Coffer 使用给定的命令以子进程方式启动该服务器。
- `coffer mcp list` 显示所有已注册的服务器及其当前状态。
- `coffer mcp tool list <name>` 查询在线服务器并列出它所提供的工具。

服务器名称（本例中为 `filesystem`）会成为客户端调用其工具时使用的命名空间前缀，例如 `filesystem__read_file`。

[接入客户端 →](/zh/guide/connect-client)
