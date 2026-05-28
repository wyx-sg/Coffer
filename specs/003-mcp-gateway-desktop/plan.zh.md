# 实施计划：003 —— MCP Gateway Desktop

> English: [plan.md](./plan.md)

**Branch**: `feature/003-mcp-gateway-desktop`
**Date**: 2026-05-28
**Spec**: [./spec.zh.md](./spec.zh.md)
**Status**: Accepted

## 概要

把 002 的 Web UI 包进一个 Tauri 2 桌面外壳，按
[ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md) 的
detect-or-spawn 模式监管无头 daemon，在每次启动把 bundle 自带的
`coffer-mcp-shim` 部署到稳定的用户可写 PATH 目录，并把成品打包为
单包安装器：macOS（arm64 + x64）、Linux x64、Windows x64。
PyInstaller 构建的 daemon + shim 二进制以
[ADR-007](../../docs/decisions/ADR-007-distribution-pyinstaller-tauri-sidecar.md)
约定的 `bundle.externalBin` sidecar 方式装入 Tauri bundle。

本规范不引入任何新的后端、新的 resource kind 或新的 UI 屏幕。002
在 `isTauri()` 守卫后已经接好的桌面专用 `AppSettings` 组件是前端
唯一需要触碰的位置。

用户可见契约见 [./spec.zh.md](./spec.zh.md)；最终用户上手见
[./quickstart.zh.md](./quickstart.zh.md)；分发架构决策见
[ADR-007](../../docs/decisions/ADR-007-distribution-pyinstaller-tauri-sidecar.zh.md)。

## 技术上下文

| 维度               | 取值                                                                                                                                                                                               |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **语言 / 版本**    | Rust 1.78+（Tauri 2 crate）；复用 daemon / shim 的 Python 3.12（PyInstaller 打包）。                                                                                                               |
| **主要依赖**       | Tauri 2 (`tauri`, `tauri-build`)；`tauri-plugin-autostart`（登录时启动 set/get）；按需 `tauri-plugin-shell`（sidecar spawn）；002 的前端 bundle（从 `dist/` 加载）。                               |
| **Sidecar 二进制** | `coffer-daemon` 与 `coffer-mcp-shim`，由 `scripts/build_binaries.sh` 驱动 `backend/` 下的 PyInstaller spec 跨平台构建。                                                                            |
| **Daemon 发现**    | `~/.coffer/daemon.json`（port + token + pid），与 CLI、shim 共享。见 [ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.zh.md)。                                                        |
| **Shim PATH 目录** | macOS / Linux：`~/.coffer/bin/`。Windows：`%LOCALAPPDATA%\Coffer\bin\`（未设时退回 `%USERPROFILE%\Coffer\bin\`）。                                                                                 |
| **测试**           | Rust 单元测试（`#[cfg(test)]`）覆盖 shim-deploy、daemon-supervisor、tray-handler；`make dev-tauri` 下用 Playwright（`e2e/`）跑托盘与窗口场景；CI 跑 smoke test（`scripts/smoke_test_bundle.sh`）。 |
| **目标平台**       | macOS 12+（arm64 + x64，独立 DMG）；Linux x64（AppImage + deb）；Windows 10+ x64（MSI + NSIS）。                                                                                                   |
| **工程类型**       | 包裹一个 SPA 的原生桌面外壳。Tauri crate 位于 `desktop/`；前端 bundle 是 `frontend/dist/`（由 002 的 Vite 流水线构建）。                                                                           |
| **性能目标**       | 冷启动 < 3 秒（daemon 未跑时）、< 1 秒（daemon 已跑时），见 SC-D01。PyInstaller sidecar 决定了冷启动下限。                                                                                         |
| **约束**           | local-first（daemon 仅 loopback）；不访问公共互联网；不接埋点。每份 bundle ≤ 200 MB（SC-D02）。无新增章程级依赖 —— 选择均已被 ADR-006 / ADR-007 批准。                                             |
| **规模 / 范围**    | 单用户桌面；一个 daemon 进程；每个 MCP 客户端一个 shim；≤ 30 个注册资源（与 001 / 002 上限一致）。                                                                                                 |

