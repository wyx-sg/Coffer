# ADR-007: 分发 —— 用 PyInstaller 打包 daemon + shim，并作为 Tauri sidecar

> English: [ADR-007-distribution-pyinstaller-tauri-sidecar.md](./ADR-007-distribution-pyinstaller-tauri-sidecar.md)

**Status**: 已采纳 (Accepted)
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: spec `001-mcp-gateway` (FR-021, SC-009), [ADR-005](ADR-005-session-subprocess-model.md), [ADR-006](ADR-006-daemon-detect-or-spawn.md)

## 背景

Coffer 有三个可运行入口：长生命周期的 `coffer-daemon`、按 MCP 客户端会话
拉起的短生命周期 `coffer-mcp-shim`，以及一个桌面外壳 (Tauri)。项目的目标
用户群包含没有系统 Python 安装的用户。规范 `001-mcp-gateway` 在两处明确
承诺了这一点：

- **FR-021** —— "终端用户的安装路径 MUST 产出一个可工作的 coffer daemon
  和 shim，无需用户自行安装 Python 或其他运行时。"
- **SC-009** —— 一台干净机器（没有 Python）的用户，从单一发行包出发到达
  `status: ready`，除点击安装器外没有任何手工步骤。

这就排除了任何要求用户先装 Python、维护 virtualenv 或处理 wheel 构建
错误的方案。我们需要决定 Python 代码以何种方式打包给最终用户。

桌面外壳本身是另一个问题：Tauri bundle 落地时，需要内嵌（或以其它方式
定位）daemon + shim 的二进制。Tauri 2 的 "sidecar" 机制（`tauri.conf.json`
中的 `bundle.externalBin`）正是为「随应用分发原生辅助二进制」而设计的官方
方案。

## 决定

**用 PyInstaller 把 daemon 与 shim 各自打成单文件二进制；桌面端 bundle
通过 Tauri sidecar 方式携带它们。**

具体选择：

- `backend/coffer-daemon.spec` 构建 `dist/coffer-daemon`（单文件可执行）。
  `backend/coffer-mcp-shim.spec` 构建 `dist/coffer-mcp-shim`。
- `make bundle-binaries`（`scripts/build_binaries.sh`）驱动当前宿主机上的
  PyInstaller；发布 CI 矩阵在 macOS arm64+x64、Windows x64、Linux
  x64+arm64 各 runner 上调用它。
- 每份 spec 都把 FastAPI、SQLAlchemy 2 / aiosqlite、Pydantic 2、`mcp`、
  `keyring`、以及（仅 daemon）Alembic 等运行时实测必需的 `hiddenimports`
  显式钉住。隐藏导入清单记录于 `specs/001-mcp-gateway/research.md`。
- Alembic 迁移作为数据文件随 daemon 二进制一同打包，以便首次启动时对全新
  DB 跑 `upgrade head`。
- shim 二进制刻意排除 daemon 端的重依赖（FastAPI、uvicorn、SQLAlchemy、
  Alembic、structlog）以保持体积可控 —— shim 只通过 loopback HTTP 与
  daemon 通信，所需仅是 `httpx`。
- 桌面端应用单独打成 Tauri 2 bundle（DMG / MSI / AppImage / deb）。
  PyInstaller 产出的二进制通过 `tauri.conf.json` 的 `bundle.externalBin`
  接入；外壳通过 `~/.coffer/daemon.json` ([ADR-006](ADR-006-daemon-detect-or-spawn.md)) 发现 daemon，而不是
  直接拉起，这样同一对二进制也能被 CLI 与外部 MCP 客户端复用。
- Tauri sidecar 的具体接线随桌面端外壳一起落地（计划在后续 UI 规范中）。
  spec `001-mcp-gateway` 本身只发布 daemon + shim 二进制；走 CLI-only
  安装路径的用户在没有桌面 UI 的情况下也能获得可工作的 daemon 与 shim。

## 后果

**正面**

- 第一天起就满足 FR-021 与 SC-009：`make bundle-binaries` 产出两份在干净
  机器上无 Python 也能直接运行的单文件可执行。
- 跨平台一致：同一份 PyInstaller spec 在 macOS、Windows、Linux 上不改动
  即可工作（只 `--target-arch` 与宿主机有差异）。
- shim 二进制因排除服务端依赖而保持小巧 —— 对每次会话都重新拉起 shim
  的 MCP 客户端来说很关键。
