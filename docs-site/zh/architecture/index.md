---
title: 架构总览
description: Coffer 是怎么搭起来的：它有哪些进程、守护进程内部有哪些部分、四条主要数据流、技术栈，以及架构章节其余页面的阅读指引。
---

# 架构总览 {#architecture-overview}

这一页是整个架构章节的地图：一张图画出所有活动部件，列出运行中的进程、四条主要数据流如何穿过它们，以及底层用到的技术。它面向想先弄清 Coffer 怎么搭、为什么这么搭，再深入某个子系统的工程师。

::: tip 第一次来？
按顺序读这六页，整个设计就都在脑子里了；本章其余页面都是对其中某一部分的深入。

1. 本页，看全局地图。
2. [原则](/zh/architecture/principles)，看每次改动都要守住的规则。
3. [资源框架](/zh/architecture/resource-framework)，看每个受管对象共用的那一个抽象。
4. [守护进程与进程](/zh/architecture/daemon)，看谁拥有状态、每个客户端怎样找到它。
5. [MCP 网关](/zh/architecture/mcp-gateway)，看智能体的一次工具调用怎样流转。
6. [持久化](/zh/architecture/persistence)，看每类数据放在哪里、怎样写入。

如果还没用过 Coffer，先读[快速上手](/zh/start/quickstart)和[核心概念](/zh/start/concepts)。
:::

## Coffer 的架构要解决的问题 {#the-problem-coffer-s-architecture-solves}

同时用多个 AI 编程智能体的开发者，会把同一批资产攒上好几份：MCP 服务器的注册、API 密钥、技能、关于自己环境的笔记，以及每个智能体各自学到的东西。每个智能体按自己的格式保存一份，没有任何东西让它们保持一致。

Coffer 是一个本地进程，把这些资产只存一份，再通过智能体本来就支持的渠道交给每个智能体：一个 MCP 端点、智能体自己技能目录里的文件、智能体自己配置文件里的条目。它保存的一切都在你的机器上。架构由三条要求推出：

- **状态只有一个所有者。** 一个长驻的守护进程拥有保险库仓库、历史数据库、密钥存储和每一棵文件树。除了你手工编辑文件之外，写入者只有它一个，而且你的编辑也由它提交。
- **入口很多，但都很薄。** 智能体、CLI、Web 界面和桌面应用都是这个守护进程的客户端，走回环地址上的 HTTP。它们自己都不持有状态。
- **智能体自己的文件始终是权威。** Coffer 在智能体保存配置、记忆和对话记录的原位置读取它们，只写有文档说明的接口面。所以卸载 Coffer 之后，每个智能体照常工作。

## 一张图看懂 Coffer {#coffer-in-one-diagram}

下面的容器视图画出了每个进程和存储，以及谁和谁通信。实线箭头表示调用；守护进程的内部部件归在中间一组。

<ArchDiagram />

每个方框是什么：