## 章程检查 (Constitution Check)

| 章程条款                            | 合规 | 备注                                                                                                                                         |
| ----------------------------------- | ---- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **I. Local-First (NON-NEGOTIABLE)** | OK   | daemon 仍仅 loopback；桌面外壳不访问公共互联网。auto-update 明确划出范围，因此不会出现遥测 / 更新服务器调用。                                |
| **II. Spec-as-Truth**               | OK   | spec 在代码之前提交；每个验收场景都有覆盖测试（acceptance audit）。                                                                          |
| **III. Open-Source-Readiness**      | OK   | Tauri 2（MIT/Apache-2.0）与 `tauri-plugin-autostart`（MIT）均为宽松许可证；PyInstaller 是 GPL 但带运行时例外，不污染 bundle 出来的二进制。   |
| **语言**                            | OK   | 章程 Languages 条款允许桌面外壳用 Rust；daemon 与 shim 仍是 Python 3.12。                                                                    |
| **架构：分层**                      | OK   | 桌面 crate 是薄薄一层 —— supervisor、tray、shim-deploy 各自有模块；视图层来自 002 的 Web UI。                                                |
| **持久化：SQLite 作为控制面**       | OK   | 本规范不拥有持久化；daemon 拥有。外壳读 `~/.coffer/daemon.json`（不是 SQLite）发现 daemon —— 该发现文件是 ADR-006 拥有的运行时契约的一部分。 |
| **凭据：仅 keychain**               | OK   | 本规范不拥有凭据。autostart 偏好由 `tauri-plugin-autostart`（OS 原生设施）存储，不进 keychain。                                              |
| **网络默认：仅 loopback**           | OK   | 外壳只与 daemon.json 中的 `127.0.0.1:<port>` 通话；不访问其他 HTTP origin。                                                                  |

## 工程结构

### 文档（本特性）

```text
specs/003-mcp-gateway-desktop/
├── spec.md / spec.zh.md           # 用户可见契约
├── plan.md / plan.zh.md           # 本文件
└── quickstart.md / quickstart.zh.md   # 最终用户上手（下载 → 安装 → 首次启动 → 托盘）
```

本目录刻意不含 `data-model.md`（本规范无后端数据）也不含 `tasks.md`
（工作按用户故事 / PR 切，单位是「一个桌面关切」——shim 部署、托盘、
autostart、release 流水线 —— 每个独立 PR）。

### 源代码（本 PR 交付）

```text
desktop/
├── Cargo.toml                        # Tauri 2 crate
├── tauri.conf.json                   # 窗口、bundle.externalBin sidecars、macOS signingIdentity 占位
├── icons/                            # 平台托盘 + 应用图标 + 兜底 PNG
├── binaries/                         # PyInstaller 产物落点（gitignore；CI 中填充）
├── src/
│   ├── main.rs                       # 入口 —— tauri::Builder
│   ├── lib.rs                        # app 启动、托盘菜单接线、窗口关闭拦截
│   ├── daemon_supervisor.rs          # detect-or-spawn helper（POSIX setsid / Windows DETACHED_PROCESS）
│   ├── shim_deploy.rs                # 幂等 shim 拷贝 + size-mismatch 启发式
│   └── tray.rs                       # 托盘菜单（Open / Restart daemon / Quit）
└── tests/                            # 上述模块的 Rust 单元测试

scripts/
├── build_binaries.sh                 # 驱动 backend/ 下的 PyInstaller spec（来自 001）
└── smoke_test_bundle.sh              # CI post-build smoke test（已存在）

.github/workflows/
└── release.yml                       # 跨平台 release 矩阵 + 逐制品 SHA-256
```

