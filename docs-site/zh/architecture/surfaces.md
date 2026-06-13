# 接口面（Surfaces）

::: tip 核心模型
Coffer 的每个接口面都是通向同一底层守护进程的入口点。守护进程持有全部状态；接口面是读取或修改该状态的只读或可读写窗口。通过 CLI 添加一个 MCP 服务器，Web UI 会立即显示它——因为两者都在调用同一个守护进程。断开桌面应用连接，守护进程仍在运行，所以你的 MCP 客户端依然正常工作。
:::

## 所有接口面共享的内容

所有接口面都建立在同一个 `coffer-daemon` 进程之上。守护进程是一个 FastAPI 应用，绑定到 `127.0.0.1:<auto-port>`，并暴露两个顶级端点组：

- `/api/v1/*` — 管理面（REST，JSON），使用 `X-Coffer-Token` 鉴权。
- `/mcp` — MCP 协议端点（HTTP/SSE），同样使用 `X-Coffer-Token` 鉴权。

每个接口面都通过 loopback HTTP 与守护进程通信，从 `~/.coffer/daemon.json`（权限 `0600`，仅 owner 可读）读取端口和 token。没有任何接口面持有自己的持久化状态——它们是进入守护进程有状态内核的无状态入口点。

以下各接口面均采用统一模板描述：**它是什么 · 所在进程 · 传输方式 · 生命周期 · 安全边界**。

---

## REST API

**它是什么。** 管理面。这是执行每一种资源 kind 及跨切面操作的 HTTP JSON API。它在 `/api/v1/` 下按路由组组织，每个 kind 一个家族，加上共享关注点：

| 路由组                            | 涵盖内容                                                            |
| --------------------------------- | ------------------------------------------------------------------ |
| `/resources`                      | 与 kind 无关的资源 CRUD、启用/禁用、生命周期。                     |
| `/resources/mcp_server`           | MCP 能力偏好与调用日志。                                           |
| `/agents`                         | Agent 注册表、配置文件、工作区切面、memory 投影。                  |
| `/skills`                         | 技能主存储与各 agent 的绑定。                                      |
| `/knowledge_bases`                | KB 文档、上传、重建索引、检索。                                    |
| `/memory_stores`                  | Memory 事实、scope 与原生投影。                                    |
| `/channels`                       | 通道绑定（Telegram、SeaTalk）、配对。                             |
| `/chat`、`/models`                | Chat 会话/轮次与模型目录。                                        |
| `/credentials`、`/settings`       | 加密凭据存储；设置含 `/settings/credentials`（主密钥存储）与 `/embedding` 配置。 |
| `/sync`                           | 多机同步运行与配置。                                              |
| `/fs`                             | 用于配置选择器的文件系统浏览辅助。                                |
| `/audit`、`/retention`、`/daemon` | 审计日志、保留策略、守护进程 token/备份操作。                     |

REST API 是规范接口——CLI、Web UI 和桌面应用都调用它。

**所在进程。** 守护进程（`coffer-daemon`）。REST API 嵌入在 FastAPI 应用中，与守护进程不可分割。

**传输方式。** 在 `127.0.0.1:<auto-port>` 上的 HTTP/1.1。所有端点都在 `/api/v1/` 下。JSON 请求体和响应体。管理面无 WebSocket，无 SSE。

**生命周期。** REST API 从守护进程达到「就绪」状态起即可用。守护进程关闭时随之关闭。

**安全边界。** 每个请求都必须携带有效的 `X-Coffer-Token` 头。token 在守护进程启动时生成，存储在 `~/.coffer/daemon.json` 中，从不传输到机器外部。CORS 配置为仅允许来自本地 Web UI 来源的请求。由于守护进程仅绑定到 `127.0.0.1`，网络本身就是第一道防线：网络上其他机器的请求无法到达 API。

---

## MCP 协议端点

**它是什么。** 聚合 MCP 接口面。这是 MCP 客户端最终通信的端点。它接受通过 HTTP/SSE 传输的 JSON-RPC 2.0 消息，支持完整的 MCP 协议：`initialize` 握手、`tools/list`、`tools/call`、`resources/list`、`resources/read`、`prompts/list`、`prompts/get` 以及 `notifications/*`。守护进程聚合所有已注册上游 MCP 服务器的工具、资源和提示，以 `<server-name>__<capability-name>` 为每项命名，呈现为来自单一 MCP 服务器的样子。

