# Coffer

> English: [README.md](./README.md)

> 本地优先 (local-first) 的 AI agent 保险库。一个地方统一管理你的 MCP 服务器、技能 (skills)、记忆 (memories) 与 agents。

Coffer 是一个守护进程 (daemon) + 桌面应用，它把上游 (upstream) MCP 服务器聚合起来，再通过一个统一、带命名空间的接口重新暴露给各类 MCP 客户端（Claude Desktop、Cursor、Claude Code）。配置一次，所有客户端看到的工具完全一致。所有状态都保存在你自己的机器上 —— 没有云账号，没有厂商锁定。

**状态**：v0.1 开发中。首个已实现功能（在 PR #14 中合并）：**MCP gateway**（聚合 stdio 与 HTTP 上游 MCP 服务器）。其它资源 kind（skills、memory、agents、channels）将在后续 spec 中规划。

---

## 安装

### 方案 1 —— 预构建安装包（发布后可用）

从 [Releases](https://github.com/wyx-sg/Coffer/releases) 下载对应平台的 `.dmg`（macOS）、`.msi`（Windows）、`.deb` / `.AppImage`（Linux），双击安装即可。首次启动时，shim 可执行文件会被部署到 `~/.coffer/bin/`。

### 方案 2 —— 源码安装（开发者模式）

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ./backend[dev]
cd frontend && npm ci && npm run build && cd ..
make verify          # sanity-check the install
coffer daemon start  # boots the daemon on http://127.0.0.1:<auto-port>
```

### 方案 3 —— 仅 CLI（不要桌面 UI）

同方案 2，但跳过前端构建。`pip install` 会把 CLI（`coffer`）与 stdio shim（`coffer-mcp-shim`）作为 console-script 入口装到 `PATH` 上 —— 它们脱离 Tauri 应用也能独立工作，无需单独部署。

---

## 快速上手

注册你的第一个 MCP 服务器 —— 以 `@modelcontextprotocol/server-filesystem` 为例：

```bash
coffer mcp add filesystem \
  --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"

coffer mcp list                   # → filesystem  | stdio | enabled
coffer mcp tool list filesystem   # → read_file, write_file, list_directory, …
```

然后把你的 MCP 客户端指向 shim 即可。完整的 5 分钟流程见 **[docs/quickstart.md](docs/quickstart.md)**。

---

## 接入 MCP 客户端

在下列任一客户端里，把 `coffer-mcp-shim` 配成 stdio MCP 服务器的启动命令即可。shim 会自动发现守护进程（必要时自动拉起），无需手工配置端口或 token。

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）/ `%APPDATA%\Claude\claude_desktop_config.json`（Windows）：

```json
{
  "mcpServers": {
    "coffer": {
      "command": "coffer-mcp-shim"
    }
  }
}
```

### Cursor

`~/.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "coffer": {
      "command": "coffer-mcp-shim"
    }
  }
}
```

### Claude Code

```bash
claude mcp add coffer coffer-mcp-shim
```

改完配置后重启客户端。工具名带命名空间，形如 `<server-name>__<tool-name>`（例如 `filesystem__read_file`）。

---

## 项目结构

```
backend/              Python daemon + CLI + shim
  coffer/
    domain/           pure types + business rules (no I/O)
    application/      services + orchestration
    infrastructure/   DB, MCP transports, keychain, daemon discovery
    surfaces/         HTTP (FastAPI) + CLI (Typer) + stdio shim
frontend/             React + Vite + Tailwind + shadcn desktop UI
desktop/              Tauri 2 shell (Rust)
specs/                Speckit specs (one per feature)
docs/decisions/       Architectural Decision Records (ADRs)
agents/               Workflow, SDD, stack, and testing guides
```

架构深入解读：[.specify/memory/architecture.md](.specify/memory/architecture.md)。
ADRs：[docs/decisions/](docs/decisions/)。

---

## 开发者常用命令

| 命令                            | 作用                                                                 |
| ------------------------------- | -------------------------------------------------------------------- |
| `make verify`                   | 全量检查：lint、类型、单元、集成、契约 (contract) 与 acceptance 审计 |
| `make install`                  | 把所有依赖装进项目 venv 和 node_modules                              |
| `make bundle-binaries`          | 用 PyInstaller 打包 `coffer-daemon` 与 `coffer-mcp-shim`             |
| `cd frontend && npm run dev`    | Vite 开发服务器，http://localhost:5173                               |
| `cd desktop && cargo tauri dev` | Tauri 应用 dev 模式（连接到 Vite）                                   |
| `cd e2e && npm test`            | Playwright e2e 测试（会真实拉起一个 daemon）                         |

---

## 参与贡献

- **Conventional Commits**（必须遵守）—— 见 [agents/workflow.md](agents/workflow.md)
- **Spec-driven development**（规格驱动开发）—— 每个功能从 `specs/<id>/` 下的 spec 开始 —— 见 [agents/sdd.md](agents/sdd.md)
- **架构契约** —— 6 条 importlinter 契约必须保持绿色（定义在 [backend/pyproject.toml](backend/pyproject.toml)）
- **凭据 (credentials)** —— 所有 secret 必须走 `coffer.infrastructure.credentials.keyring_adapter`，绝不允许以明文落到 DB

---

## 许可证

MIT —— 见 [LICENSE](LICENSE)。
