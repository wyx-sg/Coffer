# 功能规范：桌面外壳与分发

> English: [spec.md](./spec.md)

**Feature Branch**: `feature/003-mcp-gateway-desktop`（在 `feature/002-mcp-gateway-web` 之上）
**Status**: Draft
**Input**：002-ui-shell 交付了 Web UI，但明确把 spec 002 的 User Story 5（桌面外壳）的两个验收场景 —— 登录时启动（launch-at-login）与关闭到托盘（close-to-tray）—— 延期到本规范。本规范承接这两个场景，并交付让它们工作的 Tauri 桌面包装与分发流水线。

**范围说明**：Coffer 的用户可见 UI 由 002-ui-shell 拥有（Web 外壳、视觉语言、信息架构）。本规范新增的是**桌面包装层** —— Tauri 2 外壳、daemon 监管、托盘图标、autostart 插件、PyInstaller sidecar 打包、以及 macOS 公证发布流水线。它不引入任何新的 resource kind，也不引入任何新的 UI 屏幕；来自 002 的 Web UI 在 Tauri 窗口中渲染，桌面专用的 `AppSettings` 组件透过 002 已经接好的 `isTauri()` 守卫激活。

## 用户场景与测试

### User Story 1 —— 桌面外壳：常驻且不碍事（优先级 P3）

完成初次设置之后，开发者期望 Coffer 在任意 MCP 客户端启动时已经在线 —— 无需手工拉起 —— 并且在他们不主动管理时尽量隐身。Tauri 桌面应用监管本地 daemon（启动 daemon 并透明重连）、常驻系统托盘、点击托盘可恢复主窗口、并提供可选的「登录时启动」。

**为什么是这个优先级**：P3 —— 体验润色。daemon 与 shim（spec 001）即便没有桌面应用也能工作；本故事是把 Coffer 变成日用桌面产品的便利层。继承自 spec 002 §User Story 5，其中 launch-at-login 与 close-to-tray 被显式延期到本规范。

**独立可测**：打开「登录时启动」，登出后再登入 —— daemon 在运行，托盘图标在。关闭主窗口 —— daemon 仍活、托盘仍在、MCP 客户端仍可使用；从托盘恢复窗口看到的是同一状态。

**代表性场景**（完整列表见 `## Acceptance Scenarios`）：

- launch at login
- close to tray, not exit

---

### User Story 2 —— 单包安装（优先级 P3）

开发者从 GitHub Releases 页面下载一份本平台的安装包，得到一份可用的 Coffer —— 不需要系统 Python、不需要单独安装 daemon、也不需要手工把 shim 加入 PATH。Tauri bundle 把 `coffer-daemon` 与 `coffer-mcp-shim` 作为 PyInstaller 构建的 sidecar 一并携带；首次启动把 shim 部署到稳定的用户级 PATH 目录，daemon 自动就绪。

**为什么是这个优先级**：P3 —— 分发是把本地开发产物变成同事 / 开源贡献者可以「不 clone 仓库就试用」的产品的关键。没有单包安装，US1 的桌面外壳就没有目标人群。

**独立可测**：在干净机器（无 Python、无 Coffer checkout）上下载平台安装包，安装，启动一次；验证 daemon 到达 `status: ready` 且新开终端中 `coffer-mcp-shim` 可被解析。

**代表性场景**（完整列表见 `## Acceptance Scenarios`）：

- release tag produces the platform artifact matrix
- post-build smoke test boots shim and gets JSON-RPC reply

---

### User Story 3 —— Daemon 自动监管（优先级 P3）

用户打开桌面应用，期望「daemon 在运行」是开箱即真。若 daemon 已经在跑（由 CLI 或 shim 等其他入口拉起），桌面外壳直接连接；若没在跑，外壳把 daemon 作为脱离父进程的独立进程拉起，并让 daemon 在桌面窗口关闭之后继续存活。用户也可以从桌面 UI 显式重启 daemon。

**为什么是这个优先级**：P3 —— detect-or-spawn 模式由 [ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md) 拥有；本故事是桌面外壳「正确应用该模式」的责任，使 daemon 寿命长于 GUI。

**独立可测**：daemon 已在跑（例如先 `coffer daemon start`）时启动桌面应用 —— 直接连接，不重复拉起。退出桌面应用 —— daemon 仍可达。daemon 未跑时启动桌面应用 —— 应用拉起 daemon；关闭桌面应用后 daemon 仍存活。

**代表性场景**（完整列表见 `## Acceptance Scenarios`）：

- desktop shell connects to an already-running daemon without duplicating it
- desktop shell spawns the daemon when none is running and the daemon survives close
- restart daemon from the tray/app menu

---

### User Story 4 —— Shim 自动部署到 PATH（优先级 P3）

