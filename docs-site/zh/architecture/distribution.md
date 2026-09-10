# 分发

::: tip 核心锚点
Coffer 只以**一个层级**分发：一个由 PyInstaller 二进制文件组成的 `coffer-cli-<triple>.tar.gz` 压缩包，随每个 `v*` tag 发布，并附带一份聚合的 `SHA256SUMS`。它不需要用户机器上预装 Python；管理界面是一个由 **daemon 自己提供**的 Web UI —— 没有需要单独安装和升级的桌面应用。
:::

## 这解决了什么问题

Coffer 的 daemon 和 shim 是 Python 应用程序。目标用户群体包括：完全没有安装 Python 3.12 的开发者，以及只有系统自带 Python（通常落后一两个版本）的 macOS 用户。要求这些用户 `pip install coffer` 并管理虚拟环境，会立刻让 Coffer 失去作为日常工具的资格。

规范中对此有精确的要求：一个完全没有安装 Python 的用户，能够从单个可下载的工件出发，除解压之外无需任何手动步骤，就能让系统达到 `status: ready`。

## 为什么不再有桌面外壳

Coffer 曾经发布过第二个层级 —— 一个把 Web UI 内嵌进原生窗口的 Tauri 2 桌面应用。它已被移除，而这个判断针对的是**每一次更新的运维成本**，不是代码行数。

产品的每一处改动都必须先经过一次重新构建**再加**一次重新安装才能被看到，而构建出的产物还会不断和源码发生偏离。有两次事故被记录在案：一次构建在 fetch 之前完成，发布出的应用悄悄跑着陈旧的代码；另外，由于应用是从一个单独固定的目录构建的，UI 缺陷报告必须先对着 `main` 复核一遍才能采信。这两种失效模式在 Web 形态下都不存在：重启 daemon，浏览器强制刷新，你看到的就是当前的代码。

桌面外壳真正承担的职责 —— 提供 UI，以及把辅助二进制文件部署到用户机器上 —— 已经转移进 daemon，详见下文。

## 开发者安装路径

从源码 checkout 进行开发的开发者完全绕过 PyInstaller：

```bash
pip install -e ./backend[dev]
```

这会在开发者的 `PATH` 上放置两个控制台脚本入口点：

- **`coffer`** — 管理 CLI（`surfaces/cli/` 中的 Typer 应用程序）
- **`coffer-mcp-shim`** — 每个 MCP 会话一份的 stdio shim（`surfaces/shim/`）

daemon 直接作为 Python 进程运行：`coffer daemon start` 调用已安装包内部的 FastAPI/uvicorn 启动路径。无需二进制打包，无需构建步骤。对 Python 源码的修改立即生效；源码安装也完全不需要任何二进制部署 —— `pip install` 已经把控制台脚本放到 `PATH` 上了。

这条开发者路径有完善的文档，也是主要的贡献路径。它**不是**面向最终用户的分发渠道——PyInstaller 二进制文件承担那个角色。

## PyInstaller：独立二进制文件

对于面向最终用户的分发，`make bundle-binaries`（由 `scripts/build_binaries.sh` 驱动）在当前主机上针对以下 spec 文件运行 PyInstaller：

