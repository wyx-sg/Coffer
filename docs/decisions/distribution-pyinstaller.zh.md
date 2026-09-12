# 分发 —— 用 PyInstaller 打包 daemon、shim 与 CLI

> English: [distribution-pyinstaller.md](./distribution-pyinstaller.md)

**Status**: 已采纳 (Accepted)
**Date**: 2026-05-20（2026-09-09 修订，见「修订历史」）
**Deciders**: Yuxing Wu
**Related**: spec `mcp-gateway` (FR-022, SC-009), [Session Subprocess Model](session-subprocess-model.md), [Detect-or-Spawn](daemon-detect-or-spawn.md)

## 背景

Coffer 有三个可运行入口：长生命周期的 `coffer-daemon`、按 MCP 客户端会话
拉起的短生命周期 `coffer-mcp-shim`，以及 `coffer` 管理 CLI。项目的目标
用户群包含没有系统 Python 安装的用户。规范 `mcp-gateway` 明确承诺了
这一点：

- **SC-009** —— 一台干净机器（没有 Python）的用户，从单一发行包出发到达
  `status: ready`，除点击安装器外没有任何手工步骤。

**FR-022** 进一步固定了这份发行包的形态：每个 tag 一份发布归档
`coffer-cli-<triple>.tar.gz`，内含全部可运行二进制。

这就排除了任何要求用户先装 Python、维护 virtualenv 或处理 wheel 构建
错误的方案。我们需要决定 Python 代码以何种方式打包给最终用户。

## 决定

**用 PyInstaller 把 daemon、shim 与管理 CLI 各自打成单文件二进制；由一个
CI 发布任务产出单一下载层级。**

具体选择：

- `backend/coffer-daemon.spec` 构建 `dist/coffer-daemon`（单文件可执行）。
  `backend/coffer-mcp-shim.spec` 构建 `dist/coffer-mcp-shim`。`coffer`
  管理 CLI 同样方式构建。
- `make bundle-binaries`（`scripts/build_binaries.sh`）驱动当前宿主机上的
  PyInstaller；发布 CI 任务在 macOS arm64 runner 上调用同一脚本。
- 每份 spec 都把 FastAPI、SQLAlchemy 2 / aiosqlite、Pydantic 2、`mcp`、
  `keyring`、以及（仅 daemon）Alembic 等运行时实测必需的 `hiddenimports`
  显式钉住。隐藏导入清单记录于 `specs/mcp-gateway/research.md`。
- Alembic 迁移作为数据文件随 daemon 二进制一同打包，以便首次启动时对全新
  DB 跑 `upgrade head`。
- **惰性导入的依赖必须钉进 `hiddenimports`**，因为 PyInstaller 的静态分析看不到
  发生在函数内部的 import —— `markitdown`（入站 channel 文档抽取，spec channels
  FR-030）、`openai`、`langgraph`、`langchain`。包*数据*还需要额外的
  `collect_data_files`，因为 `collect_submodules` 只够得到 Python 模块。
  **2026-09-12 修订：** 本条原本讲的是 sqlite-vec —— 它的
  `vec0.dylib`/`.so`/`.dll` 作为数据文件打包，bundle 冒烟测试会探测
  `coffer-daemon --check-vec`，使丢失该扩展的构建直接失败，而不是把向量检索
  静默降级为仅关键词。知识层已经没有向量索引
  （[Knowledge Is Plain Files](knowledge-is-plain-files.md)），所以这个探测已经
  移除。`backend/coffer-daemon.spec` 里仍留着的那几行 `sqlite_vec` 收集已经不
  服务于任何东西，属于待清理的残留。
- shim 二进制刻意排除 daemon 端的重依赖（FastAPI、uvicorn、SQLAlchemy、
  Alembic、structlog）以保持体积可控 —— shim 只通过 loopback HTTP 与
  daemon 通信，所需仅是 `httpx`。
