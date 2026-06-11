# Quickstart —— Coffer 桌面端

> English: [quickstart.md](./quickstart.md)

5 分钟把 Coffer 桌面端从下载装进托盘，并让 `coffer-mcp-shim` 已经在
`PATH` 上、daemon 在后台运行。本文是 [`specs/001-mcp-gateway/quickstart.md`](../001-mcp-gateway/quickstart.md)
（CLI / shim）与 [`specs/002-ui-shell/quickstart.md`](../002-ui-shell/quickstart.md)
（开发者 checkout）的最终用户配套，覆盖单包安装路径。

## 选择你的下载层级

Coffer 今天**只发布 macOS（Apple Silicon）**。Releases 页面提供两个层级，
二者都基于同一组 `coffer` + `coffer-daemon` + `coffer-mcp-shim` 二进制构建：

- **CLI-only** —— 一份 `coffer-cli-<triple>.tar.gz` 归档（macOS arm64），
  含三份二进制。适合 headless 服务器与无 GUI 安装。见下文
  [CLI-only 安装](#cli-only-安装)。
- **CLI+desktop** —— 未签名 macOS arm64 `.dmg`，含桌面外壳 + Web UI。适合
  日用桌面。即下文步骤 1–7 所述路径。

## 前置条件

- 一台 macOS 12+、Apple Silicon（M 系列）的 Mac。不需要 Python。
- 一个 MCP 客户端（Claude Code、Claude Desktop、Cursor，或任意支持
  stdio MCP 服务器的客户端）。

## 1. 下载安装包

前往 [GitHub Releases 页面](https://github.com/coffer/coffer/releases)，
下载 macOS bundle：

| 平台                          | 文件                                       |
| ----------------------------- | ------------------------------------------ |
| macOS Apple silicon（M 系列） | `Coffer_<version>_aarch64-unsigned.dmg`    |

release 提供单个聚合的 `SHA256SUMS` 文件（而非逐文件的 `.sha256` 邻居）。
校验（可选但推荐）：

```bash
# 在存放下载文件 + SHA256SUMS 的目录里执行
shasum -a 256 -c SHA256SUMS --ignore-missing
```

> **macOS Gatekeeper**：在拿到 Apple Developer ID 之前，DMG 以未签名形式
> 发布（注意文件名里的 `-unsigned`）。首次打开时 macOS 会拒绝运行。要么右键
> app 选 **打开** 做一次绕行；要么运行
> `xattr -dr com.apple.quarantine /Applications/Coffer.app`。详见
> [macos-notarization.zh.md](../../docs/distribution/macos-notarization.zh.md)。

## 2. 安装

- **macOS**：打开 DMG，把 **Coffer.app** 拖进 `/Applications`。

## 3. 首次启动

从 Applications 文件夹打开 **Coffer**。首次启动时：

- 主窗口落在 Agents 视图（index 重定向到 `/agents`；与
  [002-ui-shell quickstart](../002-ui-shell/quickstart.zh.md) step 2 描述的
  同一份 Web UI）。
- 桌面外壳静默把 `coffer-mcp-shim` 部署到稳定的 PATH 目录：
  `~/.coffer/bin/coffer-mcp-shim`。
- daemon 在一个空闲端口（默认 8000，被占用时退到 8001–8009）启动，
  并写出 `~/.coffer/daemon.json`。
- 托盘图标出现在菜单栏。

如果 shim 的目标目录不在 `PATH` 上，Coffer 会在 **Settings → App** tab
弹出一次性提示，给出添加到你 shell rc 文件（`~/.zshrc`、`~/.bashrc` 等）
的准确一行。

## 4. 添加一个 MCP 服务器

在侧栏打开 **MCP servers**（`/mcp-servers`），点击 **Add MCP server**。
粘贴任意厂商 README 里的标准 `mcpServers` JSON，确认 secrets-review 步骤，
提交。该服务器落在 MCP servers 列表上并在约 10 秒内进入 "healthy"。

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

左键托盘图标（macOS 上左键即弹出菜单）。菜单提供：

| 项                 | 含义                                                                  |
| ------------------ | --------------------------------------------------------------------- |
| **Open**           | 恢复主窗口（被关闭键隐藏到托盘的那个）。                              |
| **Restart daemon** | 重启 daemon（限频；与应用内 banner 的 Restart 按钮调用同一个 command）。 |
| **Quit**           | 退出桌面应用并移除托盘图标。daemon 继续运行，MCP 客户端仍可工作。    |

**Quit** 只停桌面（GUI）应用 —— daemon 是脱离父进程的独立进程，会在 Quit
后存活，因此已注册的 MCP 客户端透过 shim 继续工作。若要停掉 daemon 本身，
用 CLI（`coffer daemon stop`）。

应用内同样可以重启 daemon：当 daemon 不可达时，应用内的
**Daemon not running** banner 提供一个 **Restart** 按钮，背后与托盘项
是同一个限频 command。

用 OS 关闭键关掉主窗口只会把窗口**隐藏**到托盘；daemon 仍存活，你的
MCP 客户端继续工作。

## 7. 可选：登录时启动 Coffer

打开 **Settings → App**，打开 **Launch at login** 开关。Coffer 会把自己
注册到 macOS 的 autostart 机制（`~/Library/LaunchAgents/` 下的 LaunchAgent）。

登出再登入（或重启）验证 —— 托盘图标会在你不打开任何东西的情况下出现。

## CLI-only 安装

对于 headless 机器，或任何你不想要桌面应用的机器，下载 CLI-only 归档
而不是安装包。

1. 在 [GitHub Releases 页面](https://github.com/coffer/coffer/releases)
   下载 macOS arm64 归档（`<triple>` 为 `aarch64-apple-darwin`）：
   `coffer-cli-<triple>.tar.gz`。

   对照聚合的 `SHA256SUMS` 校验（可选但推荐）：

   ```bash
   shasum -a 256 -c SHA256SUMS --ignore-missing
   ```

2. 解压 —— 它含 `coffer`、`coffer-daemon` 与 `coffer-mcp-shim`
   （三者保持同目录共存，使 `coffer` 能 detect-or-spawn daemon）：

   ```bash
   tar -xzf coffer-cli-<triple>.tar.gz
   ```

3. 启动 daemon。它会挑一个空闲端口（默认 8000，被占用时退到 8001–8009）
   并写出 `~/.coffer/daemon.json`：

   ```bash
   ./coffer-daemon
   ```

4. 把 `coffer-mcp-shim` 放上 `PATH`，使 MCP 客户端可以解析
   `command: coffer-mcp-shim` 配置：移到 `~/.coffer/bin/`，并在 shell rc
   （`~/.zshrc`、`~/.bashrc` 等）把该目录加入 `PATH`。

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
  内嵌 PNG（见 spec 的 Edge Cases）。桌面侧诊断目前还不落盘（desktop crate
  没有接日志 sink），所以从终端启动 Coffer 查看其 stderr；daemon 问题查
  `~/.coffer/logs/daemon.log`。
- **`coffer-mcp-shim: command not found`** —— 你的 shell `PATH` 没有
  包含 shim 目录。重启一次 Coffer，按 Settings → App 的提示操作，然后
  打开一个新终端。
- **daemon 拉不起来** —— 打开 `~/.coffer/logs/daemon.log` 搜
  `ERROR`。最常见的原因是 8000–8009 段每个端口都已被其他进程占用；
  退掉那些进程或等它们释放端口。
- **更新** —— 新版本请查看
  [GitHub Releases 页面](https://github.com/coffer/coffer/releases)；
  在已有应用上安装新 bundle 即可（你 `~/.coffer/` 下的数据会被保留）。