| 部件 | 是什么 |
| --- | --- |
| 编程智能体 | Claude Code 和 Codex，Coffer 注册的两种智能体。每个智能体通过 Coffer 写进它配置里的一条 MCP 服务器条目连到 Coffer，并读取 Coffer 投递到它技能目录里的技能。 |
| `coffer-mcp-shim` | 一个很小的 stdio 转 HTTP 转发器，智能体把它当作 MCP 服务器启动。它找到（或启动）守护进程，把 JSON-RPC 转发到 `/mcp`，并在握手里盖上智能体的身份。 |
| `coffer` CLI | 一个 Typer 应用，命令很少：守护进程的生命周期、日志、`coffer run`，以及少数由程序或智能体交接运行的命令。每条读写状态的命令都是一次对守护进程的 HTTP 调用；CLI 自己从不打开数据库或密钥存储。 |
| Web 界面 | 一个 React 单页应用，构建成静态文件，由守护进程在自己的源上提供。 |
| 桌面壳 | 一个 Tauri 2 应用，在原生窗口里承载同一份构建好的前端，并带一个菜单栏项。它通过 IPC 把守护进程地址和令牌交给页面，在没有守护进程运行时启动一个，并根据签名的发布清单自我更新。 |
| HTTP API | `/api/v1/*` 下的 FastAPI 路由：所有客户端共用的管理面。 |
| MCP 网关 | `/mcp` 端点。它把每个启用的上游 MCP 服务器聚合到一个端点后面，加上 Coffer 的内置工具，并按生效范围过滤每个智能体能看到的内容。见 [MCP 网关](/zh/architecture/mcp-gateway)。 |
| 资源框架与各类型 | 与类型无关的核心，给每个用户管理的东西（一个 MCP 服务器、一个技能、一个消息渠道）同一套身份、生命周期、审计轨迹和生效范围，外加接入它的七种类型。见 [资源框架](/zh/architecture/resource-framework)。 |
| 后台 worker | 进程内的 asyncio 循环：保留期清理、知识清扫、记忆聚合与提炼、保险库同步轮次、对话记录缓存预热、MCP 会话回收，以及承载 Telegram 轮询和 SeaTalk websocket 连接的消息渠道运行时。完整列表和运行周期见 [守护进程与进程](/zh/architecture/daemon#background-work)。 |
| `vault/` | `~/.coffer` 下的一个 git 仓库，是配置和内容的记录系统：每个资源一个 JSON 文件、状态文档、知识集、技能文件夹和密钥密文。每一次被接受的写入都是一次经过校验、写明写入者的提交。它旁边，`local/` 存只对本机成立的东西，`content/` 存媒体和对话工作目录，`derived/` 存可以重建的东西，比如记忆树。见 [持久化](/zh/architecture/persistence)。 |
| `runs.db` | SQLite，只存历史：审计日志、MCP 调用、对话和消息、同步轮次、用量。 |
| 上游 MCP 服务器 | 你注册的服务器（stdio 子进程或 HTTP 端点），按客户端会话启动。 |
| 模型提供商 | Anthropic 和 OpenAI 兼容端点（包括这台机器上的模型运行时），以及它投射到智能体里的提供商配置。 |
| Telegram 和 SeaTalk | 消息渠道绑定的消息平台。Coffer 只通过出站连接访问它们。 |
| 你的 git 远端 | 一个可选的、你自己拥有的仓库，保险库与它同步。 |

## 进程 {#processes}

Coffer 以一小组相互协作的进程运行，其中只有一个持有状态。

| 进程 | 生命周期 | 作用 |
| --- | --- | --- |
| `coffer-daemon` | 长驻。一直服务到你停掉它或另一个守护进程取代它；从不自行退出。 | 拥有全部状态：保险库唯一的写入者，也是唯一的 SQLite 写入者。绑定 `127.0.0.1` 上你在 `~/.coffer/daemon-config.json` 里固定的端口，没有就用 `38470`；绑不上这个端口就拒绝启动，并报出占用者。 |
| `coffer-mcp-shim` | 每个 MCP 客户端会话一个。 | 把 stdio 转发到守护进程的 `/mcp` 端点；探测或拉起守护进程；守护进程重启后自动恢复。 |
| `coffer` | 每条命令一个。 | 通过回环地址调用守护进程；探测或拉起它；守护进程版本与自己不一致时在 stderr 上警告。 |
| 桌面壳 | 应用运行期间。 | 承载前端，通过 IPC 提供密钥，探测或拉起并重启守护进程。退出它不会停掉守护进程。 |
| 上游 MCP 服务器 | 每个客户端会话、每个服务器一个。 | 由网关的会话级 supervisor 拉起，会话关闭时回收。 |
| 智能体运行时 | 每个对话轮次或每个对话。 | Claude Agent SDK 和 Codex app-server，由对话平台启动来跑一个轮次。 |

CLI、shim 和桌面壳都通过 `~/.coffer/daemon.json`（pid、端口、令牌；权限 `0600`）找到守护进程，这个文件由守护进程在启动时写入、退出时删除。`~/.coffer/daemon.lock` 上的拉起锁让并发的探测或拉起尝试最终汇聚到同一个守护进程。在 macOS 上，**开机自启动**会把守护进程注册为登录服务。完整生命周期见 [守护进程与进程](/zh/architecture/daemon)。

## 主要数据流 {#main-data-flows}

<DataFlows>

### 智能体的一次工具调用 {#an-agent-s-tool-call}

1. **智能体** 智能体调用它 `coffer` MCP 服务器上的一个工具。
2. **coffer-mcp-shim** shim 带着守护进程令牌把 JSON-RPC 消息转发到 `POST /mcp`。
3. **MCP 网关** 网关解析出会话（每个下游客户端会话都有自己的一组上游子进程），把 `github__create_issue` 这样带命名空间的名字路由到 `github` 服务器的会话，或者自己回答 `coffer__*` 内置工具。
4. **生效范围检查** 在列出或调用之前，网关会拿服务器的生效范围去比对 shim 在握手时上报的智能体 uid，所以一个生效范围不包含这个智能体的服务器不会呈现任何工具。
5. **工具预算** 当完整工具列表会超出配置的预算时，网关只列出一个子集，其余的由 `coffer__search_tools` 找出来。详见 [MCP 网关](/zh/architecture/mcp-gateway)。

### 一个对话轮次 {#a-chat-turn}

1. **你** 你在 **对话** 页面发一条消息，或者已配对的所有者从 Telegram 或 SeaTalk 发一条。
2. **轮次编排器** 两个入口调用同一个轮次编排器：对话空闲时它开始一个轮次，否则把消息排在正在运行的轮次后面。
3. **适配器与总线** 编排器向智能体提供者注册表要这个对话的智能体，构建一个适配器（Claude Agent SDK 或 Codex app-server），并把每个事件发布到一条按对话划分的总线上，网页和消息渠道渲染器都订阅这条总线。
4. **任一入口** 消息一旦到达编排器，下游就不再知道它来自哪个入口。详见 [对话与轮次](/zh/architecture/chat)。

### 一次技能投递 {#a-skill-delivery}

1. **技能库** 一个技能就是 `~/.coffer/vault/skills/<name>/` 下的一个主文件夹加一个 `skill` 资源文件。当且仅当技能已启用、且智能体在它的范围内时，技能才会到达这个智能体。
2. **调和** 两者中任何一项发生变化（启用、停用、扩大或缩小范围），都会对每个智能体做一次调和：Coffer 把主文件夹链接进 `<config_dir>/skills/`（符号链接、junction，或退而求其次的复制），或者收回一个已经不在生效范围内的副本。
3. **偏移检查** 启动时的偏移检查会修复被人手工弄坏的链接。Coffer 自己的说明书 `coffer-guide` 也由完全相同的代码投递。
4. **导入** 技能可以从文件夹、压缩包或 Git 仓库进入技能库，都会先暂存、确认；来自 Git 的技能固定在它的提交上，直到你接受更新。详见 [技能](/zh/architecture/skills)。

### 一轮同步 {#a-sync-round}

1. **Worker** 当你配置了一个你自己拥有的 git 远端，一个 worker 会按远端的间隔跑一轮同步，默认每小时一次。
2. **合并** 保险库本来就是 git 仓库，所以一轮同步只需要 fetch，让 git 在工作树之外算出合并；如果合并干净、有效且没触发删除熔断，就给保险库拍快照、检出合并结果并 push。
3. **冲突** 任何冲突都会让这一轮停下，两边都不改，直到你逐个文件给出答复。
4. **传输的内容** 生效范围和智能体从不传输（它们在 `local/` 里）；密钥只以 Fernet 密文传输，而且只在你选择开启时才传；一轮会丢失太多内容的同步会挂起，等你答复。详见 [保险库同步](/zh/architecture/vault-sync)。

</DataFlows>

## 十一项决策构成的设计 {#the-design-in-eleven-decisions}

Coffer 的大部分形态都来自少数几项决策。下面每一项都在它链接的页面上有完整论证，包括落选的方案。

<DecisionList>

- **每个保险库一个常驻守护进程；其他所有进程都是客户端，找到它或拉起它。** 只有一个 SQLite 写入者和一组上游进程，也不需要「先启动守护进程」这一步。空闲退出会让智能体的下一次调用承担冷启动。 [守护进程与进程](/zh/architecture/daemon)
- **回环地址、每次启动生成的令牌和 `Host` 检查就是全部访问模型。** Coffer 只在一台机器上服务一个人。绑定 `127.0.0.1` 挡住远程主机；`Host` 检查挡住把自己的 DNS 名重新指向回环地址的网页。 [安全模型](/zh/architecture/security)
- **每个受管对象都是一个带不可变 `uid` 的资源；行为留在各自的类型里。** 身份、生命周期、审计和生效范围对每种类型都一样，只建一次。调用工具和投递技能没有共同点，所以不强行统一。 [资源框架](/zh/architecture/resource-framework)
- **生效范围只属于本机，并在知道提问智能体是谁的地方执行。** 如果权限通过同步合并过来，就等于让另一台机器的同步轮次决定这台机器暴露什么。集中式的闸门则会压在每种类型的读路径上。 [资源框架](/zh/architecture/resource-framework#reach)
- **每个 MCP 客户端会话都有自己惰性启动的上游进程。** MCP 是按会话的协议。跨客户端共享上游，意味着要在网关里重新实现能力协商和通知路由。 [MCP 网关](/zh/architecture/mcp-gateway)
- **网关按使用量排序列出一部分工具，其余的提供搜索。** 工具超过大约 30 到 50 个后，模型选工具就不那么可靠了。分层只决定列出什么，从不决定能调用什么。 [MCP 网关](/zh/architecture/mcp-gateway#budget-driven-tiering)
- **知识是不带索引的纯 Markdown；它的目录以技能的形式到达智能体。** 智能体整天都在读文件，却很少调用检索工具。没有派生物，就不会有东西和文件不一致。 [知识](/zh/architecture/knowledge)
- **记忆从每个智能体自己的文件只读聚合，从不回写。** 每个智能体自己的记忆回路保持原样，Coffer 派生出的一切都可以删掉重建。 [记忆](/zh/architecture/memory)
- **保险库是一个 git 仓库；同步 pull 和 push 它，应用干净的合并，遇到任何冲突就停。** 只有共同的基线才能区分「从来没有」和「删掉了」，而且 Coffer 自己做的任何事都不需要撤销。你的远端始终是一个你可以查看的普通仓库。 [保险库同步](/zh/architecture/vault-sync)
- **密钥是用一个主密钥加密的 Fernet 密文，主密钥默认存在一个 `0600` 文件里。** Coffer 的构建没有签名，macOS 会对新构建碰到的每个钥匙串条目重新弹窗。一个文件里放一把密钥就没有弹窗了；钥匙串作为可选项保留。 [安全模型](/zh/architecture/security#the-secret-store)
- **未完成的功能随每个构建发布，在你开启之前一直关闭，而不是放在分支上。** 只有一条开发线，所有者测的正是用户在跑的东西。关闭一个功能只是隐藏它，数据保留。 [分发与发布](/zh/architecture/distribution#experimental-features)

</DecisionList>

### Coffer 刻意不做的事 {#what-coffer-deliberately-is-not}

同样的决策也排除了一些方向，知道它们可以省得再去提议：

- **不是托管服务。** 没有 Coffer 账号，也没有云端点。唯一的远端是你自己拥有的 git 仓库，任何一台机器都能重建它。
- **不是智能体。** Coffer 不会用模型处理你的知识或记忆；整理它们是你的智能体的工作，由**整理**按钮发起。它唯一的模型调用是可选的语音转文字。对话页面驱动的是你安装的智能体；Coffer 没有自己的对话人格。
- **不是检索引擎。** Coffer 不做任何 embedding，也不保存向量或全文索引。一条导入契约禁止代码库使用 embedding 库。
- **不是策略引擎。** Coffer 不逐个审批工具调用。管控是事先做好的，靠按工具的开关和生效范围；消息渠道只听从它已配对的所有者。
- **不是插件平台。** 各类型在组合根显式接线。插件契约需要好几个具体实现来作为设计依据，而一个单用户工具没有需要服务的生态。

这一切背后的规则及其理由，写在 [设计原则](/zh/architecture/design-principles) 里。

## 技术栈 {#tech-stack}

版本以 [`backend/uv.lock`](https://github.com/wyx-sg/Coffer/blob/main/backend/uv.lock)、[`frontend/package.json`](https://github.com/wyx-sg/Coffer/blob/main/frontend/package.json) 和 [`desktop/Cargo.toml`](https://github.com/wyx-sg/Coffer/blob/main/desktop/Cargo.toml) 中固定的为准。

| 层 | 技术 | 用途 |
| --- | --- | --- |
| 语言 | Python 3.12+ | 守护进程、CLI 和 shim。 |
| HTTP | FastAPI 0.141、Uvicorn 0.52 | REST API、`/mcp` 端点、提供 Web 界面。 |
| 校验 | Pydantic 2.13 | 所有配置 schema 和传输模型；JSON 列在进出时都经过校验。 |
| 持久化 | git；SQLAlchemy 2.0（async）基于 aiosqlite，Alembic 1.18 | 保险库仓库；历史数据库及其迁移。 |
| 密钥 | `cryptography`（Fernet）、`keyring` 25 | 信封加密；`keyring` 只用于可选的钥匙串主密钥。 |
| MCP | `mcp` SDK 2.2 | 网关既作为 MCP 服务器，又作为上游服务器的客户端。 |
| 智能体轮次 | Claude Agent SDK 0.2、Codex app-server | 在 Claude Code 或 Codex 里跑一个对话轮次。 |
| 文档 | MarkItDown 0.1 | 把上传的文档和消息渠道附件转成 Markdown 或文本。 |
| CLI | Typer 0.26、Rich | `coffer` 命令。 |
| 日志 | structlog 26.1 | `~/.coffer/logs/` 下每条记录一行 JSON。 |
| 前端 | React 18、TypeScript 5、Vite 5、React Router 6、TanStack Query 5 | Web 界面。 |
| UI 组件 | Tailwind CSS 3、基于 Radix 原语的 shadcn/ui、lucide-react | 组件和样式。 |
| API 客户端 | openapi-typescript、openapi-fetch | 由每个规格的 OpenAPI 契约生成的传输类型。 |
| 国际化 | i18next、react-i18next | 英文和简体中文界面。 |
| 桌面 | Tauri 2（Rust 2021） | 原生壳、菜单栏项和更新器。 |
| 打包 | PyInstaller | 冻结的 `coffer-daemon`、`coffer-mcp-shim` 和 `coffer` 二进制。 |

## 阅读指引 {#reading-guide}

本章其余部分从基础向外组织。

**基础** 讲其他一切所依赖的理念。

- [设计原则](/zh/architecture/design-principles)：代码库坚持的规则，每条都附理由和它排除了什么。
- [资源框架](/zh/architecture/resource-framework)：每个受管对象共享的唯一抽象：身份、生命周期、审计和生效范围。
- [分层与代码布局](/zh/architecture/layering)：四个层、强制执行分层的导入契约，以及代码该放在哪里。
- [平台端口](/zh/architecture/platform)：为什么只有一处知道宿主操作系统、其他地方都去问它，以及维持这一点的门禁。
- [智能体切面](/zh/architecture/agent-facets)：每个智能体一条记录，写明所有差异；机制是启动时绑定的可选切面，投射只有一个注册表，探测有两个信号。
- [调和器](/zh/architecture/reconciler)：一个电平触发的循环，让 Coffer 写进不归它所有的文件里的内容保持正确：它比较每个参数，只修复每个目标的策略允许修复的部分，可以只预览不写入，并审计每一次修复。

**运行时** 讲进程以及请求如何在其中流转。

- [守护进程与进程](/zh/architecture/daemon)：探测或拉起、发现文件、常驻、版本不一致。
- [MCP 网关](/zh/architecture/mcp-gateway)：聚合、按会话的上游、分层和工具搜索。
- [对话与轮次](/zh/architecture/chat)：对话页面和每个消息渠道共用的轮次平台。
- [事件流](/zh/architecture/event-stream)：一条守护进程级的失效提示流，告诉页面什么变了，连接断开后可续传；不断增长的列表按游标分页。
- [持久化](/zh/architecture/persistence)：五种存储类别、写入保险库的唯一路径，以及历史数据库。

**子系统** 是设计最多的三个功能。

- [知识](/zh/architecture/knowledge)、[记忆](/zh/architecture/memory)、[保险库同步](/zh/architecture/vault-sync)。

**横切关注点** 适用于所有地方。

- [安全模型](/zh/architecture/security)、[可观测性](/zh/architecture/observability)、[应用外壳](/zh/architecture/app-shell)、[分发与发布](/zh/architecture/distribution)，以及 [决策记录](/zh/architecture/decisions) 索引。

## 在代码里的位置 {#where-it-lives-in-the-code}

| 路径 | 内容 |
| --- | --- |
| [`backend/coffer/`](https://github.com/wyx-sg/Coffer/tree/main/backend/coffer) | 守护进程、CLI 和 shim，分四层。 |
| [`backend/coffer/surfaces/http/`](https://github.com/wyx-sg/Coffer/tree/main/backend/coffer/surfaces/http) | HTTP 界面层，其中的组合根负责执行迁移、装配每种类型并启动 worker。 |
| [`frontend/src/`](https://github.com/wyx-sg/Coffer/tree/main/frontend/src) | Web 界面。 |
| [`desktop/`](https://github.com/wyx-sg/Coffer/tree/main/desktop) | Tauri 壳。 |
| [`openspec/specs/`](https://github.com/wyx-sg/Coffer/tree/main/openspec/specs) | 产品契约，每项能力一个规格。 |
| [`docs/decisions/`](https://github.com/wyx-sg/Coffer/tree/main/docs/decisions) | 架构决策记录（ADR）。 |
