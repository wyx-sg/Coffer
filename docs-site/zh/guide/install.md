# 下载与安装

本页面是 Coffer 的权威安装指南 —— 安装脚本和发布说明均链接至此。请根据你的使用场景选择合适的方式：

| 方式                            | 适用场景                                          |
| ------------------------------- | ------------------------------------------------- |
| [一行命令安装](#一行命令安装)   | 服务器、headless 环境、希望最快完成安装的终端用户 |
| [桌面应用](#桌面应用)           | 工作站日常使用；包含 GUI 和 Web UI                |
| [从源码安装](#从源码安装开发者) | Coffer 的贡献者与开发者                           |

::: tip 守护进程自动启动 —— 你不需要手动运行它
安装完成后，只需把 MCP 客户端指向 `coffer-mcp-shim` 并连接即可。守护进程在首次需要时会自动启动。
这是 [ADR-006（探测或拉起）](/zh/architecture/distribution#adr-006) 的核心设计。全新安装后，
你永远不会看到「守护进程未运行」的错误。
:::

---

## 一行命令安装

最快捷的安装方式。一条命令即可将三个二进制文件下载并解压到 `~/.coffer/bin`：

- **`coffer`** —— 管理 CLI（`coffer mcp add`、`coffer mcp list` 等）
- **`coffer-daemon`** —— 长生命周期的后台进程，负责聚合上游 MCP 服务器
- **`coffer-mcp-shim`** —— MCP 客户端（Claude Code、Cursor 等）与 daemon 通信的 stdio 桥接程序

### macOS / Linux

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
```

脚本会自动将 `~/.coffer/bin` 添加到 `PATH`（修改 shell profile）。打开新终端后，
三个二进制文件均可直接使用。

### 环境变量覆盖

| 变量                    | 作用                                         |
| ----------------------- | -------------------------------------------- |
| `COFFER_INSTALL_DIR`    | 覆盖安装目录（默认：`~/.coffer/bin`）        |
| `COFFER_VERSION`        | 固定版本，例如 `v0.1.0`（默认：最新版）      |
| `COFFER_NO_MODIFY_PATH` | 设为 `1` 以跳过修改 shell profile / 环境变量 |

### 验证下载

每次发布都会附带 `SHA256SUMS` 文件。安装脚本会自动校验；若需手动核查：

```sh
# macOS
shasum -a 256 -c SHA256SUMS

# Linux
sha256sum -c SHA256SUMS
```

### 安装后：接入 MCP 客户端

一行命令安装完成后，守护进程尚未启动 —— 它会在首次使用时自动拉起：

```sh
# 将 Coffer 注册到 Claude Code（首次工具调用时自动拉起守护进程）
claude mcp add coffer coffer-mcp-shim
```

对于其他客户端，在配置中设置 `command: coffer-mcp-shim` 并重启客户端。shim 首次收到连接时
会自动启动守护进程。

也可通过管理 CLI 触发自动启动：

```sh
coffer mcp add filesystem --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"
coffer mcp list
```

上述任一命令均会在守护进程未运行时自动启动它。

### 下一步

- [快速上手](/zh/guide/getting-started) —— 注册第一个 MCP 服务器并验证安装
- [接入客户端 →](/zh/guide/connect-client) —— 完整的客户端配置参考

---

## 桌面应用

桌面应用将一切 —— 守护进程、shim、Web UI —— 打包进单个安装包。无需 Python。推荐在工作站上使用。

### 下载

前往 [GitHub Releases 页面](https://github.com/wyx-sg/Coffer/releases/latest)，选择适合你平台的文件：

| 平台                          | 文件                              |
| ----------------------------- | --------------------------------- |
| macOS Apple silicon（M 系列） | `Coffer_<version>_aarch64.dmg`    |
| macOS Intel                   | `Coffer_<version>_x64.dmg`        |
| Linux x64（AppImage，推荐）   | `Coffer_<version>_amd64.AppImage` |
| Linux x64（deb）              | `coffer_<version>_amd64.deb`      |

每份文件都有一个 `.sha256` 邻居文件，运行前请先校验：

```sh
# macOS / Linux
shasum -a 256 -c SHA256SUMS   # Linux 上改用 sha256sum -c SHA256SUMS
```

### 安装

- **macOS**：打开 DMG，把 **Coffer.app** 拖进 `/Applications`。
- **Linux（AppImage）**：`chmod +x Coffer_<version>_amd64.AppImage`，然后运行。
- **Linux（deb）**：`sudo apt install ./coffer_<version>_amd64.deb`。

### macOS Gatekeeper（未签名 —— 公证待完成）

DMG 以未签名形式发布。首次打开时 macOS 会拒绝运行。一次性清除隔离标志：

```sh
xattr -d com.apple.quarantine /Applications/Coffer.app
```

或右键应用选择**打开**进行一次性绕行。

### 安装后

首次启动时，桌面应用会：

1. 在空闲端口（默认 8000）启动守护进程，并写出 `~/.coffer/daemon.json`。
2. 将 `coffer-mcp-shim` 部署到 `~/.coffer/bin/`，使 MCP 客户端能找到它。
3. 在主窗口中打开 Web UI。

接入 MCP 客户端：

```sh
claude mcp add coffer coffer-mcp-shim
```

完整的桌面应用指南（托盘菜单、登录时启动等）请参阅[桌面应用 →](/zh/guide/desktop)。

---

## 从源码安装（开发者）

适用于 Coffer 的贡献者与开发者。将 `coffer` CLI 和 shim 作为 Python console-script 入口安装
（无 PyInstaller、无二进制下载）。

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ./backend[dev]
make verify          # lint + 类型检查 + 单元 + 集成 + 契约 + acceptance
```

::: tip 这里同样适用自动启动
`pip install` 会把 `coffer`、`coffer-daemon` 和 `coffer-mcp-shim` 装到 `PATH` 上。守护进程在
你首次运行管理命令或 MCP 客户端连接时会自动启动 —— `coffer daemon start` 可用于显式控制，
但**不是**必要的安装步骤。
:::

完整的从源码安装流程请参阅[快速上手](/zh/guide/getting-started)。
