# 下载与安装

本页面是 Coffer 的权威安装指南 —— 安装脚本和发布说明均链接至此。请根据你的使用场景选择合适的方式：

| 方式                              | 适用场景                                      |
| --------------------------------- | --------------------------------------------- |
| [一行命令安装](#一行命令安装)     | 工作站、服务器、headless 环境上最快的安装方式 |
| [手动下载压缩包](#手动下载压缩包) | 离线机器、需要固定版本，或想自己校验签名      |
| [从源码安装](#从源码安装开发者)   | Coffer 的贡献者与开发者                       |

::: tip 只有一个下载，界面就在里面
Coffer 只发布**单个工件**：`coffer-cli-<triple>.tar.gz`。没有单独的桌面应用 —— 守护进程自己
提供 Web UI，用 `coffer open` 打开即可。
:::

::: tip 守护进程自动启动 —— 你不需要手动运行它
安装完成后，只需把 MCP 客户端指向 `coffer-mcp-shim` 并连接即可。守护进程在首次需要时会自动启动。
这是 [ADR-006（探测或拉起）](/zh/architecture/processes#detect-or-spawn-adr-006) 的核心设计。全新安装后，
你永远不会看到「守护进程未运行」的错误。
:::

---

## 一行命令安装

最快捷的安装方式。一条命令即可下载发布压缩包，并把其中的二进制文件解压到 `~/.coffer/bin`：

- **`coffer`** —— 管理 CLI（`coffer mcp add`、`coffer mcp list`、`coffer open` 等）
- **`coffer-daemon`** —— 长生命周期的后台进程，负责聚合上游 MCP 服务器并提供 Web UI
- **`coffer-mcp-shim`** —— MCP 客户端（Claude Code、Codex 等）与 daemon 通信的 stdio 桥接程序

以及守护进程自己会拉起的运行时辅助二进制文件（用于 SeaTalk 渠道的
`coffer-callback`）。

### macOS（Apple Silicon）

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
```

Coffer 只提供 macOS（Apple Silicon）构建。在 Linux 或 Intel macOS 上，安装脚本会给出友好提示，
并引导你使用[从源码安装](#从源码安装开发者)。

脚本会自动将 `~/.coffer/bin` 添加到 `PATH`（修改 shell profile）。打开新终端后，
这些二进制文件均可直接使用。

### 环境变量覆盖

| 变量                    | 作用                                         |
| ----------------------- | -------------------------------------------- |
| `COFFER_INSTALL_DIR`    | 覆盖安装目录（默认：`~/.coffer/bin`）        |
| `COFFER_VERSION`        | 固定版本，例如 `v0.1.0`（默认：最新版）      |
| `COFFER_NO_MODIFY_PATH` | 设为 `1` 以跳过修改 shell profile / 环境变量 |

### 验证下载

每次发布都会附带**一份聚合的 `SHA256SUMS`**，覆盖该次发布的全部工件。安装脚本会自动校验；
若需手动核查：

```sh
shasum -a 256 -c SHA256SUMS
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

### 打开 Web UI

```sh
coffer open
```

它会在守护进程自己的地址上打开浏览器，并通过一个一次性、短时效的 code 把 token 交给页面。
详见 [Web UI 指南](/zh/guide/web-ui)。

### 下一步

- [快速上手](/zh/guide/getting-started) —— 注册第一个 MCP 服务器并验证安装
- [接入客户端 →](/zh/guide/connect-client) —— 完整的客户端配置参考

---

## 手动下载压缩包

前往 [GitHub Releases 页面](https://github.com/wyx-sg/Coffer/releases/latest)，选择适合你平台的压缩包：

| 平台                          | 文件                         |
| ----------------------------- | ---------------------------- |
| macOS Apple silicon（M 系列） | `coffer-cli-<triple>.tar.gz` |

Coffer 只提供 macOS（Apple Silicon）构建。在 Linux 或 Intel macOS 上，请使用[从源码安装](#从源码安装开发者)。

先用该次发布的聚合 `SHA256SUMS` 校验下载，再解压：

```sh
shasum -a 256 -c SHA256SUMS
tar -xzf coffer-cli-<triple>.tar.gz -C ~/.coffer/bin
```

把 `~/.coffer/bin` 加入 `PATH`，MCP 客户端才能找到 `coffer-mcp-shim`。

### macOS Gatekeeper（未签名 —— 签名待完成）

这些二进制文件未签名，macOS 会在首次运行时隔离它们。代码签名与公证需要付费的 Apple Developer ID，
目前尚未申请。请对解压出来的二进制文件清除隔离属性：

```sh
xattr -d com.apple.quarantine ~/.coffer/bin/coffer ~/.coffer/bin/coffer-daemon ~/.coffer/bin/coffer-mcp-shim
```

### 安装后

守护进程首次以 frozen 构建方式启动时，会把同级的二进制文件部署进 `~/.coffer/bin/`（幂等 ——
未变化的文件不会被动），让 MCP 客户端能找到 shim，也让 shim 能自动拉起守护进程。然后：

```sh
claude mcp add coffer coffer-mcp-shim
coffer open
```

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
