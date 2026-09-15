# Web UI

Coffer 内置了一个基于浏览器的网关管理界面。你可以通过它添加、编辑、启用和禁用
MCP 服务器；浏览调用日志；调整设置 —— 全程无需使用 CLI。

## Web UI 是什么

Web UI 是一个建立在守护进程 REST API 之上的 React/Vite 单页应用，是日常 MCP 网关
管理工作的主要可视化界面。侧边栏分为三组：

```
AGENTS
  Agents           管理已注册的 AI 编码助手
RESOURCES
  MCP servers      管理已注册的服务器
  Skills           管理 Coffer 可交付给 agent 的技能
  Knowledge        每个知识作用域一个页面:笔记与文档
  Model providers  厂商端点及其密钥
  Channels         agent 应答所在的 IM 传输
SYSTEM
  Activity         改了什么、调了什么、哪里坏了
  Settings
```

RESOURCES 里每个带列表 UI 的 resource kind 恰好一项——五个 kind，五个入口。
AGENTS 只有一项，因为 agent 是**使用**金库、而不是住在金库里的那个东西。

**守护进程自己提供 Web UI**，在它自己的 loopback origin 上以静态文件的形式发布，
因此页面与 REST API 同源。没有额外要装的东西，也没有第二个服务器要起：守护进程在跑，
UI 就在。

## 打开 Web UI

```bash
coffer open
```

`coffer open` 从 `~/.coffer/daemon.json` 读取守护进程真实的端口 —— 守护进程绑定的是它端口
区间内第一个空闲端口，因此地址会随重启变动 —— 然后在那里打开浏览器。它不交付任何凭据，
因为不需要：守护进程会把自己当前的 API token 注入到它提供的 `index.html` 里，因此**任何**
由守护进程提供的页面都已经是登录状态。书签、手敲地址、刷新，或者
`http://127.0.0.1:<port>/agents` 这样的深链接，效果完全一样 —— 哪怕守护进程刚刚重启并铸造
了新的 token。

token 绝不会被放进 URL —— 那会把它写进浏览器历史记录 —— 也绝不会存进浏览器。存下来的
token 会活得比铸造它的守护进程更久，而这正是过去「刷新一下就变成未认证、除了重跑
`coffer open` 别无他法」的成因。

为了让这份随页面下发的 token 是安全的，守护进程只响应发往它自己 loopback 地址的请求：
`Host` 请求头写着别的东西的请求会被以 `421` 拒绝。正是这一点，挡住了恶意网页把自己的
域名重新指向 `127.0.0.1`、再从被提供的页面里读走 token。

如果守护进程没在运行，先启动它：

```bash
coffer daemon start
coffer open
```

## 在开发模式中打开 Web UI

在仓库根目录运行：

```bash
make dev
```

`make dev` 会启动两个进程：

1. Coffer 守护进程（`coffer daemon start`），在 8000–8009 范围内选取一个空闲端口，
   并把地址和 token 写入 `~/.coffer/daemon.json`。
2. Vite 开发服务器，监听 **`http://localhost:5173/`**。一个 dev 专用的 token 注入插件
   （`frontend/vite.config.ts`）读取 `~/.coffer/daemon.json` 并自动把 daemon token
   注入页面 —— 无需手动粘贴。

Vite 在确认守护进程可达（最长等待 30 秒）之后才会启动。用任意现代浏览器打开
`http://localhost:5173/`。

> 开发服务器与守护进程不同源，因此需要跨源开关：`make dev` 已经为你设置了
> `COFFER_DEV_CORS=1`。日常使用走 `coffer open`，那是同源的，不需要任何开关。

## 你可以做什么

### 首次运行欢迎页

第一次打开 UI 且尚未注册任何服务器时，Resources 页面会显示一张欢迎卡片，简短介绍
Coffer，并给出唯一的主要操作：**Add MCP server**。页面不会显示空表格或占位行。

如果守护进程未运行，UI 会显示"Daemon not running"视图，并提供可复制的
`coffer daemon start` 命令。一旦守护进程重新可达，视图会自动恢复 —— 无需手动刷新。

### MCP 服务器（Resources）

