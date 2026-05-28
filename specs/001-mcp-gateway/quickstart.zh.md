# Quickstart — Coffer MCP Gateway

> English: [quickstart.md](./quickstart.md)

从 "我刚装好 Coffer" 到 "Claude Code 已经通过它在调用 filesystem 工具" 的 10 分钟路径。本文档是随功能交付的**面向用户**的 quickstart；想搭开发环境的开发者请参考 `CONTRIBUTING.md`。

本 quickstart 覆盖本 spec 当前所交付的 **CLI + shim** 安装路径。完整的桌面端流程（安装包 DMG / MSI / AppImage、GUI 表单、系统托盘）由计划中的 UI 规范（将作为 `002-ui-shell` 在后续 PR 中起草）承载；见底部的 [Future (planned in the UI spec)](#future-planned-in-the-ui-spec)。

## Prerequisites

- 已安装受支持的 MCP 客户端：Claude Code、Claude Desktop 或 Cursor
  （任意支持 stdio 或 HTTP MCP 服务器配置的版本均可）。
- 你想要使用的一个或多个 MCP 服务器。下面的演示使用公开的
  `@modelcontextprotocol/server-filesystem` 服务器，它需要 `npx`（Node.js 18+）。
- `coffer` CLI 与 `coffer-mcp-shim` 二进制位于你的 `PATH`。源码检出时：
  `pip install -e ./backend` 会把两者都作为 console-script 入口装到 `PATH`。
  或者使用 PyInstaller bundle（`make bundle-binaries`——见
  [ADR-007](../../docs/decisions/ADR-007-distribution-pyinstaller-tauri-sidecar.md)）：
  `dist/coffer-daemon` 与 `dist/coffer-mcp-shim` 是自包含可执行文件，
  放在任意 `PATH` 目录即可。

使用 PyInstaller bundle 时**不需要**系统 Python。

## First launch

启动 daemon：

```bash
coffer daemon start
```

首次启动时 Coffer 会：

1. 在 8000–8009 范围内挑一个空闲端口，写入 `~/.coffer/daemon.json`（mode `0600`），
   以便 CLI 与 shim 互相发现。
2. 在 `~/.coffer/coffer.db` 初始化 SQLite。
3. 写入默认保留策略（audit：365 天；invocations：30 天）。

验证 daemon 是否就绪：

```bash
coffer daemon status
# → status: ready
# → port:   8001
```

## Add your first MCP server

```bash
coffer mcp add filesystem \
  --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"
```

Coffer 会注册该服务器、启动它一次以发现能力，并列出发现的工具
（例如 `read_file`、`write_file`、`list_directory`）。

带凭据添加 HTTP MCP 服务器的方式相同：

```bash
coffer keychain set github-token "ghp_xxxxxxxxxxxx"
coffer mcp add github --http https://api.github.com/mcp \
  --credential "Authorization=Bearer ${github-token}"
```

（凭据存放在 OS keychain；coffer 配置里仅持有 keychain 的引用。）

## Wire Coffer into your MCP client

### Claude Code / Claude Desktop / 任何支持 stdio MCP 的客户端

编辑你客户端的 MCP 配置文件（位置因客户端而异；对 Claude Code 来说是
`~/.claude/mcp.json` 或通过 `claude mcp add …`）：

```json
{
  "mcpServers": {
    "coffer": {
      "command": "coffer-mcp-shim"
    }
  }
}
```

如果二进制不在客户端的 `PATH`，请改成绝对路径。

重启客户端。

### 支持 HTTP MCP 的客户端

```json
{
  "mcpServers": {
    "coffer": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

（若 Coffer 选了别的端口——查看 `~/.coffer/daemon.json` 获取真实值——把这里换成对应的端口。）

## Verify it works

1. 在 MCP 客户端中列出可用工具。你应当看到每个启用的上游工具，都带有前缀：
   - `filesystem__read_file`
   - `filesystem__write_file`
   - `filesystem__list_directory`
   - ……
2. 让 AI 读取一个文件。它应当调用 `filesystem__read_file`。Coffer 会把该调用以原始名称路由到上游 filesystem 服务器。
3. 运行 `coffer mcp invocations filesystem`。你应当看到这次调用被记录，含时间戳、耗时和结果。

## Common tasks

### Disable a single tool

```bash
coffer mcp tool disable filesystem write_file
```

重启 MCP 客户端；被禁用的工具不再出现。

### Add a second MCP server

重复上面的步骤。客户端中的工具调用现在按各自服务器名带前缀——没有冲突。

### See what changed and when

```bash
coffer audit list --kind mcp_server --name filesystem
```

### Change how long logs are kept

```bash
coffer retention list
coffer retention set mcp_invocations --days 7
coffer retention set audit_log --forever
```

### Update a credential

```bash
coffer keychain set github-token "<new value>"
```

（无需更新服务器配置——它已通过 key 名称引用 keychain。）

## Troubleshooting

| Symptom                                    | Most likely cause    | Fix                                                                     |
| ------------------------------------------ | -------------------- | ----------------------------------------------------------------------- |
| 客户端报 `Cannot connect to coffer daemon` | daemon 未运行        | `coffer daemon start`                                                   |
| `command not found: coffer-mcp-shim`       | PATH 未更新          | 使用二进制的绝对路径，或把它所在目录加入你的 `PATH`。                   |
| 服务器已注册但 capabilities 为空           | 上游 initialize 失败 | `~/.coffer/logs/upstream-<name>.log` 含上游 stderr。                    |
| `CREDENTIAL_LOCKED` 错误                   | OS keychain 已锁     | 解锁 keychain（macOS：登录 GUI；Linux：解锁 GNOME-keyring / KWallet）。 |
| 被禁用的工具仍在客户端中出现               | 客户端缓存了工具列表 | 重启客户端，或寻找 "reload MCP servers" 选项。                          |
| `no free port in 8000-8009 range`          | 10 个端口都被占用    | 杀掉占用进程，再 `coffer daemon start`。                                |

## Where things live

```text
~/.coffer/
├── coffer.db              # SQLite — your config, audit, invocation log
├── coffer.db-wal          # WAL
├── coffer.db-shm          # WAL shared memory
├── daemon.json            # daemon discovery: pid + port + token (mode 0600)
├── logs/
│   ├── daemon.log         # structured JSON, one line per event
│   └── upstream-<name>.log
├── backups/               # 由 `coffer daemon backup` 产出
└── upstream-pids/         # for orphan-subprocess cleanup
```

要做一份干净的备份，运行 `coffer daemon backup`（WAL 模式下文件拷贝是安全的；SQLite 的 online-backup API 会处理一致性）。

## Future (planned in the UI spec)

下列内容**不**由 spec `001-mcp-gateway` 交付；它们由计划中的 UI 规范
（将作为 `002-ui-shell` 在后续 PR 中起草）承载：

- 单一桌面安装包（DMG / MSI / AppImage / deb）。
- 用于添加 / 列出 / 筛选 MCP 服务器，浏览 audit、查看 invocation、配置
  retention 的桌面 UI。
- 系统托盘、关闭即收起到托盘、开机自启。
- macOS Gatekeeper / Notarisation 的处理与首次启动流程。
- 首次安装的可发现性流程。