- daemon 同时以静态文件形式在自己的 loopback origin 上托管构建产物 Web UI
  （spec mcp-gateway FR-024），因此 Web 资源随 daemon 二进制一同分发，而不再依赖
  一个独立外壳。没有额外的 GUI 制品需要构建、签名或安装。
- **daemon 在冻结态启动时部署同目录二进制**（spec mcp-gateway FR-026）。当
  `coffer-daemon` 检测到自己运行自冻结构建时，它会幂等地把同目录的
  `coffer-mcp-shim`、`coffer-callback` 复制到 `~/.coffer/bin/`，
  使用原子的「临时复制再重命名」以及 3 信号陈旧判定（字节大小、mtime、
  版本哨兵）。这既让 MCP 客户端能解析 `command: coffer-mcp-shim` 配置，也
  让 shim 旁边始终有一份 `coffer-daemon`，使冻结态 shim 的 detect-or-spawn
  （[Detect-or-Spawn](daemon-detect-or-spawn.md)）在重启后能找到可启动的
  daemon。由 daemon 承担这件事是自然的：运行期正是它拉起 `coffer-callback`
  。`~/.coffer/bin/` 与 [Detect-or-Spawn](daemon-detect-or-spawn.md)
  里的 `~/.coffer/daemon.json` 共处一处，简化用户心智模型（"Coffer 的所有
  东西都在 `~/.coffer/` 之下"）。源码安装完全不需要这套逻辑 ——
  `pip install` 已经把 console scripts 放到 `PATH` 上（spec mcp-gateway FR-018）。
- macOS 的 Apple 代码签名与公证暂缓（需要付费 Apple Developer ID）。因此
  下载的 CLI 归档仍会受 Gatekeeper 隔离；当前用户侧的绕行是对解压出来的
  二进制执行 `xattr -d com.apple.quarantine`。给 CLI 二进制做签名与公证是
  尚未关闭的后续项。

## 后果

**正面**

- 第一天起就满足 SC-009 与 FR-022：`make bundle-binaries` 产出在干净机器
  上无 Python 也能直接运行的单文件可执行。
- 同一批二进制服务于命令行调用、MCP 客户端拉起、和直接下载，无须维护多条
  分发路径。
- 跨平台一致：同一份 PyInstaller spec 在 macOS、Windows、Linux 上不改动
  即可工作（只 `--target-arch` 与宿主机有差异），因此重新扩大发布矩阵只是
  CI 改动，而非重新设计。
- shim 二进制因排除服务端依赖而保持小巧 —— 对每次会话都重新拉起 shim
  的 MCP 客户端来说很关键。
- 更新成本很低：替换二进制、重启 daemon、浏览器强制刷新即可。不存在一个
  会与源码漂移的独立 GUI 制品。
- 与后续可选的「系统服务安装」（[Detect-or-Spawn](daemon-detect-or-spawn.md) 运维后续）前向兼容：
  launchd / systemd / Windows service 配置都指向同一份二进制路径。

**负面**

- PyInstaller 产出的二进制较大（每平台约 80–120 MB，Python 解释器 + httpx
  - SQLAlchemy + aiosqlite + keyring + Pydantic + structlog + Typer + …）。
    对面向开发者的工具而言可接受。
- PyInstaller 冷启动 ~500–800 ms（对比系统 Python ~100 ms）。daemon 每次
  OS 登录拉起一次、寿命长；shim 每个 MCP 客户端启动拉起一次。两者都在
  人类可感知阈值之内。
- CI 维护成本：每次依赖升级都必须在真实的冻结构建上验证，而不只是在源码
  树上验证。靠 post-build 冒烟测试缓解。
- macOS Gatekeeper 摩擦持续到签名与公证启用为止。目前用户侧的绕行是对
  解压出来的二进制执行 `xattr -d com.apple.quarantine`。