### 扩展点：daemon-supervisor 模块

`desktop/src/daemon_supervisor.rs` 是 CLI / shim 所用 Python
`detect-or-spawn` helper 的 Rust 镜像。它读 `~/.coffer/daemon.json`、
探测记录的 PID、在找不到存活 daemon 时把 `coffer-daemon` 作为脱离父进程
的独立进程拉起。"脱离" 在 POSIX 上是 `setsid`，在 Windows 上是
`CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS` —— 这正是让 daemon 在窗口
close-to-tray 之后仍然存活的关键。

### Shim 部署策略

`desktop/src/shim_deploy.rs` 在每次桌面启动时运行：

1. 解析目标目录（macOS/Linux：`~/.coffer/bin/`；Windows：
   `%LOCALAPPDATA%\Coffer\bin\`；`%LOCALAPPDATA%` 未设时退回
   `%USERPROFILE%\Coffer\bin\`）。
2. 在 bundle 内探测 `coffer-mcp-shim` sidecar 二进制。先看 sidecar
   的期望位置，再向上一级目录探测 —— Tauri 在 dev (`target/debug/`)
   与 release (`Resources/`) 下放 sidecar 的相对路径不同。
3. 比较 bundle 自带 shim 的字节大小与磁盘上的 shim（若存在）。
   一致 → no-op。不一致 → 原子替换（`tempfile` + `rename`）。

PATH 是否包含目标目录的提示，由 002 的 `AppSettings` tab 在首次启动时
显示一次；外壳只负责把二进制放到目标目录。

### 构建矩阵

| 平台    | 架构  | 安装包格式             | 跨平台宿主 runner   |
| ------- | ----- | ---------------------- | ------------------- |
| macOS   | arm64 | `.dmg`                 | macos-14 runner     |
| macOS   | x64   | `.dmg`                 | macos-13 runner     |
| Linux   | x64   | `.AppImage`、`.deb`    | ubuntu-22.04 runner |
| Windows | x64   | `.msi`、`.exe`（NSIS） | windows-2022 runner |

每份制品都伴随一份 `<artifact>.sha256` 校验文件，由同一个 job step 生成。
macOS 公证仅当 Apple Developer secrets 存在时才运行（见
[`docs/distribution/macos-notarization.zh.md`](../../docs/distribution/macos-notarization.zh.md)）；
在 secrets 就位之前，DMG 以未签名形式继续发布。

### 文件体积上限

- 每份 Tauri bundle ≤ 200 MB（SC-D02）。当前观测：90–150 MB。
- 每份 PyInstaller sidecar ≤ 100 MB。当前观测：daemon ~70 MB、shim ~30 MB。
- `desktop/src/` 中每份 Rust 源文件 ≤ 250 LOC（由 `scripts/check_file_sizes.py` 强制）。

## 阶段（高层）

阶段是**交付边界**，不是原子任务拆分。

### Phase 1 —— Tauri 外壳 + 前端挂载

`tauri.conf.json`（窗口、sidecar、图标）、`desktop/src/main.rs` + `lib.rs`、
Vite 前端挂载。

**完成标志**：`cargo tauri dev` 在 Tauri 窗口里启动 002 的 Web UI；
首次渲染时 `isTauri()` 为 true。

### Phase 2 —— Daemon supervisor

`daemon_supervisor.rs` —— 对 `~/.coffer/daemon.json` 执行 detect-or-spawn；
detached spawn（`setsid` / `DETACHED_PROCESS`）。

**完成标志**：外壳能连接到已在跑的 daemon 而不重复拉起；没在跑时能拉起一个；
被拉起的 daemon 在桌面应用关闭后仍存活（US7 场景）。

### Phase 3 —— 托盘菜单 + close-to-tray

`tray.rs`（Open / Restart daemon / Quit），`lib.rs` 中的窗口关闭拦截。

**完成标志**：US9 的托盘场景通过；US5 的 "close to tray, not exit" 通过。

### Phase 4 —— Autostart + AppSettings 接线

集成 `tauri-plugin-autostart`，把 set/get 暴露到 JS 桥；002 的
`AppSettings` 组件拾取该开关。

**完成标志**：US5 的 "launch at login" 通过。

### Phase 5 —— Shim 自动部署

`shim_deploy.rs` —— 幂等拷贝 + size-mismatch 启发式、父目录探测、
Windows PATH 兜底。

**完成标志**：US8 的三个场景通过。

### Phase 6 —— Release 流水线 + smoke test

`.github/workflows/release.yml` 跑构建矩阵；每份制品伴随 SHA-256；
对每份 bundle 运行 `scripts/smoke_test_bundle.sh`。

**完成标志**：US6 的两个 build-pipeline 场景通过；在某个 `v*-rc` tag 上
打 draft release 时四份安装包全绿。

## 复杂度记录

| 决策                                                          | 为什么需要                                                                                                                            | 更简单方案被否的原因                                                                                                                              |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tauri 2 而非 Electron                                         | bundle 更小（不内嵌 Chromium）、原生 OS 控件、Rust 内核 —— 契合 Coffer「本地优先 + 轻量」的定位。                                     | Electron 会在 PyInstaller sidecar 之上再加 ~150 MB 并引入完整 Node 运行时；002 的视觉语言润色不需要 Chromium 特有功能。                           |
| 脱离父进程的 daemon spawn（setsid / DETACHED_PROCESS）        | 让 daemon 在窗口 close-to-tray 后仍存活的必要条件 —— 否则 OS 进程树清理会在 Tauri 进程退出时连带杀掉 daemon。                         | 前台子进程会破坏 close-to-tray 场景；reparent 到 PID 1 正是 `setsid` 与 `DETACHED_PROCESS` 的用途。                                               |
| 每次启动幂等 shim 部署                                        | 桌面外壳是唯一知道 bundle 自带 shim 在哪的入口；只在安装时部署一次会错过原地升级。                                                    | 独立的 "shim updater" 服务会增加运动部件；size-mismatch 启发式只有几行代码，shim 已最新时在微秒级完成。                                           |
| macOS 两份独立 DMG（arm64 + x64），不做 universal binary      | Tauri 2 的 release 流水线一次 `cargo tauri build` 产出一份 DMG；universal DMG 需要额外的 `lipo` 后处理步骤，目前没在跑。              | universal binary 能把 macOS 下载次数减半，但代价是每个用户的下载体积翻倍并让 release 矩阵更复杂；两份 DMG 更简单，也与当前 release.yml 行为一致。 |
| 用 `tauri-plugin-autostart` 而非自手 launchd / Task Scheduler | 跨平台 launch-at-login 并不简单（launchd plist + systemd user unit + Windows Task Scheduler / Run key）；该插件已经被维护并通过测试。 | 自己撸三套平台逻辑会让 bug 表面与测试量乘三，却没有功能收益。                                                                                     |

## 交叉引用索引

- Spec 契约：[spec.zh.md](./spec.zh.md)
- Quickstart：[quickstart.zh.md](./quickstart.zh.md)
- 分发决策：[ADR-007](../../docs/decisions/ADR-007-distribution-pyinstaller-tauri-sidecar.zh.md)
- Daemon detect-or-spawn：[ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.zh.md)
- macOS 公证 runbook：[`docs/distribution/macos-notarization.zh.md`](../../docs/distribution/macos-notarization.zh.md)
- Web UI 宿主：[`specs/002-ui-shell/spec.zh.md`](../002-ui-shell/spec.zh.md)
- 架构总览：[`.specify/memory/architecture.zh.md`](../../.specify/memory/architecture.zh.md)
- 章程：[`.specify/memory/constitution.zh.md`](../../.specify/memory/constitution.zh.md)