点击 **Add MCP server** 打开导入对话框。粘贴任意厂商 README 中的标准 `mcpServers`
JSON 块 —— 一次可粘贴一台或多台：

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    }
  }
}
```

Review 步骤让你标记哪些 `env` 值是 secret；这些值会加密进 Coffer 的凭据存储
（resource 配置里只保留它们的 ref），而非以明文存在 resource 配置中。

在服务器详情页可切换以下标签：

- **Overview** — 健康状态、最近一次在线、传输方式、命名空间。
- **Tools / Resources / Prompts** — 每个能力一行，带启用/禁用开关和搜索框。
- **Invocations** — 分页表格，展示每次调用的时间戳、类型、能力、状态和延迟。
  点击任意行可展开其原始调用 JSON。

### Agents

打开 **Agents** 管理已注册的 AI 编码助手（`claude_code` 和 `codex`）。列表是一个表格，
带搜索框、状态过滤器、分页，以及用于批量操作的行多选。点击 **Detect** 扫描已安装的
agent；检测对话框列出找到的结果，每一个都需要你确认后才会被注册 —— 不会自动注册任何
东西。每个 agent 都注册到单个**配置目录 (config directory)**（例如 `~/.claude` 或
`~/.codex`）；Coffer 会把技能交付到该目录的 `skills/` 子文件夹中。

agent 详情页有以下标签：

- **Overview** —— 该 agent 的类型与配置目录，以及它的 LLM 连接。在内置登录下，面板会列出
  该 agent 自己的 CLI 所提供的东西，模型选择器与聊天里的 `/model` 卡片提供的正是这些——
  没有什么需要你勾选。对 Claude Code 来说那就是它的档位别名（`opus`、`sonnet`、`haiku`、
  `fable`），每个都标着它今天解析到的那个模型（「Opus 5」）：那是 CLI 自己的选择器所提供的，
  也是唯一不会失败的选择——一个账号能跑哪些带版本号的模型是服务端事实，本机没有副本。你账号
  自己的附加选项（例如 1M 上下文变体）来自 CLI 的配置文件，与它们并排出现。Codex 则由它自己
  的 app-server 报告的模型来回答。
- **Skills** —— Coffer 为此 agent 管理的技能，每个都带启用/禁用开关。**Install skills**
  按钮会打开一个选择对话框（搜索、过滤、分页、多选），用于为该 agent 绑定更多技能。
- **MCP servers** —— 分两部分。*Via Coffer gateway* 显示 shim 的安装状态并链接到 MCP
  servers 页面。*Direct servers* 列出从该 agent 自己的配置文件读到的 MCP 条目：每行显示
  来源、传输方式，以及作为纯展示徽章的 enabled 状态；唯一的写操作是 **Adopt** ——
  把该条目接管进 Coffer 成为受管资源。Coffer 不改动别的工具的私有配置，因此这里既没有
  移除、也没有启用/禁用开关。
- **Memory** —— 该 agent 通过 Coffer 网关能触达的内容（一个指向 Memory 页面的链接）、它的
  **投递**状态，以及该 agent 自己的原生逐项目记忆库的只读表格。投递是这里唯一的写操作：
  在该 agent 的设置里安装或移除 Coffer 的会话开始 hook。在 hook 真正跑过一次之前，徽标显示
  *已安装——从未触发*，因为一个从不触发的 hook 和这个功能压根不存在没有区别。
- **Config files** —— 在编辑器中打开该 agent 任意经过策展的配置文件。保存时会校验文件
  格式（格式错误的 JSON/TOML 会被拒绝，文件保持不变），以原子方式写入并保留 `.bak`
  备份，并提供一个可滚动到匹配项的查找/替换框。

agent 头部的 **Install Coffer MCP** 开关会将 Coffer 自身的 `coffer` MCP 服务器条目
写入（或从中移除）该 agent 的配置，并配有实时状态指示。

### Skills

打开 **Skills** 管理 Coffer 可交付给 agent 的技能。列表是一个表格，带搜索框、过滤器、
分页，以及用于批量操作的行多选（例如批量校验或批量移除）。你可以从本地文件夹导入技能，
或从公开 Git URL 拉取技能；对技能进行校验（会运行 drift 检查），按行或批量执行；刷新
来自 Git 的技能；或移除某个技能。为某个具体 agent 启用或禁用技能是在那个 **agent** 的
详情页完成的，而不是在这里。

在技能详情页可切换以下标签：

- **Overview** —— 元数据：来源、版本哈希、master 路径以及时间戳。
- **Files** —— 该技能 master 文件夹的文件树，每个文本文件都可直接编辑。master 文件夹是事实源，
  以 FOLDER 方式投递的技能是软链到它的，所以一次编辑无需重新投递就能到达每个 agent。二进制文件、
  以及大到无法整份载入的文件保持只读 —— 保存一份被截断的内容会把磁盘上的文件也截短。

### Knowledge

打开 **Knowledge** 查看你的知识作用域:`global`、每个项目一个,以及任何你创建的集合。
每一行展示笔记数、文档数和磁盘占用。**Add collection** 创建一个具名集合;除了名字和描述之外
它什么也不问 —— 一个作用域带哪种索引是实现细节,不该在创建时抛给你当问题。embedding 模型
本身在 **Settings → Embedding** 中整个安装配置一次,而非按作用域配置。

点击某个作用域,会打开 `/knowledge/:scope`,包含两个标签页,以及树上方一个随输入即时匹配
文件名的过滤框 —— 纯客户端,没有按钮,也不发请求:

- **Documents** —— 被摄取并转换为 Markdown 的文件。可拖入文件、阅读、重新转换或删除。
  追踪了外部原件的文档会显示该原件在磁盘上是否已变化。
- **Notes** —— agent(和你)写下的内容。可在此新增、编辑与删除笔记。

页头带着作用域标题、一支重命名铅笔和项目路径。**Upload** 与 **Tidy** 是仅有的两个按钮
—— Tidy 按需对其中的文件跑一趟整理流程 —— Settings、Check sources 和 Reindex 收在溢出菜单里。
只有当作用域里存在转换失败的文档时,标题旁才会出现一条告警。

服务端检索不在这个页面上:agent 用 `coffer__search`,CLI 用 `coffer knowledge recall`。

旧的 `/knowledge-bases` 和 `/knowledge-bases/:name` URL 会重定向到此处。`/memory` 是它自己的界面——见下文 [Memory](#memory)。

### Memory

打开 **Memory** 查看你的 agent 已经学到的内容——从它们自己的原生记忆里读出来、按项目归一化成
一组事实。这个列表和这里的其他列表一样是一张表：每个分区一行——`global` 加上每个项目一个——
显示它命名所依据的项目、持有多少条事实，以及 MCP servers 和 Skills 列表逐行都带的那个
**生效范围**控件，并支持多选批量设置。生效范围是一个按钮，上面写着这个分区当下触达到哪里
——「所有 agent」「2 个 agent」「已禁用」——点开的面板里是「已禁用 / 所有 agent / 只限选中
的」三个选项：开还是关，以及对哪些 agent。而它是**按机器**设置的：它不参与同步，你用的每台
机器都各自设置自己的。面板会在你使用它的地方说明这一点，[同步](/zh/guide/sync) 说明为什么。
本页上的东西都不是你创建的，因此页头动作是
**Sync** 而不是 Add；还没有任何分区的库看到的是同一张表加一行空状态，Sync 仍在原处。

点击某个分区会打开 `/memory/:name`：它的事实、成对摆出待裁定的冲突、逐条事实的四种覆盖
（隐藏、置顶、标记为被取代、裁定冲突），以及一次 **Organise** 整理。Coffer 从不写回 agent
自己的记忆——一条事实唯一非派生的状态，就是你在这里记下的决定。

有两个相关界面是有意放在别处的：

- **投递**——Coffer 的会话开始 hook 是否已为某个 agent 安装、以及上一次真正触发是什么时候
  ——在那个 **agent** 自己的详情页的 Memory 标签下。hook 写进的是那一个 agent 自己的设置
  文件，所以它是逐 agent 的状态。
- 记忆事件的**审计轨迹**和全库其他事件一起，在 [Activity](#activity) 页面的 Changes 标签里。
  不存在第二份只含记忆的拷贝。

### Model providers

打开 `/model-providers` 查看 Coffer 为之持有密钥的厂商端点。一个 provider 是
`{protocol, base_url, credential_ref}`——端点加它的密钥。**模型**既不存在这里，
也不在这里选：agent 的模型在它自己的详情页上选，Coffer 内部引擎的模型在本页下方选。
把某个 provider 标记为 **internal default**，它就成了跑知识整理流程（tidy）
与语音转写的那条连接。embedding 配置是同一页底部的一张卡片。

这个界面过去在 Settings 下叫「LLM connections」。它挪出来是因为 `provider` 和其他
resource kind 没有区别；它改名是因为旧名字描述的是一个页面，而不是它管理的东西。

### Channels

打开 `/channels` 查看 agent 应答所在的 IM 传输——Telegram 与 SeaTalk。每个 channel
用自己的凭据注册、通过一次性配对码与你配对、并绑定一个默认 agent。它过去在 AGENTS
组下；一个 channel 是金库拥有的、带凭据的传输，因此它属于其他资源那一组。

### Activity

打开 `/activity`，Coffer 记下的一切都在这里。一份记录一个 tab，各自一张从新到旧的表：

- **变更** —— 审计日志：金库里改了什么、谁改的、什么时候。
- **MCP 调用** —— gateway 代理过的每一次调用：服务器、能力、耗时、结果。
- **守护进程** —— Coffer 自己的日志：级别、logger、消息，包括哪里坏了。

每个 tab 都能按自由文本和时间范围过滤，外加它那份记录才有的那一个过滤——actor、
调用状态、只看错误。点任意一行展开成它的原始记录。单台服务器的调用在它自己的详情页
也有一份，在 **Invocations** tab 下——同一张表，范围收到那台。

做成三张表而不是一张，是因为一张表只能展示三份记录的共同部分，而那并不多：一次调用的
耗时、一条日志的级别都会无处安放。**跨**这三者去读是你的 agent 的活儿，不是某个过滤器
的活儿：**`coffer__diagnose`** 会把它们拼在同一条时间线上一次返回，所以「刚才为什么
失败了？」是一个你直接问就行的问题。

脚本用途不变：`GET /api/v1/audit` 与 `coffer audit` 照旧。`/audit` 与 `/observability`
都重定向到这里。

### Settings

打开 `/settings` 可访问 **General**、**Data**（retention 策略、手动清理）、
**Sync**（金库导出与导入）、**Security** 与 **About**（版本、许可证、源代码）。没有"Daemon"标签，也没有 daemon 状态面板 ——
守护进程是实现细节，只有在出现问题时才会通过离线横幅呈现给用户。

### 语言

在侧边栏底部的语言切换器中可在 English 与 中文 之间切换。切换立即生效，并以
`coffer.language` 为 key 存入 `localStorage`。

## 下一步

- [注册 MCP server →](/zh/guide/register-server)
- [下载与安装 →](/zh/guide/install)
