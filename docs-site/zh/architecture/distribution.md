# 分发

::: tip 核心锚点
Coffer 从同一对 PyInstaller 二进制文件以两个层级进行分发：面向无界面/开发者使用的**纯 CLI 压缩包**，以及面向日常桌面使用的 **CLI+桌面 Tauri 捆绑包**。两种层级都不需要用户机器上预装 Python。
:::

## 这解决了什么问题

Coffer 的 daemon 和 shim 是 Python 应用程序。目标用户群体包括：完全没有安装 Python 3.12 的开发者、只有系统自带 Python（通常落后一两个版本）的 macOS 用户，以及对设置 venv 不熟悉的 Windows 用户。要求这些用户 `pip install coffer` 并管理虚拟环境，会立刻让 Coffer 失去作为日常桌面工具的资格。

规范中对此有精确的要求：一个完全没有安装 Python 的用户，能够从单个可下载的工件出发，仅通过点击安装程序这样的手动步骤，就能让系统达到 `status: ready`。

## 开发者安装路径

从源码 checkout 进行开发的开发者完全绕过 PyInstaller 和 Tauri 捆绑包：

```bash
pip install -e ./backend[dev]
```

这会在开发者的 `PATH` 上放置两个控制台脚本入口点：

- **`coffer`** — 管理 CLI（`surfaces/cli/` 中的 Typer 应用程序）
- **`coffer-mcp-shim`** — 每个 MCP 会话一份的 stdio shim（`surfaces/shim/`）

daemon 直接作为 Python 进程运行：`coffer daemon start` 调用已安装包内部的 FastAPI/uvicorn 启动路径。无需二进制打包，无需构建步骤，无需边车编排。对 Python 源码的修改立即生效。

这条开发者路径有完善的文档，也是主要的贡献路径。它**不是**面向最终用户的分发渠道——PyInstaller 二进制文件承担那个角色。

## PyInstaller：独立二进制文件

对于面向最终用户的分发，`make bundle-binaries`（由 `scripts/build_binaries.sh` 驱动）在当前主机上针对两个 spec 文件运行 PyInstaller：

| Spec 文件                      | 输出二进制文件         | 包含内容                                                                                            |
| ------------------------------ | ---------------------- | --------------------------------------------------------------------------------------------------- |
| `backend/coffer-daemon.spec`   | `dist/coffer-daemon`   | FastAPI、SQLAlchemy 2 / aiosqlite、Pydantic 2、`mcp`、`keyring`、Alembic、structlog、Typer、uvicorn |
| `backend/coffer-mcp-shim.spec` | `dist/coffer-mcp-shim` | 仅 `httpx`（shim 是一个轻量级 loopback 转发器）                                                     |

PyInstaller 将 Python 解释器、所有依赖以及应用程序代码打包成单个可执行文件。用户直接运行 `coffer-daemon`，不需要 `python` 命令，不需要 `venv`，不需要 `pip`。shim 二进制文件刻意保持精简——它不包含任何服务端依赖，因为 shim 只需要 `httpx` 来通过 loopback HTTP 向 daemon 转发请求。每次会话都重新拉起 shim 的 MCP 客户端受益于更小二进制文件带来的更短冷启动时间。

Alembic 迁移文件通过 PyInstaller 的 `datas` 机制作为数据文件打包进 daemon 二进制文件。首次启动时，daemon 在接受连接之前对新数据库运行 `alembic upgrade head`——最终用户无需任何额外步骤即可完成正确的 schema 创建。

::: tip 为什么选择 PyInstaller 而非其他方案
有两个替代方案被明确考虑并在 v0 阶段被否决：

- **Nuitka / PyOxidizer**：AOT 编译能产生更小、更快的二进制文件，但会显著延长构建周期，并需要在 CI 中引入平台特定的编译器。切换打包工具是一个有界的可逆变更——daemon 的运行时契约中没有任何 PyInstaller 特定的部分。
- **依赖系统 Python**：直接违反了「没有 Python 的用户也能安装 Coffer」的需求。即使在 Linux 上，发行版自带的 Python 通常也落后一个版本；用户会遇到 `aiosqlite` 或 `pydantic-core` 的 wheel 构建错误。
  :::

## 两个下载层级

同一对 PyInstaller 二进制文件为两个分发层级提供支持：

### 层级 1：纯 CLI 压缩包

一个 `coffer-cli-<triple>` 压缩包——macOS 和 Linux 上为 `.tar.gz`，Windows 上为 `.zip`——包含：

- `coffer-daemon`（独立可执行文件）
- `coffer-mcp-shim`（独立可执行文件）
- SHA-256 校验和文件

此层级面向无界面服务器、CI 环境以及想要独立二进制文件而不需要桌面应用的开发者。用户解压压缩包，运行 `coffer-daemon`，将 `coffer-mcp-shim` 放到 `PATH` 上，然后将 MCP 客户端指向 shim。无需 Tauri，无需 GUI，无需桌面集成。

### 层级 2：CLI+桌面 Tauri 捆绑包

一个平台原生安装程序（macOS 上为 DMG，Windows 上为 MSI 和 NSIS 安装程序，Linux 上为 AppImage 和 `.deb`），内嵌：

