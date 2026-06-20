# 实施计划：003 —— MCP Gateway Desktop

> English: [plan.md](./plan.md)

**Branch**: `feature/003-mcp-gateway-desktop`
**Spec**: [./spec.zh.md](./spec.zh.md)
**Status**: Accepted

## 概要

把 002 的 Web UI 包进一个 Tauri 2 桌面外壳，按
[ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md) 的
detect-or-spawn 模式监管无头 daemon，在每次启动把 bundle 自带的
`coffer-mcp-shim` 部署到稳定的用户可写 PATH 目录，并把成品以两个下载层级
分发，二者都基于同一组 PyInstaller 二进制构建，**仅发布 macOS arm64**：
一份 **CLI-only** 的 `coffer-cli-<triple>.tar.gz` 归档（含 `coffer` +
`coffer-daemon` + `coffer-mcp-shim`，用于 headless 安装），以及一份
**CLI+desktop** 的 Tauri bundle（未签名 macOS arm64 `.dmg`）。PyInstaller
构建的 daemon + shim 二进制以
[ADR-008](../../docs/decisions/ADR-008-distribution-pyinstaller-tauri-sidecar.md)
约定的 `bundle.externalBin` sidecar 方式装入 Tauri bundle。

本规范不引入任何新的后端、新的 resource kind 或新的 UI 屏幕。

用户可见契约见 [./spec.zh.md](./spec.zh.md)；最终用户上手见
[./quickstart.zh.md](./quickstart.zh.md)；分发架构决策见
[ADR-008](../../docs/decisions/ADR-008-distribution-pyinstaller-tauri-sidecar.zh.md)。

## 技术上下文

| 维度               | 取值                                                                                                                                                                                               |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **语言 / 版本**    | Rust 1.78+（Tauri 2 crate）；复用 daemon / shim 的 Python 3.12（PyInstaller 打包）。                                                                                                               |
| **主要依赖**       | Tauri 2 (`tauri`, `tauri-build`)；按需 `tauri-plugin-shell`（sidecar spawn）；002 的前端 bundle（从 `dist/` 加载）。                               |
| **Sidecar 二进制** | `coffer-daemon` 与 `coffer-mcp-shim`，由 `scripts/build_binaries.sh` 驱动 `backend/` 下的 PyInstaller spec 跨平台构建。                                                                            |
| **Daemon 发现**    | `~/.coffer/daemon.json`（port + token + pid），与 CLI、shim 共享。见 [ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.zh.md)。                                                        |
| **Shim PATH 目录** | macOS / Linux：`~/.coffer/bin/`。Windows：`%LOCALAPPDATA%\Coffer\bin\`（未设时退回 `%USERPROFILE%\Coffer\bin\`）。                                                                                 |
| **测试**           | Rust 单元测试（`#[cfg(test)]`）覆盖 shim-deploy、daemon-supervisor、tray-handler；`make dev-tauri` 下用 Playwright（`e2e/`）跑托盘与窗口场景；CI 跑 smoke test（`scripts/smoke_test_bundle.sh`）。 |
| **目标平台**       | 仅 macOS 12+ arm64（Apple Silicon）—— 一份未签名 `.dmg`。macOS x64、Linux、Windows 不构建（见构建矩阵）。                                                                                          |
| **工程类型**       | 包裹一个 SPA 的原生桌面外壳。Tauri crate 位于 `desktop/`；前端 bundle 是 `frontend/dist/`（由 002 的 Vite 流水线构建）。                                                                           |
| **性能目标**       | 冷启动 < 3 秒（daemon 未跑时）、< 1 秒（daemon 已跑时），见 SC-D01。PyInstaller sidecar 决定了冷启动下限。                                                                                         |
| **约束**           | local-first（daemon 仅 loopback）；不访问公共互联网；不接埋点。每份 bundle ≤ 200 MB（SC-D02）。无新增章程级依赖 —— 选择均已被 ADR-006 / ADR-008 批准。                                             |
| **规模 / 范围**    | 单用户桌面；一个 daemon 进程；每个 MCP 客户端一个 shim；≤ 30 个注册资源（与 001 / 002 上限一致）。                                                                                                 |

## 章程检查 (Constitution Check)

