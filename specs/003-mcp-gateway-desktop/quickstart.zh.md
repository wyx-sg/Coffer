# Quickstart —— Coffer 桌面端

> English: [quickstart.md](./quickstart.md)

5 分钟把 Coffer 桌面端从下载装进托盘，并让 `coffer-mcp-shim` 已经在
`PATH` 上、daemon 在后台运行。本文是 [`specs/001-mcp-gateway/quickstart.md`](../001-mcp-gateway/quickstart.md)
（CLI / shim）与 [`specs/002-ui-shell/quickstart.md`](../002-ui-shell/quickstart.md)
（开发者 checkout）的最终用户配套，覆盖单包安装路径。

## 选择你的下载层级

Releases 页面提供两个层级，二者都基于同一对 `coffer-daemon` +
`coffer-mcp-shim` 二进制构建：

- **CLI-only** —— 一份 `coffer-cli-<triple>` 归档（macOS / Linux 为
  `.tar.gz`，Windows 为 `.zip`），仅含这两份二进制。适合 headless 服务器
  与无 GUI 安装。见下文 [CLI-only 安装](#cli-only-安装)。
- **CLI+desktop** —— Tauri 安装包（DMG / MSI / AppImage / deb），含桌面
  外壳 + Web UI。适合日用桌面。即下文步骤 1–7 所述路径。

## 前置条件

- 一台 macOS 12+、Linux x64（基于 glibc 的发行版，用于 AppImage / deb）、
  或 Windows 10+ x64 的电脑。不需要 Python。
- 一个 MCP 客户端（Claude Code、Claude Desktop、Cursor，或任意支持
  stdio MCP 服务器的客户端）。

## 1. 下载安装包

前往 [GitHub Releases 页面](https://github.com/coffer/coffer/releases)，
下载与你的平台匹配的文件：

| 平台                          | 文件                                                                 |
| ----------------------------- | -------------------------------------------------------------------- |
| macOS Apple silicon（M 系列） | `Coffer_<version>_aarch64.dmg`                                       |
| macOS Intel                   | `Coffer_<version>_x64.dmg`                                           |
| Linux x64（AppImage，推荐）   | `Coffer_<version>_amd64.AppImage`                                    |
| Linux x64（deb）              | `coffer_<version>_amd64.deb`                                         |
| Windows 10+ x64（安装包）     | `Coffer_<version>_x64_en-US.msi` 或 `Coffer_<version>_x64-setup.exe` |

每份下载都有一份 `.sha256` 邻居。校验（可选但推荐）：

```bash
shasum -a 256 -c Coffer_<version>_aarch64.dmg.sha256   # macOS / Linux
certutil -hashfile Coffer_<version>_x64_en-US.msi SHA256   # Windows
```

> **macOS Gatekeeper**：在拿到 Apple Developer ID 之前，DMG 以未签名形式
> 发布。首次打开时 macOS 会拒绝运行。要么右键 app 选 **打开** 做一次绕行；
> 要么运行 `xattr -d com.apple.quarantine /Applications/Coffer.app`。详见
> [macos-notarization.zh.md](../../docs/distribution/macos-notarization.zh.md)。

## 2. 安装

- **macOS**：打开 DMG，把 **Coffer.app** 拖进 `/Applications`。
- **Linux (AppImage)**：`chmod +x Coffer_<version>_amd64.AppImage`，
  双击或终端运行。
- **Linux (deb)**：`sudo apt install ./coffer_<version>_amd64.deb`。
- **Windows**：双击 MSI（或 NSIS 的 `setup.exe`），按引导完成。

## 3. 首次启动

从应用菜单（或 AppImage）打开 **Coffer**。首次启动时：

- 主窗口落在 Resources 欢迎视图（与 [002-ui-shell quickstart](../002-ui-shell/quickstart.zh.md)
  step 2 描述的同一份 Web UI）。
- 桌面外壳静默把 `coffer-mcp-shim` 部署到稳定的 PATH 目录：
  - **macOS / Linux**：`~/.coffer/bin/coffer-mcp-shim`
  - **Windows**：`%LOCALAPPDATA%\Coffer\bin\coffer-mcp-shim.exe`
- daemon 在一个空闲端口（默认 8000，被占用时退到 8001–8009）启动，
  并写出 `~/.coffer/daemon.json`。
- 托盘图标出现在菜单栏 / 系统托盘。

如果 shim 的目标目录不在 `PATH` 上，Coffer 会在 **Settings → App** tab
弹出一次性提示，给出添加到你 shell rc 文件（`~/.zshrc`、`~/.bashrc` 等）
的准确一行。

## 4. 添加一个 MCP 服务器

在欢迎视图点击 **Add MCP server**。粘贴任意厂商 README 里的标准
`mcpServers` JSON，确认 secrets-review 步骤，提交。该服务器落在
Resources 列表上并在约 10 秒内进入 "healthy"。

## 5. 让你的 MCP 客户端指向 Coffer

在你的 MCP 客户端配置中把 Coffer shim 加为一个服务器。下面的片段可以
逐字复制 —— 它们自动发现 daemon，无需逐机器参数化：

**Claude Code / Claude Desktop / Cursor**（`.mcp.json` 或厂商特有配置）：

```json
{
  "mcpServers": {
    "coffer": {
      "command": "coffer-mcp-shim"
    }
  }
}
```

重启你的 MCP 客户端。它现在应该看到从 Coffer 注册的所有服务器中已启用
的全部能力。

## 6. 托盘使用

右键（或 macOS 上左键）托盘图标。菜单提供：

| 项                 | 含义                                                                        |
| ------------------ | --------------------------------------------------------------------------- |
| **Open**           | 恢复主窗口（被关闭键隐藏到托盘的那个）。                                    |
| **Restart daemon** | 停止本地 `coffer-daemon` 进程，并在同一端口起一个新的。                     |
| **Quit**           | 同时停止桌面进程**和** daemon，托盘图标消失。（点窗口关闭键不会做这件事。） |

用 OS 关闭键关掉主窗口只会把窗口**隐藏**到托盘；daemon 仍存活，你的
MCP 客户端继续工作。

## 7. 可选：登录时启动 Coffer

打开 **Settings → App**，打开 **Launch at login** 开关。Coffer 会把自己
注册到 OS 的 autostart 机制：

- macOS：`~/Library/LaunchAgents/` 下的 LaunchAgent。
- Linux：`~/.config/autostart/` 下的 `.desktop` 文件。
- Windows：`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 下的 Run key。

登出再登入（或重启）验证 —— 托盘图标会在你不打开任何东西的情况下出现。

## CLI-only 安装

对于 headless 机器，或任何你不想要桌面应用的机器，下载 CLI-only 归档
而不是安装包。

1. 在 [GitHub Releases 页面](https://github.com/coffer/coffer/releases)
   下载与你平台 build triple 匹配的归档（`<triple>` 如
   `aarch64-apple-darwin`、`x86_64-apple-darwin`、
   `x86_64-unknown-linux-gnu`、`x86_64-pc-windows-msvc`）：
   - **macOS / Linux**：`coffer-cli-<triple>.tar.gz`
   - **Windows**：`coffer-cli-<triple>.zip`

   校验（可选但推荐）：

   ```bash
   shasum -a 256 -c coffer-cli-<triple>.tar.gz.sha256   # macOS / Linux
   certutil -hashfile coffer-cli-<triple>.zip SHA256     # Windows
   ```

2. 解压 —— 它仅含 `coffer-daemon` 与 `coffer-mcp-shim`：

   ```bash
   tar -xzf coffer-cli-<triple>.tar.gz                   # macOS / Linux
   ```

3. 启动 daemon。它会挑一个空闲端口（默认 8000，被占用时退到 8001–8009）
   并写出 `~/.coffer/daemon.json`：

   ```bash
   ./coffer-daemon
   ```

4. 把 `coffer-mcp-shim` 放上 `PATH`，使 MCP 客户端可以解析
   `command: coffer-mcp-shim` 配置：
   - **macOS / Linux**：移到 `~/.coffer/bin/`，并在 shell rc
     （`~/.zshrc`、`~/.bashrc` 等）把该目录加入 `PATH`。
   - **Windows**：移到 `%LOCALAPPDATA%\coffer\bin`，并把该目录加入
     用户 `PATH`。

5. 让你的 MCP 客户端指向 shim —— 与桌面路径
   （[步骤 5](#5-让你的-mcp-客户端指向-coffer)）相同的片段：

   ```json
   {
     "mcpServers": {
       "coffer": {
         "command": "coffer-mcp-shim"
       }
     }
   }
   ```

shim 通过 `~/.coffer/daemon.json` 自动发现运行中的 daemon，无需逐机器
参数化。

## 故障排查

- **托盘图标始终不出现** —— 桌面外壳在平台托盘图标加载失败时退回到一份
  内嵌 PNG（见 spec 的 Edge Cases）。如果仍然看不到，检查
  `~/.coffer/logs/desktop.log`。
- **`coffer-mcp-shim: command not found`** —— 你的 shell `PATH` 没有
  包含 shim 目录。重启一次 Coffer，按 Settings → App 的提示操作，然后
  打开一个新终端。
- **daemon 拉不起来** —— 打开 `~/.coffer/logs/daemon.log` 搜
  `ERROR`。最常见的原因是 8000–8009 段每个端口都已被其他进程占用；
  退掉那些进程或等它们释放端口。
- **更新** —— 新版本请查看
  [GitHub Releases 页面](https://github.com/coffer/coffer/releases)；
  在已有应用上安装新 bundle 即可（你 `~/.coffer/` 下的数据会被保留）。