- 同一对 `coffer-daemon` 和 `coffer-mcp-shim` PyInstaller 二进制文件，作为 **Tauri 边车**
- Tauri 2 桌面 shell（Rust + WebView）
- 来自 spec 002 的 Web UI

Tauri 边车机制（`desktop/tauri.conf.json` 中的 `bundle.externalBin`）是 Tauri 2 官方提供的随应用一起分发原生辅助二进制文件的方式。它处理平台特定的打包细节：代码签名身份、Linux 上的 `chmod +x`、Windows 代码签名——这些手动处理会很繁琐。Tauri 内嵌资源（另一种机制）用于静态资产，而非可执行文件；边车机制才是可运行二进制文件的正确选择。

::: tip 为什么不只提供桌面下载？
无界面服务器和 CI 环境无法运行 Tauri 应用。如果只提供桌面捆绑包，这些环境将没有任何可运行的工件。纯 CLI 压缩包是一个一等公民的发布层级，而非 v0 之后才会考虑的事后补充。
:::

## Tauri 桌面集成

桌面 shell 不仅仅是把 Web UI 包在窗口里。关键职责（由 spec 003 负责）：

**Daemon 监管。** 启动时，桌面 shell 读取 `~/.coffer/daemon.json`。如果已有一个可达的 daemon 在运行（任何入口点都可能已经启动了它——CLI、shim 或此前的桌面启动），shell 就连接到它。否则，它将 `coffer-daemon` 作为一个独立进程拉起（POSIX 上使用 `setsid`，Windows 上使用 `DETACHED_PROCESS`），使 daemon 在桌面窗口关闭后仍然存活。daemon 的「检测-或-拉起」模式确保不会出现重复的 daemon 进程。

**Shim 自动部署到 PATH。** 在每次桌面启动时，shell 以幂等方式将捆绑的 `coffer-mcp-shim` 部署到一个稳定的用户可写目录：

- macOS / Linux：`~/.coffer/bin/coffer-mcp-shim`
- Windows：`%LOCALAPPDATA%\Coffer\bin\coffer-mcp-shim.exe`（当 `%LOCALAPPDATA%` 未设置时，回退到 `%USERPROFILE%\Coffer\bin\`）

一个大小比较启发式方法处理升级：如果磁盘上的二进制文件与捆绑包中的二进制文件字节数相同，则保持不变（重复启动时的无操作）。不同的大小触发原子替换。这意味着通过新 DMG 或 MSI 升级 Coffer 的用户，在下次启动时会自动获得更新后的 shim，无需手动管理 PATH。

**系统托盘图标。** 主窗口关闭后，桌面应用以系统托盘图标运行。关闭窗口会将其隐藏；daemon 和托盘仍然存在。托盘菜单提供：打开（恢复窗口）、重启 daemon 和退出（调用 `app.exit()` 真正终止进程）。

**开机自启。** `tauri-plugin-autostart` 插件让 `AppSettings` 桌面标签页能够切换开机自启选项。启用后，Coffer 会在登录后在后台启动，托盘图标随即出现。

## 发布流水线

CI 发布矩阵（`.github/workflows/release.yml`）在每个 `v*` 标签上跨四个目标平台（macOS arm64、macOS x64、Linux x64、Windows x64）运行，生成：

**桌面安装程序（CLI+桌面层级）**：

- macOS arm64 DMG
- macOS x64 DMG（两个独立的按架构 DMG；目前没有通用 `lipo` 二进制文件）
- Linux x64 AppImage
- Linux x64 `.deb`
- Windows x64 MSI
- Windows x64 NSIS 安装程序（`.exe`）

**纯 CLI 压缩包（纯 CLI 层级）**：

- `coffer-cli-darwin-arm64.tar.gz`
- `coffer-cli-darwin-x86_64.tar.gz`
- `coffer-cli-linux-x86_64.tar.gz`
- `coffer-cli-windows-x86_64.zip`

每个工件都附带在 CI 中生成的 `<artifact>.sha256` 校验和文件。

上传前，每个捆绑包都运行一个构建后冒烟测试（`scripts/smoke_test_bundle.sh`）：脚本启动捆绑的 `coffer-daemon` 到 `status: ready` 状态，并让捆绑的 `coffer-mcp-shim` 与其通过 loopback 交换一个 JSON-RPC `initialize` 消息。冒烟测试非零退出会导致发布失败。该脚本仅支持 Unix；Windows 工件会被构建和上传，但在 CI 中不进行冒烟测试。

## macOS 公证

macOS Gatekeeper 会在首次启动时将未签名的应用程序标记为隔离状态。macOS 公证——Apple 证明应用程序不含已知恶意软件的流程——目前是 Coffer 的非目标：它需要付费的 Apple Developer 账户。

在公证启用之前，安装 macOS DMG 的用户必须在首次启动时手动清除隔离属性：

```bash
xattr -d com.apple.quarantine /Applications/Coffer.app
```

一旦 Developer ID 证书可用，启用签名和公证的完整操作手册见 `docs/distribution/macos-notarization.md`。

## 另请参阅

- [ADR-008：分发——PyInstaller + Tauri 边车](/zh/reference/adr/ADR-008-distribution-pyinstaller-tauri-sidecar) — 决策记录、被否决的替代方案和修订历史
- [Spec 003 参考](/zh/reference/specs/003-mcp-gateway-desktop/spec) — 桌面 shell 验收场景和功能需求