| Spec 文件                      | 输出二进制文件         | 包含内容                                                                                                                                                                                                                  |
| ------------------------------ | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/coffer-daemon.spec`   | `dist/coffer-daemon`   | FastAPI、SQLAlchemy 2 / aiosqlite、Pydantic 2、`mcp`、`keyring`、Alembic、structlog、Typer、uvicorn、`tomlkit` / `yaml`（agent 配置编辑）、`sqlite_vec`（及其原生 `vec0` 可加载扩展数据文件）、`markitdown`、`openai`，以及对话 agent 栈（`langchain*` / `langgraph`） |
| `backend/coffer-mcp-shim.spec` | `dist/coffer-mcp-shim` | 仅 `httpx`（shim 是一个轻量级 loopback 转发器）                                                                                                                                                                          |
| `backend/coffer.spec`          | `dist/coffer`          | 管理 CLI（Typer 应用）                                                                                                                                                                                                  |

PyInstaller 将 Python 解释器、所有依赖以及应用程序代码打包成单个可执行文件。用户直接运行 `coffer-daemon`，不需要 `python` 命令，不需要 `venv`，不需要 `pip`。shim 二进制文件刻意保持精简——它不包含任何服务端依赖，因为 shim 只需要 `httpx` 来通过 loopback HTTP 向 daemon 转发请求。每次会话都重新拉起 shim 的 MCP 客户端受益于更小二进制文件带来的更短冷启动时间。

除此之外，发布压缩包还携带 daemon 在运行时作为子进程拉起的**运行时辅助二进制文件**：`coffer-callback`（SeaTalk 回调监听器，`surfaces/callback/`，在任何 SeaTalk channel 启用期间由 daemon 启动）。在源码/开发运行中，daemon 以 `python -m coffer.surfaces.callback` 启动回调监听器；在 frozen 构建里，`listener_spawn.py` 会在 daemon 二进制旁寻找同级的 `coffer-callback`。正是这种同级关系，决定了部署这些二进制文件应该由 daemon 负责，而不是由安装程序负责（见[frozen 启动时的二进制部署](#frozen-启动时的二进制部署)）。

Alembic 迁移文件通过 PyInstaller 的 `datas` 机制，以数据文件的形式随 daemon 二进制一起发布。首次启动时，daemon 会在接受连接之前对一个全新的数据库执行 `alembic upgrade head`——最终用户无需额外步骤即可得到正确的 schema。

daemon 二进制还打包了更重的知识与对话依赖（knowledge 与对话两份规范）：用于向量索引的 `sqlite_vec`、用于文档转换的 `markitdown`、用于 embedding 的 `openai`，以及 `langchain*` / `langgraph` 对话 agent 栈。它们在函数内部惰性导入，PyInstaller 的静态分析无法追踪——因此 `coffer-daemon.spec` 把它们显式声明为 hidden imports，让 frozen 的 daemon 能够转换文档、做 embedding、执行向量检索并驱动内置对话 agent。

构建好的 Web UI（spec ui-shell）同样以数据文件的形式随 daemon 二进制发布，这正是 frozen 的 daemon 能从自己的 origin 提供 UI 的原因。

::: warning 捆绑验证——sqlite-vec 原生扩展
`sqlite-vec` 以**包数据**而非 Python 子模块的形式分发其可加载原生扩展（`vec0.dylib` / `vec0.so` / `vec0.dll`），因此 `collect_submodules` 永远捕获不到它——`coffer-daemon.spec` 通过 `collect_data_files("sqlite_vec")` 加入它。如果冻结构建缺失该数据文件，daemon 将无法加载 `vec0` 扩展，向量检索会静默降级为仅关键字（`VecIndex.available()` 吞掉加载失败）。因此发布冒烟测试必须把「捆绑的 daemon 能加载 `vec0`」作为一个显式的捆绑验证项（按 [Files as Truth](/zh/reference/adr/files-as-truth-sqlite-retrieval) 与 [PyInstaller Distribution](/zh/reference/adr/distribution-pyinstaller)）。
:::

::: tip 为什么选 PyInstaller，而不是其他方案
v0 阶段明确考虑并否决了两个替代方案：

- **Nuitka / PyOxidizer**：AOT 编译产出更小更快的二进制文件，但会显著拉长构建周期，并要求 CI 提供平台特定的编译器。之后更换打包器是一个有界且可逆的改动——daemon 的运行时契约里没有任何东西依赖 PyInstaller。
- **要求系统 Python**：直接违反「没有 Python 的用户也能安装 Coffer」这一要求。即便在 Linux 上，发行版自带的 Python 通常也落后一个版本；用户会遇到 `aiosqlite` 或 `pydantic-core` 的 wheel 构建错误。
  :::

## 单一下载层级

每次发布只产出一种面向用户的工件（**FR-022**）：一个 `coffer-cli-<triple>.tar.gz` 压缩包，内含

- `coffer`（管理 CLI）
- `coffer-daemon`（独立可执行文件，构建好的 Web UI 就在其中）
- `coffer-mcp-shim`（独立可执行文件）
- daemon 会拉起的运行时辅助二进制文件 —— `coffer-callback`

用户解压压缩包，运行 `coffer-daemon`（或 `coffer daemon start`），再用 `coffer open` 打开界面。同一个压缩包同时服务于无界面服务器、CI 环境和工作站，因为 UI 只是一个浏览器页面而非原生应用：在无界面机器上，你不打开它就是了。

发布不再为每个文件附一个 `.sha256` 伴生文件，而是发布**一份聚合的 `SHA256SUMS`**，覆盖该次发布的全部工件（**FR-023**），一条 `shasum -c SHA256SUMS` 即可校验整套下载。

## daemon 提供 Web UI

daemon 在自己的 loopback origin 上，以静态文件的形式提供构建好的 Web UI（**FR-024**）。因此 UI 与 REST API 是**同源**的：页面从 `http://127.0.0.1:<port>/` 取得，并调用 `http://127.0.0.1:<port>/api/v1/`。没有原生窗口，没有托盘图标，前端也不再有「我是否在桌面外壳里」这类构建期分支。