用户复制粘贴厂商的 MCP 客户端配置片段（`"command": "coffer-mcp-shim"`），它无须告诉用户具体路径就能解析。桌面应用每次启动都幂等地把 bundle 自带的 `coffer-mcp-shim` 二进制部署到稳定的用户可写目录（macOS / Linux：`~/.coffer/bin/`；Windows：`%LOCALAPPDATA%\Coffer\bin\`）；通过 size-mismatch 启发式判断 bundle 升级则重新拷贝，否则保持 no-op。

**为什么是这个优先级**：P3 —— shim 的可发现性使 README 里的 MCP 客户端配置片段在不同用户之间可移植，无需逐机器参数化。

**独立可测**：在全新安装上启动桌面应用，验证 `which coffer-mcp-shim` 解析到预期目录；版本未变时再启动，验证磁盘上的二进制未被改动（mtime / size 不变）；升级 bundle 后启动，验证磁盘上的二进制被替换。

**代表性场景**（完整列表见 `## Acceptance Scenarios`）：

- first launch deploys shim to user PATH
- subsequent launch is idempotent (no-op when shim already up to date)
- upgraded bundle triggers shim re-deploy via size-mismatch heuristic

---

### User Story 5 —— 托盘菜单动作（优先级 P3）

用户点击托盘图标，期望看到一个小而明确的菜单 —— 打开主窗口、重启 daemon、退出。"退出" 真的退出（不会再次 hide-to-tray）；"重启" 干净地拉起 daemon；"打开" 恢复被隐藏的窗口。

**为什么是这个优先级**：P3 —— 当主窗口关闭后，托盘图标是用户操作运行中 Coffer 的唯一抓手。没有显式 "退出"，停止 Coffer 的唯一方法就是系统进程管理器。

**独立可测**：关闭主窗口（hide 到托盘）；点击托盘 "Open" —— 主窗口恢复。点击 "Restart daemon" —— daemon 进程重启，daemon.json 中同一端口可达。点击 "Quit" —— Coffer 进程退出、托盘图标消失、没有遗留的 daemon。

**代表性场景**（完整列表见 `## Acceptance Scenarios`）：

- tray menu open restores the hidden window
- tray menu quit exits the desktop app via app.exit()
- tray menu restart bounces the daemon process

---

### Edge Cases

