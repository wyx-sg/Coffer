---
title: 术语表
description: Coffer 所用术语的定义，从生效范围、类型到同步轮次和整理，每条都链接到详细讲解它的页面。
outline: 2
pageClass: glossary
---

# 术语表 {#glossary}

Coffer 在界面、CLI、API 和文档中使用的术语，按英文字母顺序排列。每个条目都链接到深入讲解该概念的页面。

<AzBar />

## A {#a}

### 执行者（Actor） {#actor}

在[审计日志](#audit-log)中记录的操作执行者：`cli`、`ui`、`api`、`system`，或者通过 MCP 工具写入时的智能体名称。HTTP 客户端用 `X-Coffer-Actor` 请求头设置它。见[安全模型](/zh/architecture/security)。

### 纳入托管（Adopt） {#adopt}

把智能体磁盘上已有的东西交给 Coffer 管理：智能体自身配置里的某个 MCP 服务器条目，或者手动放进其技能目录的技能文件夹（[非托管技能](#unmanaged-skill)）。见[智能体](/zh/guides/agents)。

### 智能体（Agent） {#agent}

安装在本机并在 Coffer 中注册的编程智能体，比如 Claude Code（`claude_code`）或 Codex（`codex`）。智能体是类型为 `agent` 的[资源](#resource)。每台机器上每种类型最多一个，它的名称就是它的类型（`claude-code`、`codex`）；除了模型绑定，它唯一的设置是配置目录。见[智能体](/zh/guides/agents)。

### 聚合任务（Aggregate pass） {#aggregate-pass}

一种[维护任务](#upkeep-pass)，把每个已注册智能体的[原生记忆](#native-memory)读进 Coffer 的记忆，成为[原始条目](#raw-entry)。Coffer 从不写回智能体自己的记忆。见[记忆](/zh/architecture/memory#the-aggregation-pass)。

### 审批（Approval） {#approval}

一项会扩大密钥去向的改动，在有人于桌面应用中答复之前一直被挂起：从新的[目的地](#destination)引用某个密钥，或把它发往新的[接收方](#target)；或关闭这项保护。批准需要一次[在场授权](#presence-grant)；拒绝则不需要，在任何界面都能操作。改动需要等待审批的命令会打印 "waiting for approval in the Coffer app" 并以 `9` 退出。见[密钥](/zh/guides/secrets#approvals)。

### 审计日志（Audit log） {#audit-log}

对 Coffer 状态每一次改动的只追加记录：资源生命周期事件、被查看或解析的密钥、审批、配置写入、提供商切换、配对。每个条目都注明[执行者](#actor)。见[活动与审计](/zh/guides/activity)和[可观测性](/zh/architecture/observability#the-audit-log)。

## B {#b}

### 绑定（Binding） {#binding}

[技能](#skill)与它被投递到的智能体之间的联系。Coffer 投递技能的方式，是在智能体的技能目录里放一个指向[主存储](#master-store)中该技能目录的符号链接；**技能**页面会报告任何偏移。见[技能](/zh/guides/skills)。

### 自带登录（Built-in login） {#built-in-login}

智能体自己的认证方式，即 Coffer 把某个[连接](#connection)[投影](#projection)进去之前的状态。智能体页面上的**更改模型**会让智能体回到它。见[模型提供商](/zh/guides/providers)。

### 内置工具（Built-in tool） {#built-in-tool}

Coffer 自己提供的 MCP 工具，以保留前缀 `coffer__` 与上游工具一起列出：只有一个：`coffer__search_tools`。见 [MCP 工具](/zh/reference/mcp-tools)。

## C {#c}

### 消息渠道（Channel） {#channel}

一个即时通讯应用机器人（Telegram 或 SeaTalk），你离开电脑时可以通过它和智能体聊天、接收通知。消息渠道是类型为 `channel` 的[资源](#resource)，只供已配对的所有者使用（[所有者配对](#owner-pairing)），并由一台机器运行（[`runs_on`](#runs-on)）。见[消息渠道](/zh/guides/channels)。

### 知识集（Collection） {#collection}

一棵知识树：`~/.coffer/vault/knowledge/<collection>/` 下的一个 Markdown 文档目录，由你和你的智能体编写。知识集是类型为 `knowledge` 的[资源](#resource)。见[知识](/zh/guides/knowledge)。

### `coffer-guide` {#coffer-guide}

Coffer 自带并自行维护的技能。它是 Coffer 给智能体的说明书，后面附有每个[知识集](#collection)中每篇文档的路径、标题和描述。Coffer 根据正在运行的构建重新生成它，并拒绝删除它。见[技能](/zh/guides/skills)。

### `coffer run` {#coffer-run}

把[独立密钥](#standalone-secret)交给一个子进程的命令：`coffer run --secret ENV=<id> -- cmd`。这些值只设置在该子进程的环境中，在其输出里被遮盖为 `***`，每次解析都以 `secret_resolved` 记入审计。它只解析人在桌面应用里允许本机程序使用的密钥。它能防止密钥不小心进入文件和对话记录；但它不会对运行该命令的人或智能体隐藏密钥，因为运行者是子进程的父进程，所以靠的是这一步“允许”。见[密钥](/zh/guides/secrets#run-a-command-with-a-secret)。

### 连接（Connection） {#connection}

一份模型提供商配置：一种传输协议、一个 base URL 和一个密钥。为某个智能体打开连接，就会把它[投影](#projection)进该智能体的配置。连接是类型为 `provider` 的[资源](#resource)。见[模型提供商](/zh/guides/providers)。

## D {#d}

### 守护进程（Daemon） {#daemon}

在 `127.0.0.1` 上长期运行的 Coffer 进程。它拥有全部状态，提供管理 API、Web 界面和 MCP 端点，并运行各项维护任务。CLI 和 [shim](#shim) 发现它没在运行时会启动它。见[运行守护进程](/zh/guides/daemon)和[守护进程与进程](/zh/architecture/daemon)。

### `daemon.json` {#daemon-json}

运行时发现文件 `~/.coffer/daemon.json`：正在运行的守护进程的端口、进程 id 和 API 令牌，权限 `0600`，启动时写入、退出时删除。与它配套的 `daemon-config.json` 保存守护进程绑定端口之前读取的设置：固定端口、机器名称和实验功能开关。见[文件与目录](/zh/reference/filesystem#daemon-files)。

### 删除断路器（Deletion breaker） {#deletion-breaker}

[保险库同步](#vault-sync)的保护机制：一轮[同步](#sync-round)如果会丢失 20 个或更多文件，或者在某个区域丢失 5 个以上且超过一半，无论方向如何，都会被挂起，直到你在**同步**页面答复：**删除 N 个文件**，或**保留文件**。移动和重命名不算丢失。见[保险库同步](/zh/architecture/vault-sync#the-deletion-breaker)。

### 投递（Delivery） {#delivery}

把 Coffer 保存的东西送进智能体：[技能](#skill)通过[绑定](#binding)送达；[记忆](#partition)则通过 Coffer 安装在智能体设置里的 Hook 送达，它在会话开始时交出索引，并交出提示词所提到的笔记。见[记忆](/zh/guides/memory)。

### 目的地（Destination） {#destination}

Coffer 发送密钥明文的地方：MCP 服务器的环境变量或 HTTP 请求头、消息渠道的密钥、同步远端的推送令牌。每个目的地都有一个[接收方](#target)，即实际收到该值的东西。密钥只有经过[审批](#approval)后，才会到达新的目的地，或某个目的地的新接收方。见[安全模型](/zh/architecture/security#a-secret-goes-somewhere-new-only-with-your-approval)。

### 检测或启动（Detect-or-spawn） {#detect-or-spawn}

每个 Coffer 客户端找到守护进程的方式：读 `daemon.json`，探测端口，没有应答就启动一个守护进程；整个过程加锁，两个客户端永远不会启动两个守护进程。见[守护进程与进程](/zh/architecture/daemon#detect-or-spawn)。

### 提炼任务（Distil pass） {#distil-pass}

一种[维护任务](#upkeep-pass)，把一个[分区](#partition)的每个新[原始条目](#raw-entry)原样变成一条[笔记](#note)，渲染分区的索引 `MEMORY.md`，并删除智能体标了 `retired:` 的笔记（记入 `RETIRED.md`）。它不调用任何模型。见[记忆](/zh/architecture/memory#the-distil-pass)。

## E {#e}

### 实验功能（Experimental feature） {#experimental-feature}

默认关闭、可按机器开启的能力。目前有两个：`knowledge`（知识）和 `memory`（记忆）。保险库同步和模型提供商已经转正，始终开启。功能关闭期间，它的路由返回 `404 FEATURE_DISABLED`，它的工具从 MCP 工具列表中消失，它的界面看起来就像不存在；数据会保留。见[实验功能](/zh/guides/experimental-features)和[配置](/zh/reference/configuration#experimental-features)。

## I {#i}

### 收件箱（Inbox） {#inbox}

知识集中隐藏的 `.inbox/` 目录，一个投放区：智能体或另一台机器放在这里的文件，会被下一次[扫描](#upkeep-pass)收编并升格为文档。见[知识](/zh/architecture/knowledge)。

### 调用日志（Invocation log） {#invocation-log}

经过网关的每次 MCP 调用的记录，包括上游和内置工具：服务器、工具、耗时、状态（`ok`、`error`、`timeout` 或 `denied`）和会话。它从不保存参数或结果。见[可观测性](/zh/architecture/observability#the-mcp-invocation-log)。

## J {#j}

### 加入（Join） {#join}

一台机器开始与一个从未同步过的远端同步的方式，总是先预览、从不自动进行：面对空远端，它推送自己的保险库；作为新机器，它取两边的并集，不删除任何东西，内容不同的文件留给你选择；作为回归的机器，它从自己描述文件中记录的提交处继续。在**同步**页面运行。见[保险库同步](/zh/architecture/vault-sync#joining)。

## K {#k}

### 类型（Kind） {#kind}

[资源](#resource)的类型。Coffer 注册了七种：`mcp_server`、`agent`、`skill`、`channel`、`knowledge`、`memory` 和 `provider`。框架为每种类型提供相同的身份、生命周期、审计和[生效范围](#reach)；每种类型自己决定它的资源做什么。见[资源框架](/zh/architecture/resource-framework#the-seven-kinds)。

## M {#m}

### 机器 id（Machine id） {#machine-id}

一台机器的稳定标识符，从主机派生，离开机器前先做哈希。[保险库同步](#vault-sync)用它区分机器，消息渠道的 [`runs_on`](#runs-on) 指明其中一台。见[保险库同步](/zh/guides/vault-sync)。

### 主密钥（Master key） {#master-key}

解密所有已存密钥的密钥。它是 macOS 钥匙串中的一个项目，只有 Coffer 的签名二进制才能读取，守护进程运行期间把它保存在内存中。它从不同步。在桌面应用中备份它，桌面应用会在在场验证之后写出一个密钥文件；再通过**设置 › 安全 › 导入主密钥**装到另一台机器上。见[密钥存储](/zh/guides/secret-store#where-the-master-key-lives)。

### 主存储（Master store） {#master-store}

`~/.coffer/vault/skills/`，Coffer 在这里保存每个托管[技能](#skill)唯一的权威副本。智能体拿到的是指向其中的符号链接。见[技能](/zh/guides/skills)。

### 材料（Material） {#material}

提交给知识集的新知识：上传内容，或留在[收件箱](#inbox)里的文件。它会立即原样成为一篇文档。见[知识](/zh/guides/knowledge)。

### MCP 网关（MCP gateway） {#mcp-gateway}

守护进程中提供 `/mcp` 的部分：它聚合会话[生效范围](#reach)内每个已启用 [MCP 服务器](#mcp-server)的工具、资源和提示词，加上[内置工具](#built-in-tool)，并路由每次调用。见 [MCP 网关](/zh/architecture/mcp-gateway#lifecycle-of-a-tools-call)。

### MCP 服务器（MCP server） {#mcp-server}

你在 Coffer 中注册的上游 Model Context Protocol 服务器，通过 stdio 或 HTTP 连接。它是类型为 `mcp_server` 的[资源](#resource)，它的工具以 `<server>__<tool>` 的形式到达智能体。见 [MCP 服务器](/zh/guides/mcp-servers)。

## N {#n}

### 原生记忆（Native memory） {#native-memory}

智能体保存在自己文件里的记忆，比如 Claude Code 按项目划分的记忆目录。Coffer 在[聚合任务](#aggregate-pass)中读取它，并在智能体页面上以只读方式显示。见[记忆](/zh/guides/memory)。

### 笔记（Note） {#note}

Coffer 记忆中的一个主题，由[提炼任务](#distil-pass)写成[分区](#partition) `notes/` 目录下的一个 Markdown 文件。智能体用自己的文件工具搜索记忆根目录来找笔记，会话开始时的投递内容和 `coffer-guide` 技能都会指明这个根目录。见[记忆](/zh/guides/memory)。

## O {#o}

### 所有者配对（Owner pairing） {#owner-pairing}

把一个[消息渠道](#channel)绑定到唯一允许使用它的人。消息渠道的页面会签发一个八位、一次性、一小时内有效的配对码；用它给机器人发消息的人就成为该渠道的所有者，其他发送者都被静默忽略。见[消息渠道](/zh/guides/channels)。

## P {#p}

### 分区（Partition） {#partition}

Coffer 记忆的一个单元：`global`，或者某一个仓库。每个分区是 `~/.coffer/derived/memory/` 下的一个目录，保存它的[笔记](#note)、`MEMORY.md` 索引和[原始条目](#raw-entry)。分区是类型为 `memory` 的[资源](#resource)。见[记忆](/zh/guides/memory)。

### 应用前快照（Pre-apply snapshot） {#pre-apply-snapshot}

Coffer 在一轮[同步](#sync-round)检出任何内容之前打的 git 标签（`refs/tags/coffer/pre-apply/<time>`，保留最新十个），这样这一轮可以从该轮的抽屉里回滚。见[保险库同步](/zh/architecture/vault-sync#rollback)。

### 在场授权（Presence grant） {#presence-grant}

证明有人在这台 Mac 前的凭证。桌面应用为一次操作——查看密钥、写出密钥备份、批准一项审批——运行 Touch ID 或登录密码验证，然后用一个从主密钥派生的密钥，对守护进程发来的一次性挑战签名，该挑战绑定到这次操作及其目标。守护进程只对验证通过的授权采取行动；授权只能用一次，两分钟内过期。见[安全模型](/zh/architecture/security#plaintext-reaches-only-a-present-human)。

### 投影（Projection） {#projection}

把一个[连接](#connection)的接入地址和密钥引用写进智能体自己的配置，让智能体与该提供商通信。切回[自带登录](#built-in-login)会把它移除。见[模型提供商](/zh/guides/providers)。

## R {#r}

### 原始条目（Raw entry） {#raw-entry}

[聚合任务](#aggregate-pass)从智能体[原生记忆](#native-memory)中读出的一条事实，保存在分区隐藏的 `.raw/` 目录里，直到[提炼任务](#distil-pass)把它变成[笔记](#note)。见[记忆](/zh/architecture/memory#stable-raw-entries)。

### 生效范围（Reach） {#reach}

一个资源在本机上的适用范围：它的 `enabled` 标志加上它的[作用范围](#scope)。知识集和记忆分区没有生效范围：它们对每个智能体都提供。生效范围只属于本机、从不同步，所以每台机器自己决定哪些智能体能看到一个已同步的资源。见[资源框架](/zh/architecture/resource-framework#reach)。

### 资源（Resource） {#resource}

你在 Coffer 中管理的任何东西：MCP 服务器、智能体、技能、消息渠道、知识集、记忆分区或提供商连接。每个资源都有一个[类型](#kind)、一个不可变的 [uid](#uid)、一个在其类型内唯一的名称，以及一个[生效范围](#reach)。见[核心概念](/zh/start/concepts)。

### 保留期限（Retention） {#retention}

Coffer 保存日志类数据行（比如审计日志和[调用日志](#invocation-log)）多长时间的逐表限制，由后台清理程序执行。在**设置 → 数据**里管理。见[可观测性](/zh/architecture/observability#retention)。

### `runs_on` {#runs-on}

运行[消息渠道](#channel)适配器的那台机器的[机器 id](#machine-id)。消息渠道的设置同步到每台机器；只有这台机器连接即时通讯平台。在消息渠道的页面上设置。见[消息渠道](/zh/guides/channels)。

## S {#s}

### 作用范围（Scope） {#scope}

资源可选的一份适用智能体列表；没有列表就表示所有智能体。它与 `enabled` 一起构成资源的[生效范围](#reach)。对[消息渠道](#channel)来说，作用范围要反过来理解：它列出的是该渠道可以驱动的智能体。用该类型的范围控件设置。见[资源框架](/zh/architecture/resource-framework#reach)。

### 密钥边界（Secret boundary） {#secret-boundary}

Coffer 为防范以你身份运行、遭到提示词注入的智能体而守住的那条线：密钥明文只会交给在桌面应用前的人，密钥只有经过这个人的[审批](#approval)才会去往新的[目的地](#destination)。智能体仍然可以读取和修改 Coffer 的配置。见[安全模型](/zh/architecture/security)。

### 会话（Session） {#session}

一个 MCP 客户端到网关的连接。每个会话有自己的上游服务器进程和自己的智能体身份，身份由 [shim](#shim) 在握手时报告。空闲会话会被回收。见 [MCP 网关](/zh/architecture/mcp-gateway#sessions-and-identity)。

### Shim {#shim}

`coffer-mcp-shim`，智能体作为自己的 `coffer` MCP 服务器启动的小型 stdio 程序。它把智能体的 MCP 消息转发到守护进程的 `/mcp` 端点，必要时启动守护进程，并报告智能体的 uid（`--agent-uid`）。见[连接客户端](/zh/guides/connect-a-client)。

### 技能（Skill） {#skill}

一个带 `SKILL.md` 的文件夹，教智能体完成一项任务。Coffer 把托管技能保存在它的[主存储](#master-store)中，并把每个技能[绑定](#binding)到其生效范围内的智能体。技能是类型为 `skill` 的[资源](#resource)。见[技能](/zh/guides/skills)。

### 独立密钥（Standalone secret） {#standalone-secret}

不属于任何资源的密钥，存为 `secret/<id>`，在技能和 env 文件中以 `coffer://secret/<id>` 引用。id 由 Coffer 在你运行 `coffer secret set --name "Orders DB"` 时生成；人从不自己选 id，只给它起名称（标签，最多 64 个字符）和写描述（最多 200 个字符），二者可随时修改。命令通过 [`coffer run`](#coffer-run) 使用它。见[密钥](/zh/guides/secrets)。

### 存储类别（Storage class） {#storage-class}

Coffer 保存的五类状态之一，每类在 `~/.coffer` 下有自己的位置：`vault/`（你的配置和内容，在 git 中）、`local/`（只对本机成立）、`content/`（媒体和对话工作目录）、`runs.db`（历史）和 `derived/`（从其余数据重建）。类别决定某样东西是否同步，以及能否安全删除。见[持久化](/zh/architecture/persistence)。

### 同步轮次（Sync round） {#sync-round}

[保险库同步](#vault-sync)的一轮：拉取远端，在工作树之外把它与本机保险库合并，遇到任何冲突就停下，运行[删除断路器](#deletion-breaker)，打一个[应用前快照](#pre-apply-snapshot)，检出合并结果并推送。停下的一轮会在**同步**页面逐个文件等待答复。见[保险库同步](/zh/architecture/vault-sync#the-round)。

## T {#t}

### 接收方（Target） {#target}

在某个[目的地](#destination)接收密钥的东西，以人能在[审批](#approval)中读懂的方式写出：stdio 服务器的完整命令行及其工作目录和其他环境变量、HTTP 服务器的 URL、git 远端的 URL、消息渠道的机器人或应用。接收方改变时会再次询问。见[密钥](/zh/guides/secrets#approvals)。

### 整理（Tidy） {#tidy}

[知识集](#collection)或记忆[分区](#partition)上的按钮（列表页上还有**整理全部**），它会在你的首选终端里启动默认的交接智能体，并把一条提示作为第一条消息发给它，让它按 `coffer-guide` 技能合并、拆分和纠正其中的内容。没有可用的托管智能体时，它提供可复制的提示。整理由你的智能体来做，Coffer 自己从不主动整理。见[知识](/zh/guides/knowledge)和[记忆](/zh/guides/memory)。

### 分层（Tiering） {#tiering}

网关的列表预算：上游工具数量超过预算时，`tools/list` 携带最常用的工具（每个服务器至少一个），其余每个工具仍可按名称调用，并能通过 `coffer__search_tools` 找到。见 [MCP 工具](/zh/reference/mcp-tools#tiering)。

### 标题（Title） {#title}

可选的显示标签，最多 80 个字符，由具备它的类型携带——模型提供商、消息渠道、知识集和记忆分区。Web 界面用它代替名称显示。智能体、MCP 服务器和技能没有标题：智能体以其类型命名，MCP 服务器或技能的固定名称显示在其描述旁边。见[资源框架](/zh/architecture/resource-framework#identity)。

### Trace id {#trace-id}

守护进程在 `X-Coffer-Trace` 响应头中返回、并打在该请求产生的每一行日志上的逐请求标识符，这样失败的响应能与它的日志记录对上。见[可观测性](/zh/architecture/observability#trace-ids)。

### 轮次（Turn） {#turn}

对话中的一次往返：你的消息和智能体流式返回的回复，包括它的工具调用。一个对话一次只运行一个轮次，其余消息排队。见[对话与轮次](/zh/architecture/chat#the-turn-orchestrator)。

## U {#u}

### uid {#uid}

资源的永久标识符：一个随机的 32 位十六进制字符串，只生成一次，从不复用，在每台同步的机器上都相同。大多数名称可以改；uid 不能。见[资源框架](/zh/architecture/resource-framework#identity)。

### 非托管技能（Unmanaged skill） {#unmanaged-skill}

智能体自己的技能目录中、不是由 Coffer 放进去的技能文件夹。智能体页面会列出它们，你可以把它们[纳入托管](#adopt)或丢弃。见[技能](/zh/guides/skills)。

### 维护任务（Upkeep pass） {#upkeep-pass}

Coffer 按定时器、无需要求就做的机械性工作：记忆的 `aggregate` 和 `distil`，以及知识的扫描（重新渲染指南、收编留在[收件箱](#inbox)的文件、提交磁盘上的编辑）。它们都不调用模型。每项都能在记忆页面的自动读取计划（**更新记忆**的 **▾**）里关闭或调整时间。见[记忆](/zh/architecture/memory#workers-and-scheduling)和[知识](/zh/architecture/knowledge#the-sweep)。

## V {#v}

### 保险库（Vault） {#vault}

位于 `~/.coffer/vault/` 的 git 仓库，保存你的配置和亲手编写的内容：资源文件、状态文档、知识集、技能文件夹、密钥密文和机器描述文件。从第一次使用起它就是一个仓库，每次被接受的改动都是一个注明其[写入者](#writer)的提交。更宽泛地说，也指 Coffer 在 `~/.coffer/` 下以五种[存储类别](#storage-class)保存的一切。见[手动编辑保险库](/zh/guides/vault-files)和[文件与目录](/zh/reference/filesystem)。

### 保险库同步（Vault sync） {#vault-sync}

通过把保险库仓库拉取和推送到你自己拥有的一个 git 远端，一轮又一轮地（[同步轮次](#sync-round)）让多台机器上的保险库保持一致。见[保险库同步](/zh/guides/vault-sync)。

## W {#w}

### 传输协议（Wire） {#wire}

一个[连接](#connection)所讲的 API 协议：`anthropic`、`openai` 或 `unknown`。传输协议决定一个连接能服务哪些智能体。见[模型提供商](/zh/guides/providers)。

### 写入者（Writer） {#writer}

[保险库](#vault)中一次提交的作者，写在它的 `Coffer-Writer` trailer 里：`user`（你，通过 Coffer 的某个界面）、`disk`（在编辑器、shell 或智能体自己的文件工具中编辑的文件）、`agent`、`daemon`、`curation`（只见于较早的历史）或 `sync`。保险库里的 `git log` 会显示它。见[手动编辑保险库](/zh/guides/vault-files)。