入口是 `coffer open`（**FR-025**）：

1. 从 `~/.coffer/daemon.json`（权限 `0600`）读取 daemon 的端口与 API token。
2. 调用一个需要鉴权的端点，签发一个**一次性、短时效的 code** —— 有效期约一分钟。
3. 在 daemon 的 origin 上打开浏览器，并把该 code 放在 URL 的 **fragment** 里。
4. 页面用该 code 换取 API token，并把 token 保存在 `localStorage` 中。

token 本身绝不出现在 URL 里。放进 URL 会把它写入浏览器历史记录，这与 spec mcp-gateway（FR-012 / FR-013）的 loopback + token 安全姿态相冲突。而交换用的 code 是一次性的，且约一分钟即过期，因此它出现在历史记录里是无害的。

由于 UI 与 API 同源，CORS **默认即为同源**。Vite 开发服务器的 origin 仍然保留在既有的 `COFFER_DEV_CORS` 开关之后，供前端开发使用。完整安全姿态见[安全](/zh/architecture/security)。

## frozen 启动时的二进制部署

桌面外壳过去会在每次启动时把 `coffer-mcp-shim` 部署到用户的 `PATH` 上。现在改由 daemon 在启动时完成，并且仅当它检测到自己以 frozen 构建方式运行时才执行（**FR-026**）。它会幂等地把同级的二进制文件复制进 `~/.coffer/bin/`：

- macOS / Linux：`~/.coffer/bin/coffer-mcp-shim`，以及 `coffer-daemon` 与 `coffer-callback`

具体机制与桌面实现完全一致：先复制到临时文件再原子重命名，并由同样的**三信号陈旧性检查**把关 —— 字节大小、mtime 和一个版本哨兵。三者全部匹配时部署是无操作；任一项不匹配都会触发原子替换。因此，通过解压更新的压缩包升级 Coffer 的用户，会在下一次 daemon 启动时自动获得更新后的二进制文件，无需手动管理 `PATH`。

daemon 是这一步天然的归属者，因为正是它在运行时拉起 `coffer-callback`，需要它位于已知的同级路径上。源码安装则完全跳过部署 —— 它不是 frozen 构建，而 `pip install` 已经把控制台脚本放到 `PATH` 上了。

## 发布流水线

CI 发布工作流（`.github/workflows/release.yml`）在每个 `v*` tag 上运行，为每个构建目标产出那唯一的 CLI 压缩包 —— 目前是 macOS arm64 —— 以及聚合的 `SHA256SUMS`。

不构建 macOS x64（Intel）和 Windows：GitHub 的 Intel macOS runner 池正在被弃用，会让 `macos-13` 任务一直「等待 runner」而饿死，且 PyInstaller 无法在 arm64 runner 上交叉编译 x86_64 二进制文件。

上传之前，压缩包会跑一轮构建后冒烟测试（`scripts/smoke_test_bundle.sh`）：脚本把捆绑的 `coffer-daemon` 启动到 `status: ready`，并让捆绑的 `coffer-mcp-shim` 通过 loopback 与它交换一条 JSON-RPC `initialize` 消息。冒烟测试返回非零即让发布失败。脚本使用后台看门狗而非 GNU `timeout`，因此在 macOS 上也能干净运行。

## macOS Gatekeeper

macOS Gatekeeper 会在首次运行时隔离下载得到的未签名可执行文件。代码签名与公证 —— Apple 用于证明二进制文件不含已知恶意代码的流程 —— 目前是 Coffer 的非目标：它们需要一个付费的 Apple Developer ID，而目前尚未申请。

在拿到之前，用户需要对从压缩包中解压出来的二进制文件清除隔离属性：

```bash
xattr -d com.apple.quarantine ~/coffer/coffer ~/coffer/coffer-daemon ~/coffer/coffer-mcp-shim
```

## 参见

- [分发——PyInstaller 打包的 daemon、shim 与 CLI](/zh/reference/adr/distribution-pyinstaller) — 决策记录、被否决的替代方案和修订历史
- [MCP Gateway 规范参考](/zh/reference/specs/mcp-gateway/spec) — FR-022 单层级压缩包、FR-023 聚合 `SHA256SUMS`、FR-024 daemon 提供 Web UI、FR-025 `coffer open`、FR-026 frozen 启动时的二进制部署