**所在进程。** 守护进程。MCP 端点是与 REST API 同一 FastAPI 应用的一部分，在同一端口上提供服务。

**传输方式。** 在 `127.0.0.1:<auto-port>/mcp` 上的 HTTP/SSE。MCP 使用 HTTP POST 发送 JSON-RPC 请求，并使用 Server-Sent Events 将通知流式传回客户端（例如 `tools/list_changed`）。stdio shim 将其 stdin/stdout 桥接到此 HTTP/SSE 端点。

**生命周期。** 客户端连接时（通过 `/mcp` 端点或通过 shim）创建一个新的 `MCPGatewaySession`。客户端断开时会话被释放。会话拥有的上游子进程在释放时被回收。MCP 端点本身的生命周期与守护进程相同。

**安全边界。** 初始连接需要 `X-Coffer-Token`。由于连接通过 stdio shim（从 `daemon.json` 读取 token）或直接来自本地进程，有效信任边界是本地用户账号。每个会话是隔离的：一个客户端的上游子进程和能力缓存对另一个客户端的会话不可见。

---

## CLI（`coffer …`）

**它是什么。** 命令行管理接口。通过 REST API 可用的每个管理操作也可以作为 `coffer` 子命令使用，按 kind 与跨切面关注点分组：

- **各 kind 分组：** `coffer mcp`、`coffer agent`、`coffer skill`、`coffer kb`、`coffer memory`、`coffer channel`。
- **跨切面分组：** `coffer credentials`、`coffer sync`、`coffer chat`、`coffer model`。
- **与 kind 无关 / 运维分组：** `coffer resource`、`coffer audit`、`coffer retention`、`coffer daemon`，以及顶级的 `coffer backup` / `coffer restore`（后者带 `--reindex` 以重建知识索引）。重建单个知识库的索引是 `coffer kb reindex`。

典型命令读作 `coffer mcp add`、`coffer mcp tool enable/disable`、`coffer audit`、`coffer daemon start/stop/status`。CLI 是 Coffer 用于脚本化工作流、基于 dotfile 的配置和没有浏览器的远程（无头）机器的主要接口。每个子命令都支持 `--json` 输出，以便机器可读集成。

**所在进程。** 短生命周期子进程。CLI 是一个独立的 Python 进程，作为控制台脚本入口点（`coffer`）安装到 `PATH` 上。执行一条命令后退出。在两次调用之间不保持运行。

**传输方式。** 通过 loopback HTTP 到 `127.0.0.1:<port>/api/v1/`，使用来自 `~/.coffer/daemon.json` 的 token。CLI 使用 detect-or-spawn 模式：如果发出 CLI 命令时守护进程未运行，CLI 将守护进程作为分离的后台进程启动，等待 `daemon.json` 出现，然后连接。用户永远不会看到「守护进程未运行」的错误；他们可能会在第一次调用时看到短暂的启动延迟。

**生命周期。** 按需启动；每条命令完成（或打印错误）后退出。CLI 退出不会停止守护进程。

**安全边界。** 来自 `~/.coffer/daemon.json`（权限 `0600`）的 token。与所有其他接口面相同的文件权限边界：只有用户账号的 owner 才能读取 token，从而发出经过认证的请求。

---

## Stdio Shim（`coffer-mcp-shim`）

**它是什么。** MCP 客户端（Claude Code、Codex、Cursor 以及任何支持 stdio MCP 服务器的工具）与守护进程 MCP 端点之间的桥接。MCP 客户端配置为 `"command": "coffer-mcp-shim"`，而不是特定的上游服务器。shim 在客户端的 stdin/stdout 接口和守护进程的 HTTP/SSE MCP 端点之间进行转换，使守护进程从客户端角度看起来像一个普通的 stdio MCP 服务器。

**所在进程。** 每个连接的 MCP 客户端会话一个 shim 进程。每个 MCP 客户端在客户端启动时启动一个新的 shim 进程。三个同时运行的 MCP 客户端意味着三个 shim 进程，每个都维护自己与守护进程的 HTTP/SSE 连接，每个都产生自己独立的 `MCPGatewaySession`，带有自己的上游子进程集合。

**传输方式。** 就 MCP 客户端而言，shim 从 stdin 读取并写入 stdout。在内部，它通过 HTTP/SSE 连接到 `127.0.0.1:<port>/mcp`，携带 `X-Coffer-Token`。stdin 上到达的 JSON-RPC 消息作为 HTTP POST 请求转发到守护进程；来自守护进程 SSE 流的通知写回 stdout。