| 章程条款                            | 合规 | 备注                                                                                                                                         |
| ----------------------------------- | ---- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **I. Local-First (NON-NEGOTIABLE)** | OK   | daemon 仍仅 loopback；桌面外壳不访问公共互联网；不会出现遥测 / 更新服务器调用。                                                             |
| **II. Spec-as-Truth**               | OK   | spec 在代码之前提交；每个验收场景都有覆盖测试（acceptance audit）。                                                                          |
| **III. Open-Source-Readiness**      | OK   | Tauri 2（MIT/Apache-2.0）为宽松许可证；PyInstaller 是 GPL 但带运行时例外，不污染 bundle 出来的二进制。   |
| **语言**                            | OK   | 章程 Languages 条款允许桌面外壳用 Rust；daemon 与 shim 仍是 Python 3.12。                                                                    |
| **架构：分层**                      | OK   | 桌面 crate 是薄薄一层 —— supervisor、tray、shim-deploy 各自有模块；视图层来自 002 的 Web UI。                                                |
| **持久化：SQLite 作为控制面**       | OK   | 本规范不拥有持久化；daemon 拥有。外壳读 `~/.coffer/daemon.json`（不是 SQLite）发现 daemon —— 该发现文件是 ADR-006 拥有的运行时契约的一部分。 |
| **凭据：加密存储**                  | OK   | 本规范不拥有凭据。                                              |
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
release 流水线 —— 每个独立 PR）。

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
│   ├── daemon.rs                     # detect-or-spawn helper（POSIX setsid / Windows DETACHED_PROCESS）
│   ├── shim.rs                       # 幂等 shim 拷贝 + size-mismatch 启发式
│   └── tray.rs                       # 托盘菜单（Open / Restart daemon / Quit）
└── tests/                            # 上述模块的 Rust 单元测试

scripts/
├── build_binaries.sh                 # 驱动 backend/ 下的 PyInstaller spec（本 PR 新增）
└── smoke_test_bundle.sh              # CI post-build smoke test（本 PR 新增）

