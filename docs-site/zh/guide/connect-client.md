# 接入 MCP 客户端

把 `coffer-mcp-shim` 配成 AI 客户端的 stdio MCP 服务器启动命令即可。shim 会自动发现守护进程（必要时自动拉起），无需手工配置端口或 token。

## Claude Code

```bash
claude mcp add coffer coffer-mcp-shim
```

## Codex

`~/.codex/config.toml`：

```toml
[mcp_servers.coffer]
command = "coffer-mcp-shim"
```

改完配置后重启客户端。工具名带命名空间，形如 `<server-name>__<tool-name>`（例如 `filesystem__read_file`）。

## Shim 的工作原理

MCP 客户端开启会话时，会以子进程方式启动 `coffer-mcp-shim`。shim 检查 `~/.coffer/daemon.json` 以定位正在运行的守护进程。如果守护进程未运行，shim 会自动拉起它。连接建立后，shim 将客户端的 `stdin/stdout` 转发到守护进程的 HTTP/SSE 端点，透明地完成 stdio MCP 协议与 HTTP 之间的转换。

因此，你在客户端只需一行配置，剩下的发现与连接工作全部由 shim 自动处理。