**生命周期。** shim 由 MCP 客户端使用该客户端支持的任何子进程机制启动（例如，Claude Code 的 `claude mcp add coffer coffer-mcp-shim`）。MCP 客户端进程退出时 shim 退出。shim 退出不会停止守护进程——其他 shim 和其他客户端继续不受影响地工作。启动时，shim 应用 detect-or-spawn：如果在 `daemon.json` 中找不到正在运行的守护进程，它会启动一个，然后连接。

**安全边界。** 与 CLI 相同：来自 `~/.coffer/daemon.json` 的 token，文件权限边界。由于 shim 由 MCP 客户端（以相同本地用户身份运行）启动，信任边界隐含在进程所有权链中。shim 在每个守护进程请求上携带 token；守护进程对其进行验证。

---

## 回调监听器（Callback Listener）

**它是什么。** 唯一可被公网访问的接口面。它是一个独立的签名回调进程，接收来自聊天平台的入站 webhook——具体为 `POST /seatalk/{channel}`——以该通道的签名密钥校验每个请求的 SeaTalk 签名，回应 `event_verification` 挑战，并将真实事件转发给守护进程，由通道运行时处理。它之所以存在，是因为 SeaTalk 将事件推送到一个 URL，而不是让 Coffer 长轮询（Telegram 采用的模型），因此需要一个可达的 HTTP 端点（规约 009，[ADR-014](/zh/reference/adr/ADR-014-channel-adapter-framework)）。

**所在进程。** 一个由守护进程启动的子进程，刻意与守护进程分离。它仅在至少有一个 SeaTalk 通道启用时运行。将其置于主守护进程之外，意味着可被公网访问的代码路径是一个小而隔离的接口面，在任何流量到达有状态内核之前先完成签名校验。

**传输方式。** 在 `127.0.0.1:<callback-port>` 上的 HTTP，仅提供签名回调路径。监听器本身绑定到 loopback；来自 SeaTalk 服务器的可达性由 owner 在带外自建的**用户隧道**提供——Coffer 自己从不开放公网端口。

**生命周期。** 当某个 SeaTalk 通道启用时由守护进程启动；当最后一个 SeaTalk 通道禁用时拆除。其生命周期绑定于通道状态，而非任何客户端会话。

**安全边界。** 与 loopback 接口面不同，这一个接受源自机外的流量，因此其信任边界是**各通道的 SeaTalk 签名**：每个请求体在被转发前都以该通道的密钥经 `verify_seatalk_signature` 校验，未签名或签名错误的请求一律拒绝。这里的关卡不是 `X-Coffer-Token`——而是签名。

---

## Web UI

**它是什么。** 基于浏览器的管理界面，由[规约 002](/zh/reference/specs/002-ui-shell/spec) 规定。Web UI 提供与每个 CLI 管理操作等价的可视化操作：通过 JSON 导入注册 MCP 服务器、浏览服务器健康状态和能力列表、开/关工具/资源/提示、查看审计日志和调用历史，以及配置保留策略。信息架构反映了资源 kind 模型：侧边栏显示 `Resources`（已上线的 kind——MCP 服务器、Agents、Skills、Knowledge Bases、Memory、Channels）、用于直接与 agent 对话的 `Chat`，以及 `System`（可观测性，及带 Security 和 Models 子区的设置）。不显示任何「即将推出」的占位符——一个 kind 只有真正可用后才会出现。

**所在进程。** 浏览器进程。在生产环境中，构建好的前端由 Tauri 桌面 shell 内嵌（`tauri.conf.json` 中的 `frontendDist`）；浏览器进程与守护进程在逻辑上是分离的。在开发模式下，Vite 开发服务器运行在 `http://localhost:5173`。所有数据都从守护进程的 REST API 获取。

**传输方式。** 浏览器 HTTP/REST 到 `http://127.0.0.1:<port>/api/v1/`。Bearer token 在启动时提供给浏览器上下文（由桌面 shell 或本地助手从 `~/.coffer/daemon.json` 读取）。

**生命周期。** Web UI 会话是浏览器标签页的生命周期。关闭标签页不会影响守护进程。UI 包含一个守护进程离线横幅，用于检测守护进程何时不可访问，并将 `coffer daemon start` 命令显示为可复制的操作建议；当守护进程重新上线时，横幅自动消失。

