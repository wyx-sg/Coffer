# 桌面应用

Coffer 桌面应用是日常使用的推荐安装方式。它把你所需的一切 —— 守护进程、shim 和
Web UI —— 打包进单个安装包，无需安装 Python。

## 桌面应用是什么

桌面应用是一个 **Tauri 2** 外壳（Rust + WebView），将 Coffer 守护进程和 MCP shim
作为 PyInstaller 构建的 sidecar 二进制文件内嵌其中。由于二进制文件自包含，最终用户
无需安装 Python。[spec 002](/zh/reference/specs/002-ui-shell/spec) 中的 Web UI 在
Tauri 窗口内渲染。

两层发布设计（CLI-only 归档 vs. CLI+desktop bundle）及其背后的架构决策，请参阅
[架构 → 分发](/zh/architecture/distribution)。

## 运行方式

每次启动时，桌面应用会：

1. **检测或拉起守护进程** —— 读取 `~/.coffer/daemon.json` 查找正在运行的守护进程。
   若不可达，则以脱离父进程的方式拉起 `coffer-daemon`，使其在桌面窗口关闭后继续存活。
2. **部署 shim + daemon** —— 幂等地把内嵌的 `coffer-mcp-shim` 与 `coffer-daemon`
   复制到稳定的用户可写 PATH 目录：
   - macOS / Linux：`~/.coffer/bin/`

   daemon 与 shim 同目录部署，使得重启后即便桌面应用没在运行，shim 也能自动拉起
   daemon。
3. **显示系统托盘图标** —— 应用运行期间始终存在。

用 OS 关闭键关掉主窗口只会把窗口**隐藏**到托盘；守护进程仍存活，MCP 客户端继续
工作。要真正退出，请使用托盘菜单中的 **Quit**。

### 托盘菜单

| 项                 | 含义                                           |
| ------------------ | ---------------------------------------------- |
| **Open**           | 恢复主窗口（被关闭键隐藏到托盘的那个）。       |
| **Restart daemon** | 停止本地守护进程，并在同一端口起一个新的。     |
| **Quit**           | 同时停止桌面进程和守护进程，托盘图标随之消失。 |

## 安装

### 下载

前往 [GitHub Releases 页面](https://github.com/wyx-sg/Coffer/releases)，下载与你
平台匹配的文件：

| 平台                          | 文件                              |
| ----------------------------- | --------------------------------- |
| macOS Apple silicon（M 系列） | `Coffer_<version>_aarch64.dmg`    |
| Linux x64（AppImage，推荐）   | `Coffer_<version>_amd64.AppImage` |
| Linux x64（deb）              | `coffer_<version>_amd64.deb`      |

每份下载都有一份 `.sha256` 邻居文件供校验。

### 安装

- **macOS**：打开 DMG，把 **Coffer.app** 拖进 `/Applications`。
- **Linux (AppImage)**：`chmod +x Coffer_<version>_amd64.AppImage`，然后运行。
- **Linux (deb)**：`sudo apt install ./coffer_<version>_amd64.deb`。

### macOS Gatekeeper

在拿到 Apple Developer ID 之前，DMG 以未签名形式发布，首次打开时 macOS 可能提示 Coffer「已损坏」。
（对于「已损坏」提示，右键「打开」无效。）请清除隔离标志：

```bash
xattr -dr com.apple.quarantine /Applications/Coffer.app
```

如果仍无法打开，重新进行 ad-hoc 签名：

```bash
codesign --force --deep --sign - /Applications/Coffer.app
```

公证（notarisation）是当前的非目标；等 Developer ID 就位后的启用 runbook 见
`docs/distribution/macos-notarization.md`。

### 首次启动

首次启动时：

- 主窗口落在 Resources 欢迎视图（即 [Web UI 指南](/zh/guide/web-ui) 中描述的界面）。
- 守护进程在空闲端口（默认 8000，被占用时退到 8001–8009）启动，并写出
  `~/.coffer/daemon.json`。
- Shim 被部署到其 PATH 目录（见上文）。
- 托盘图标出现。

如果 shim 的目标目录尚不在 `PATH` 中，Coffer 会在 **Settings → App** 弹出一次性
提示，给出添加到 shell rc 文件的准确一行。

## CLI-only 替代方案

对于 headless 服务器或不想要桌面应用的机器，在同一 Releases 页面下载
**CLI-only** 归档（`coffer-cli-<triple>.tar.gz`）。归档中仅含 `coffer-daemon` 和
`coffer-mcp-shim` —— 解压、运行守护进程、把 shim 放上 `PATH`，再让你的 MCP 客户端
指向它即可。

## 下一步

- [接入客户端 →](/zh/guide/connect-client)
- [架构 → 分发](/zh/architecture/distribution)