- **Shim size-mismatch 启发式** —— 自动部署在拷贝之前比较 bundle 自带 shim 的字节大小与磁盘上的 shim。一致 → no-op。不一致 → 原子替换。无需额外的版本戳文件就能捕获版本升级。
- **Windows shim PATH 兜底** —— 当 `%LOCALAPPDATA%` 未设（罕见；多见于非交互式服务上下文），shim 部署退回到 `%USERPROFILE%\Coffer\bin\` 并输出一行日志。桌面应用继续启动。
- **Bundled shim 搜索向上探测父目录** —— Tauri bundle 在 dev（`target/debug/`）与 release（`Resources/`）的布局不同。shim 部署步骤同时探测 sidecar 目录及其父目录，使同一份代码在两种情况下都工作。
- **托盘图标退回内嵌 PNG** —— 当平台首选的托盘图标（如 macOS 模板色 PNG）加载失败时，桌面外壳退回到一份内嵌的 PNG，确保托盘菜单永不消失。

## Acceptance Scenarios

下方场景覆盖本规范的用户故事。`launch at login` 与 `close to tray, not exit` 两个场景按 `specs/002-ui-shell/spec.md` 的 audit-traceability 注释逐字导入，对应 US1 的桌面外壳验收。本规范的 acceptance audit 从此承担它们。build-pipeline 场景覆盖 US2（单包安装）。

### Scenario: launch at login

- **Given** 用户已在 settings 中启用 launch-at-login
- **When** 用户重新登入机器
- **Then** Coffer 在后台启动，系统托盘图标出现

### Scenario: close to tray, not exit

- **Given** Coffer 正在运行且主窗口打开
- **When** 用户关闭窗口
- **Then** 窗口隐藏；daemon 与托盘图标仍在；MCP 客户端仍可使用 Coffer；从托盘重新打开窗口看到的是同一状态

### Scenario: release tag produces the platform artifact matrix

- **Given** 推送了形如 `v*` 的 release tag
- **When** `.github/workflows/release.yml` 跑完
- **Then** release 含有四份安装包 —— macOS arm64 DMG、macOS x64 DMG、Linux x64（AppImage/deb）、Windows x64（MSI/NSIS）
- **And** 每份安装包旁边都带有 SHA-256 校验文件

### Scenario: post-build smoke test boots shim and gets JSON-RPC reply

- **Given** 从 release 矩阵新构建出的 bundle
- **When** 对其运行 post-build smoke test（`scripts/smoke_test_bundle.sh`）
- **Then** bundle 自带的 `coffer-mcp-shim` 启动，与 bundle 自带的 daemon 完成一次 JSON-RPC `initialize` 交换，状态码 0 退出

## Functional Requirements

- **FR-D01**: Tauri 2 外壳 MUST 在窗口中加载 002 的 Web UI；桌面专用 UI 元素透过 spec 002 已经接好的 `isTauri()` 守卫激活。
- **FR-D02**: 桌面外壳 MUST 按 [ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md) 的 detect-or-spawn 模式监管 daemon —— 读 `~/.coffer/daemon.json` 连接已在跑的 daemon，或在不可达时把 `coffer-daemon` 作为脱离父进程的独立进程拉起（POSIX 用 `setsid`；Windows 用 `DETACHED_PROCESS`）。被拉起的 daemon MUST 在桌面窗口关闭后继续存活。
- **FR-D03**: 桌面外壳 MUST 在应用运行期间常驻一个系统托盘图标。托盘菜单 MUST 至少包含 "Open"、"Restart daemon"、"Quit" 三项。
- **FR-D04**: 窗口关闭事件 MUST 被拦截并转译为 hide-to-tray；关闭主窗口 MUST NOT 终止桌面进程。
- **FR-D05**: 从托盘选 "Quit" MUST 调用 `app.exit()`（或等价平台 API），使桌面进程真正退出，托盘图标随之消失。
- **FR-D06**: 桌面外壳 MUST 集成 `tauri-plugin-autostart` 并支持 set/get 能力，使 `AppSettings` 桌面 tab 能切换「登录时启动」并反映当前状态。
- **FR-D07**: 每次启动，桌面外壳 MUST 幂等地把 bundle 自带的 `coffer-mcp-shim` 部署到稳定的用户可写 PATH 目录（macOS / Linux：`~/.coffer/bin/`；Windows：`%LOCALAPPDATA%\Coffer\bin\`；未设变量时退回 `%USERPROFILE%\Coffer\bin\`）。部署 MUST 保持幂等 —— 磁盘上字节大小一致即 no-op；不一致触发原子替换。
- **FR-D08**: Tauri bundle MUST 把 `coffer-daemon` 与 `coffer-mcp-shim` 声明为 PyInstaller sidecar，写在 `desktop/tauri.conf.json` 的 `bundle.externalBin` 中。运行时无系统 Python 依赖。
- **FR-D09**: release 流水线 MUST 在每个 `v*` tag 上产出四份安装包：macOS arm64 DMG、macOS x64 DMG、Linux x64（AppImage / deb）、Windows x64（MSI / NSIS）。
- **FR-D10**: 每份 release 制品 MUST 在 CI 中生成一份 SHA-256 校验文件随之发布。

## Success Criteria

- **SC-D01**: 冷启动预算 —— 桌面应用启动到主窗口首屏 paint，在 2022 款 MacBook Air（Apple silicon）上：daemon 未在跑时 < 3 秒；daemon 已在跑时 < 1 秒。
- **SC-D02**: bundle 体积预算 —— 每个平台的安装包 < 200 MB。当前观测区间为 90–150 MB（PyInstaller 解释器 + httpx + SQLAlchemy + aiosqlite + keyring + Pydantic + structlog + Typer + Tauri 前端）。
- **SC-D03**: 本文件中的每一个 Acceptance Scenario MUST 至少被一个带有 `acceptance(spec="003-mcp-gateway-desktop", scenario="…")` 标记的测试覆盖，`make verify-acceptance` 报告零未覆盖场景。
- **SC-D04**: post-build smoke test（`scripts/smoke_test_bundle.sh`）MUST 在 release 矩阵每个制品上运行成功 —— bundle 自带的 shim 透过 loopback HTTP 与 bundle 自带的 daemon 通话，得到一次 JSON-RPC `initialize` 回包。

## Distribution

桌面应用以 Tauri 2 bundle 形式分发，把无头 daemon 作为 PyInstaller 构建的 sidecar 二进制包入。架构决策见 [`docs/decisions/ADR-007-distribution-pyinstaller-tauri-sidecar.md`](../../docs/decisions/ADR-007-distribution-pyinstaller-tauri-sidecar.md)；macOS 公证 runbook 见 [`docs/distribution/macos-notarization.md`](../../docs/distribution/macos-notarization.md)。

release 流水线（`.github/workflows/release.yml`）按目标架构运行 PyInstaller，把二进制放入 `desktop/binaries/`，构建 Tauri bundle，公证（macOS，等 Apple Developer ID 就位后启用），并上传制品 + SHA-256 校验文件。