**安全边界。** 每个 REST API 调用都携带 `X-Coffer-Token`。CORS 配置为仅允许来自本地 Web UI 来源的请求。由于守护进程绑定到 loopback 且 token 从不传输到远程来源，信任模型与 CLI 相同：仅限本地用户账号。

---

## 桌面应用

**它是什么。** Tauri 2 桌面应用，由[规约 003](/zh/reference/specs/003-mcp-gateway-desktop/spec) 规定。桌面应用将规约 002 的同一 Web UI 包装在原生应用窗口中，添加了守护进程监督、系统托盘图标和可选的登录时启动功能。对于日常桌面使用来说，它是零摩擦的入口点：安装它，Coffer 就始终在后台运行，无需任何手动 `coffer daemon start` 步骤。

**所在进程。** 原生桌面进程（Tauri 2，Rust + WebView）。它将 Web UI 嵌入为 WebView；桌面特定的功能（托盘菜单项、自动启动设置）在前端代码中的 `isTauri()` 守卫后面激活。

**传输方式。** 内部：WebView 通过 `127.0.0.1:<port>/api/v1/` 使用 REST，通过 `/mcp` 使用 MCP（与基于浏览器的 Web UI 相同）。Rust shell 也通过守护进程的 REST API 进行监督任务（健康检查、重启）。

**生命周期。** 桌面应用应用 detect-or-spawn 模式：启动时读取 `daemon.json`；如果守护进程已在运行，则连接；如果没有，则将 `coffer-daemon` 作为分离进程启动（POSIX 上的 `setsid`）并等待 `daemon.json` 出现。关闭主窗口会将其隐藏到系统托盘——守护进程保持运行。从托盘选择「退出」退出桌面进程。守护进程在桌面应用退出时的命运取决于是否还有其他入口点（shim、CLI）仍在使用它；分离的守护进程在桌面应用退出后继续存活。

桌面应用还在每次启动时将捆绑的 `coffer-mcp-shim` 与 `coffer-daemon` 二进制文件幂等地部署到稳定的用户可写 PATH 目录（macOS 和 Linux 上的 `~/.coffer/bin/`），使用大小/mtime/版本哨兵的过期检查来检测升级。这确保了在第一次桌面启动后 `coffer-mcp-shim` 始终在 PATH 上——其 detect-or-spawn 也能找到同目录的 `coffer-daemon`——而无需用户手动编辑 shell 配置文件。

**安全边界。** 与 Web UI 相同：每个 API 调用携带 `X-Coffer-Token`，仅限 loopback 的守护进程，本地用户账号信任边界。桌面应用将 `coffer-daemon` 和 `coffer-mcp-shim` 捆绑为 PyInstaller sidecar——运行时不依赖系统 Python。

**分发层级。** 桌面应用是发布版本的 CLI+桌面层级。一个单独的仅 CLI 层级（`coffer-cli-<triple>.tar.gz`）将这些二进制文件打包在没有 Tauri 包装器的情况下，用于无头或服务器安装。

---

## 接口面对比

| 接口面          | 进程类型         | 到守护进程的传输            | 由谁启动                | 生命周期         |
| --------------- | ---------------- | --------------------------- | ----------------------- | ---------------- |
| REST API        | 守护进程         | —（即守护进程本身）         | 系统 / 手动             | 守护进程生命周期 |
| MCP 端点        | 守护进程         | —（即守护进程本身）         | 系统 / 手动             | 守护进程生命周期 |
| CLI（`coffer`） | 短生命周期子进程 | Loopback HTTP               | 用户 / shell            | 每条命令         |
| Stdio shim      | 每会话一个       | HTTP/SSE                    | MCP 客户端              | MCP 客户端会话   |
| 回调监听器      | 守护进程启动的子进程 | Loopback HTTP（转发给守护进程） | 守护进程（SeaTalk 启用时） | 有 SeaTalk 通道启用期间 |
| Web UI          | 浏览器标签页     | Loopback HTTP（REST）       | 用户 / 浏览器           | 浏览器标签页会话 |
| 桌面应用        | 原生进程         | Loopback HTTP（REST + MCP） | 用户 / 操作系统自动启动 | 直到从托盘退出   |

---

**参见：** [架构参考](/zh/reference/project/architecture)，[规约 002：UI Shell](/zh/reference/specs/002-ui-shell/spec)，[规约 003：Desktop](/zh/reference/specs/003-mcp-gateway-desktop/spec)