- PyInstaller 的隐藏导入发现靠经验积累；首次引入新 Python 依赖
  （特别是 Pydantic / SQLAlchemy 升级）可能需要重新走一遍 import graph。
  缓解：在 `research.md` 与 `backend/coffer-*.spec` 中钉住清单，并在 CI
  中跑 bundle smoke test（[`scripts/smoke_test_bundle.sh`](../../scripts/smoke_test_bundle.sh) ——
  把 bundle 自带的 daemon 启动到 `status: ready` 并与 bundle 自带的 shim
  完成一次 JSON-RPC `initialize`）。

**运维后续**

- 每个 `v*` tag，CI 发布任务只产出一份归档 —— macOS arm64 的
  `coffer-cli-<triple>.tar.gz`，内含 `coffer`、`coffer-daemon`、
  `coffer-mcp-shim` 以及运行期辅助二进制（`coffer-callback`）
  —— 外加一份覆盖全部发布制品的聚合 `SHA256SUMS`（spec mcp-gateway FR-022 / FR-023）。
- 每次发布前都对 bundle 跑一次 post-build smoke test
  ([`scripts/smoke_test_bundle.sh`](../../scripts/smoke_test_bundle.sh)) ——
  必须能在 loopback 上启动 bundle 自带的 daemon 到 `status: ready`，并
  让 bundle 自带的 shim 完成一次 JSON-RPC `initialize`。
- shim 二进制路径通过 `coffer daemon status`（以及 daemon 托管的 Web UI）
  暴露给用户，以便粘贴进 MCP 客户端配置。

## 备选方案

**要求系统 Python 3.12+ 与一个 venv（`pip install coffer`）**。被否决。

- 直接违反 SC-009。Windows 上以及大多数设计师 / 非开发者背景的
  macOS 用户没有可工作的 Python 安装，更别说我们要求的版本了。
- 即便在 Linux 上，发行版自带的 Python 通常落后我们一个大版本；用户会
  撞上 `aiosqlite` 或 `pydantic-core` 的 wheel 构建错误。
- 面向贡献者的开发者安装路径（`pip install -e ./backend`）依然
  在文档中保留 —— 但它不是面向终端用户的分发渠道。

**用 Nuitka 或 PyOxidizer 取代 PyInstaller**。v0 暂否决。

- PyInstaller 对我们的依赖集合（FastAPI、SQLAlchemy async、`mcp`、
  `keyring` backends）支持最广，社区里隐藏导入的配方也最齐全。Nuitka 的
  AOT 编译诱人，但会让构建周期更长，并在 CI 中引入平台相关的编译器依赖。
- 后续换打包工具是一个有边界、可逆的改动：daemon 的运行时契约里没有
  任何东西特别绑定 PyInstaller。

**多个下载层级（在 CLI 归档之外再发一个 GUI 安装包）**。被否决。

- 多一个层级就意味着多一份要构建、要验证、还要与另一份保持同步的制品。
  真正发布的就是单一的 `coffer-cli-<triple>.tar.gz` 层级：它能在服务器上
  headless 运行；而因为 daemon 自己就托管 Web UI，它同时也是完整的图形界面
  安装方式。
- 对从 checkout 工作的开发者，`pip install -e ./backend` 仍是文档化路径；
  他们完全绕开 PyInstaller。

## 修订历史

- **2026-05-20** —— 初版决定（spec mcp-gateway 时期）：PyInstaller 二进制、
  计划做 universal macOS binary、macOS 上 shim 路径在
  `~/Library/Application Support/Coffer/bin/`。