- Tauri sidecar 是 Tauri 2 应用分发辅助二进制的官方做法；`tauri build`
  自动产出 DMG / MSI / AppImage / deb 等格式。
- 与后续可选的「系统服务安装」（[ADR-006](ADR-006-daemon-detect-or-spawn.md) 运维后续）前向兼容：
  launchd / systemd / Windows service 配置都指向同一份二进制路径。

**负面**

- PyInstaller 产出的二进制较大（macOS 上每份约 40–80 MB，Windows 上更大），
  因为它内嵌了 Python 解释器及其部分标准库。对面向开发者的桌面应用而言
  可接受；如果未来要面向嵌入式场景缩减 shim 体积，就不行。
- PyInstaller 的隐藏导入发现靠经验积累；首次引入新 Python 依赖（特别是
  Pydantic / SQLAlchemy 升级）可能需要重新走一遍 import graph。缓解方式：
  在 `research.md` 与 `backend/coffer-*.spec` 中钉住清单，并在 CI 中跑
  bundle smoke test。
- macOS Gatekeeper 要求要么走公证 (notarization)，要么首次启动时执行
  `xattr -d com.apple.quarantine`。公证暂缓（尚未有 Apple Developer
  账号）；手动 `xattr` 步骤记录在 `specs/001-mcp-gateway/quickstart.md`。
- 内嵌 Python 解释器意味着一次 Python 安全更新就需要发一版 Coffer；这是
  「无需系统 Python」的代价。

**运维后续**

- CI 发布矩阵每次发布产出六份制品（macOS arm64 + x64 universal、Windows
  x64、Linux x64 + arm64）。每份在发布前都跑 post-build smoke test
  （`scripts/smoke_test_bundle.sh`）—— 必须能启动 bundled daemon 到
  `status: ready`。
- shim 二进制路径在首次启动时暴露给用户（桌面 UI 存在时通过 UI 提示；
  CLI-only 用户通过 `coffer daemon status` 获取），以便粘贴进 MCP 客户端
  配置。

## 备选方案

**要求系统 Python 3.12+ 与一个 venv（`pip install coffer`）**。被否决。

- 直接违反 FR-021 与 SC-009。Windows 上以及大多数设计师 / 非开发者背景的
  macOS 用户没有可工作的 Python 安装，更别说我们要求的版本了。
- 即便在 Linux 上，发行版自带的 Python 通常落后我们一个大版本；用户会
  撞上 `aiosqlite` 或 `pydantic-core` 的 wheel 构建错误。
- 面向贡献者的 CLI-only 开发者安装路径（`pip install -e ./backend`）依然
  在文档中保留 —— 但它不是面向终端用户的分发渠道。

**用 Nuitka 或 PyOxidizer 取代 PyInstaller**。v0 暂否决。

- PyInstaller 对我们的依赖集合（FastAPI、SQLAlchemy async、`mcp`、
  `keyring` backends）支持最广，社区里隐藏导入的配方也最齐全。Nuitka 的
  AOT 编译诱人，但会让构建周期更长，并在 CI 中引入平台相关的编译器依赖。
- 后续换打包工具是一个有边界、可逆的改动：daemon 的运行时契约里没有
  任何东西特别绑定 PyInstaller。

**用 Tauri 的「embedded resources」取代 sidecar**。被否决。

- Tauri sidecar 机制就是为「随应用分发一份原生二进制」设计的；用它能保留
  正确的按平台打包流程（codesign identity、Linux 上 `chmod +x`、Windows
  代码签名），以及通过 OS 而非 Tauri IPC 层来拉起 daemon 的能力。
- Embedded resources 适合静态资源，而非可执行文件。

**两个独立安装器（Tauri 桌面端 + PyInstaller 二进制）**。在主用户体验
层面被否决，但在 CLI-only 路径上隐式接受。

- 桌面用户的体验必须是「把应用拖到 /Applications 就完事」；这要求 daemon
  - shim 二进制必须打进 Tauri bundle 里。sidecar 机制正好提供这一点。
- 对开发者 / CLI-only 用户，`pip install -e ./backend` 仍是文档化路径；
  他们完全绕开 PyInstaller 与 Tauri bundle。
- 后续 v0 之后或许会单独发布仅含 PyInstaller 二进制（不含 Tauri 外壳）
  的下载包，用于 headless 服务器安装；当前 v0 不需要。