.github/workflows/
└── release.yml                       # 仅 macOS-arm64 的 release 矩阵 + 聚合的 SHA256SUMS
```

### 扩展点：daemon-supervisor 模块

`desktop/src/daemon.rs` 是 CLI / shim 所用 Python
`detect-or-spawn` helper 的 Rust 镜像。它读 `~/.coffer/daemon.json`、
探测记录的 PID、在找不到存活 daemon 时把 `coffer-daemon` 作为脱离父进程
的独立进程拉起。"脱离" 在 POSIX 上是 `setsid`，在 Windows 上是
`CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS` —— 这正是让 daemon 在窗口
close-to-tray 之后仍然存活的关键。

### Shim 部署策略

`desktop/src/shim.rs` 在每次桌面启动时运行：

1. 解析目标目录（macOS/Linux：`~/.coffer/bin/`；Windows：
   `%LOCALAPPDATA%\Coffer\bin\`；`%LOCALAPPDATA%` 未设时退回
   `%USERPROFILE%\Coffer\bin\`）。
2. 在 bundle 内探测 `coffer-mcp-shim` sidecar 二进制。先看 sidecar
   的期望位置，再向上一级目录探测 —— Tauri 在 dev (`target/debug/`)
   与 release (`Resources/`) 下放 sidecar 的相对路径不同。
3. 比较 bundle 自带 shim 的字节大小与磁盘上的 shim（若存在）。
   一致 → no-op。不一致 → 原子替换（`tempfile` + `rename`）。

PATH 是否包含目标目录的提示，在首次启动时显示一次；外壳只负责把二进制放到目标目录。

### 构建矩阵

构建矩阵**仅发布 macOS arm64**。它只运行一次 PyInstaller，随后从同一组
二进制产出两个下载层级：CLI-only 归档与桌面安装包。

| 平台  | 架构  | CLI-only 归档                | 桌面安装包         | 构建宿主        |
| ----- | ----- | ---------------------------- | ------------------ | --------------- |
| macOS | arm64 | `coffer-cli-<triple>.tar.gz` | `.dmg`（未签名）   | macos-14 runner |

`<triple>` 是构建 triple `aarch64-apple-darwin`。CLI-only 归档含 `coffer`、
`coffer-daemon` 与 `coffer-mcp-shim`。DMG 与打包的 `.app` 因没有接入
签名 / 公证而被重命名为 `*-unsigned`。单个聚合的 `SHA256SUMS` 文件（而非逐
制品的 `.sha256` 兄弟文件）覆盖每一份制品。

macOS x64（Intel）刻意不构建 —— Intel runner 池正在被弃用且会让 job 长期
饿死，且 PyInstaller 无法从 arm64 runner 交叉编译 x86_64 sidecar。Linux 与
Windows bundle 不发布 —— 那些 leg 从未验证过。acceptance 矩阵断言只构建
macOS-arm64。签名 / 公证在拿到付费 Apple Developer ID 之后由一条单独的签名
发布 workflow 加入（见
[`docs/distribution/macos-notarization.zh.md`](../../docs/distribution/macos-notarization.zh.md)）。

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

`daemon.rs` —— 对 `~/.coffer/daemon.json` 执行 detect-or-spawn；
detached spawn（`setsid` / `DETACHED_PROCESS`）。

**完成标志**：外壳能连接到已在跑的 daemon 而不重复拉起；没在跑时能拉起一个；
被拉起的 daemon 在桌面应用关闭后仍存活（US3 场景）。

### Phase 3 —— 托盘菜单 + close-to-tray

`tray.rs`（Open / Restart daemon / Quit），`lib.rs` 中的窗口关闭拦截。

**完成标志**：US5 的托盘场景通过；US1 的 "close to tray, not exit" 通过。

### Phase 4 —— Shim 自动部署

`shim.rs` —— 幂等拷贝 + size-mismatch 启发式、父目录探测、
Windows PATH 兜底。

**完成标志**：US4 的三个场景通过。

### Phase 5 —— Release 流水线 + smoke test

`.github/workflows/release.yml` 跑 macOS-arm64 构建 leg；它把三份二进制
（`coffer`、`coffer-daemon`、`coffer-mcp-shim`）打成 `coffer-cli-<triple>.tar.gz`
归档并构建未签名桌面 bundle；每一份制品由单个聚合的 `SHA256SUMS` 文件覆盖；
对 bundle 运行 `scripts/smoke_test_bundle.sh`。

**完成标志**：US2 的两个 build-pipeline 场景通过；在某个 `v*-rc` tag 上
打 draft release 时 CLI-only 归档与 macOS-arm64 桌面 bundle 全绿。

## 复杂度记录

| 决策                                                          | 为什么需要                                                                                                                            | 更简单方案被否的原因                                                                                                                              |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tauri 2 而非 Electron                                         | bundle 更小（不内嵌 Chromium）、原生 OS 控件、Rust 内核 —— 契合 Coffer「本地优先 + 轻量」的定位。                                     | Electron 会在 PyInstaller sidecar 之上再加 ~150 MB 并引入完整 Node 运行时；002 的视觉语言润色不需要 Chromium 特有功能。                           |
| 脱离父进程的 daemon spawn（setsid / DETACHED_PROCESS）        | 让 daemon 在窗口 close-to-tray 后仍存活的必要条件 —— 否则 OS 进程树清理会在 Tauri 进程退出时连带杀掉 daemon。                         | 前台子进程会破坏 close-to-tray 场景；reparent 到 PID 1 正是 `setsid` 与 `DETACHED_PROCESS` 的用途。                                               |
| 每次启动幂等 shim 部署                                        | 桌面外壳是唯一知道 bundle 自带 shim 在哪的入口；只在安装时部署一次会错过原地升级。                                                    | 独立的 "shim updater" 服务会增加运动部件；size-mismatch 启发式只有几行代码，shim 已最新时在微秒级完成。                                           |
| 仅 macOS arm64（不做 x64 / Linux / Windows leg）             | Intel runner 池正在被弃用且会饿死 job，PyInstaller 无法从 arm64 交叉编译 x86_64 sidecar，且 Linux/Windows leg 从未验证过。           | 发布未验证的跨平台 bundle 等于发出没人测过的制品；矩阵刻意收敛到唯一已验证的目标，直到其他目标被接好并验证。                                       |

## 交叉引用索引

- Spec 契约：[spec.zh.md](./spec.zh.md)
- Quickstart：[quickstart.zh.md](./quickstart.zh.md)
- 分发决策：[ADR-008](../../docs/decisions/ADR-008-distribution-pyinstaller-tauri-sidecar.zh.md)
- Daemon detect-or-spawn：[ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.zh.md)
- macOS 公证 runbook：[`docs/distribution/macos-notarization.zh.md`](../../docs/distribution/macos-notarization.zh.md)
- Web UI 宿主：[`specs/002-ui-shell/spec.zh.md`](../002-ui-shell/spec.zh.md)
- 架构总览：[`.specify/memory/architecture.zh.md`](../../.specify/memory/architecture.zh.md)
- 章程：[`.specify/memory/constitution.zh.md`](../../.specify/memory/constitution.zh.md)