- **2026-05-28** (PR #28) —— 按实现现实修订：
  (a) macOS 改为两份独立的按架构制品，不再做 universal binary（release
  流水线没跑 `lipo`）；(b) macOS / Linux 上 shim 路径移到 `~/.coffer/bin/`
  与 Detect-or-Spawn 的 `~/.coffer/daemon.json` 共处一处；(c) 明确写出每次发布
  的制品数量，每个伴随 SHA-256 校验文件；
  (d) 恢复对 [`scripts/build_binaries.sh`](../../scripts/build_binaries.sh)
  与 [`scripts/smoke_test_bundle.sh`](../../scripts/smoke_test_bundle.sh)
  的交叉引用。
- **2026-05-30** —— CLI 层级扩展：release 现在发布**三份** PyInstaller
  二进制 —— 在原有 `coffer-daemon` + `coffer-mcp-shim` 之外新增 `coffer`
  管理 CLI。`coffer` 管理 CLI 此前仅可通过 `pip install -e ./backend` 获取，
  现已作为 CLI 层级的一等成员正式发布。归档
  （`coffer-cli-<triple>.tar.gz`）通过一行脚本（`install.sh`，从
  `https://wyx-sg.github.io/Coffer/` 提供）安装到 `~/.coffer/bin`；脚本同时
  自动将 `~/.coffer/bin` 添加到 `PATH`。支持的环境变量覆盖：
  `COFFER_INSTALL_DIR`、`COFFER_VERSION`、`COFFER_NO_MODIFY_PATH`。
- **2026-06-05** —— 发布范围收窄为**仅 macOS（Apple Silicon）**。Linux 与
  Windows 的 release matrix leg 从未端到端验证过，因此从 `release.yml` 中
  移除，而非未经测试就发布。这里的 PyInstaller 机制本身不变、与平台无关；
  待各目标真正测试通过后可再启用。
- **2026-06-12** —— 二进制部署改为把 shim 与 daemon **两份**都发到用户
  bin 目录：`coffer-daemon` 与 `coffer-mcp-shim` 一起复制到 `~/.coffer/bin/`
  （沿用同一套幂等的原子替换 + 版本哨兵逻辑），使冻结态 shim 的
  Detect-or-Spawn 同目录探测在重启后能找到可自启的 daemon。
- **2026-09-09** —— **桌面外壳被移除，本 ADR 收敛为纯 PyInstaller 分发
  决定。** 这个判断针对的是**每次更新的运维成本**，而不是代码行数：桌面端
  每次更新都要重新构建再重新安装，而构建产物又不断与源码漂移。有两起在案
  的事故 —— 一次是在 `git fetch` 之前做的构建产出了跑着旧代码的应用；另一
  次是单独 pin 住的构建目录，导致 UI bug 报告必须先对 `main` 重新验证才能
  采信。Web 形态没有这两种失效模式：重启 daemon、浏览器强制刷新，你就在当前
  代码上。（佐证数据：`desktop/` 下的 15 次提交里有 7 次是修复，是全项目最高
  比例 —— 不过都发生在建设期，且该目录已两个月未变。所以这移除的是一项长期
  的运维税，而不是一处正在流血的伤口。）具体地：
  (a) 决定中的 Tauri-sidecar 部分整体消失 —— `bundle.externalBin`、sidecar
  的 triple 后缀命名、`desktop/tauri.conf.json`，以及
  DMG / MSI / AppImage / deb 打包都不再存在；
  (b) 发布收敛为**单一层级** —— 每个 `v*` tag 一份
  `coffer-cli-<triple>.tar.gz`，外加一份覆盖全部制品的聚合 `SHA256SUMS`
  （spec mcp-gateway FR-022 / FR-023）；`.dmg` 与
  `Coffer-unsigned-<triple>.app.zip` 退役；
  (c) 向 `~/.coffer/bin/` 的二进制部署**移入 daemon 的冻结态启动路径**
  （spec mcp-gateway FR-026），沿用同一套原子「临时复制再重命名」与同一套 3 信号
  陈旧判定，并新增覆盖 `coffer-callback`；
  (d) macOS 公证 runbook（`docs/distribution/macos-notarization.md`）被删除
  —— 其中每一步都是 `cargo tauri build` / `.dmg` 签名与 staple，对应的流水线
  已不存在；CLI 归档的 Gatekeeper 隔离与 `xattr -d com.apple.quarantine`
  绕行方式改为在上文内联说明。
  MCP Gateway Desktop 规范退役；其中仅存的两条发布流水线需求并入
  spec mcp-gateway。
