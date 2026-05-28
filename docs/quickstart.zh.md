# Coffer 快速上手

> English: [quickstart.md](./quickstart.md)

5 分钟流程：从 `git clone` 到 Claude Code 通过 Coffer 调用工具。

---

## 1. 安装

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ./backend[dev]
```

这一步会把 `coffer` CLI 和 `coffer-mcp-shim` 入口点装进 venv。

---

## 2. 启动守护进程

```bash
coffer daemon start
```

守护进程 (daemon) 绑定到 `127.0.0.1` 上一个自动选择的端口，并把地址和 auth token 写入 `~/.coffer/daemon.json`。后续所有 `coffer` 命令都会自动读取这个文件。

```bash
coffer daemon status
# → status: running  port: 8000  version: 0.1.0
```

---

## 3. 注册一个 MCP 服务器

以官方的 filesystem 服务器作为具体示例：

```bash
coffer mcp add filesystem \
  --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"
```

Coffer 会拉起子进程、跑一遍能力发现 (capability discovery)，并把结果存下来。

```bash
coffer mcp list
# → filesystem  | stdio | enabled

coffer mcp test filesystem
# → OK (87 ms)

coffer mcp tool list filesystem
# → filesystem__read_file
# → filesystem__write_file
# → filesystem__list_directory
# → …
```

工具名带命名空间，形如 `<server-name>__<tool-name>`，因此多个上游服务器之间永远不会撞名。

---

## 4. 部署 shim

`coffer-mcp-shim` 这个可执行文件就是 MCP 客户端要对话的对象。把它部署到 `PATH` 上的某个目录：

```bash
coffer shim deploy
# → Deployed to /Users/you/.coffer/bin/coffer-mcp-shim

# One-time PATH setup (add to ~/.zshrc or ~/.bashrc):
export PATH="$HOME/.coffer/bin:$PATH"
```

如果你用的是 Tauri 桌面应用，shim 会在首次启动时自动部署。

---

## 5. 接入客户端

### Claude Code（最简单）

```bash
claude mcp add coffer coffer-mcp-shim
```

重启 Claude Code，然后让它："_List files in /tmp._"。它就会通过 Coffer 调用 `filesystem__list_directory`。

### Claude Desktop

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）：

```json
{
  "mcpServers": {
    "coffer": {
      "command": "coffer-mcp-shim"
    }
  }
}
```

退出并重新打开 Claude Desktop。

### Cursor

编辑 `~/.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "coffer": {
      "command": "coffer-mcp-shim"
    }
  }
}
```

---

## 6.（可选）打开桌面 UI

```bash
cd frontend && npm ci && npm run dev
```

打开 http://localhost:5173，就能看到刚才注册的服务器，附带开关、能力详情、调用日志与审计日志。

或者直接以 dev 模式跑完整的 Tauri 应用：

```bash
cd desktop && cargo tauri dev
```

---

## 7.（可选）30 秒上手知识库

Coffer 的 `knowledge_base` kind 把本地文件变成一个可检索的 RAG 语料库，编码 agent 可通过同一个 MCP 网关使用：

```bash
coffer kb create design-notes
coffer kb ingest design-notes ~/work/notes/architecture.md
coffer kb search design-notes "how does our retry policy work?"
```

任何已接入的 MCP 客户端都会自动获得三个内置工具：`coffer__list_knowledge_bases`、`coffer__search_knowledge_base`、`coffer__get_document`，无需额外安装 MCP 服务器。

默认 embedding 模型 `BAAI/bge-small-en-v1.5` 会在首次 `coffer kb ingest` 时从 HuggingFace Hub 下载（约 130 MB，缓存到 `~/.cache/huggingface/`）。希望把下载提前到安装器步骤里完成，可以先跑 `coffer kb warmup` 触发离线预热。

完整流程见：[`specs/006-knowledge-base/quickstart.md`](../specs/006-knowledge-base/quickstart.md)。

---

## 故障排查

**守护进程起不来**
跑 `coffer daemon status` 看看。如果端口被占了，设置 `COFFER_PORT_RANGE_START=8001` 后重试。

**工具没在客户端里出现**
跑 `coffer mcp refresh <name>` 重新做一次能力发现，然后让客户端重连（新建 MCP 会话即可立刻看到变化）。

**私有服务器需要凭据**
把 secret 存进操作系统 keychain，注册时再引用：

```bash
coffer keychain set MY_API_KEY "sk-..."
coffer mcp add myserver \
  --stdio "npx -y @my/mcp-server" \
  --credential "MY_API_KEY=MY_API_KEY"
```

**找不到 shim**
跑 `coffer shim deploy`，并确认 `~/.coffer/bin` 在你的 `PATH` 中。若守护进程未运行，shim 会自动拉起。
