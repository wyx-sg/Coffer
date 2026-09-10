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
  Knowledge        每个知识作用域一个页面:条目、文档、规则、现场
  Model providers  厂商端点及其密钥
  Channels         agent 应答所在的 IM 传输
SYSTEM
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

`coffer open` 从 `~/.coffer/daemon.json` 读取守护进程的地址与 token，向守护进程申请一个
**一次性、短时效的 code**，然后在守护进程自己的地址上打开浏览器，并把该 code 放在 URL
的 fragment 里。页面用该 code 换取 API token 并保存在 `localStorage` 中，之后直接访问
`http://127.0.0.1:<port>/` 即可使用。

token 本身绝不会被放进 URL —— 那会把它写进浏览器历史记录。而交换用的 code 是一次性的，
约一分钟即过期，因此留在历史记录里是无害的。

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

agent 详情页有四个标签：

- **Overview** —— 该 agent 的类型与配置目录。
- **Skills** —— Coffer 为此 agent 管理的技能，每个都带启用/禁用开关。**Install skills**
  按钮会打开一个选择对话框（搜索、过滤、分页、多选），用于为该 agent 绑定更多技能。
- **MCP servers** —— 分两部分。*Via Coffer gateway* 显示 shim 的安装状态并链接到 MCP
  servers 页面。*Direct servers* 列出从该 agent 自己的配置文件读到的 MCP 条目：每行显示
  来源、传输方式，以及作为纯展示徽章的 enabled 状态；唯一的写操作是 **Adopt** ——
  把该条目接管进 Coffer 成为受管资源。Coffer 不改动别的工具的私有配置，因此这里既没有
  移除、也没有启用/禁用开关。
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
- **Files** —— 该技能 master 文件夹的只读文件树与内容查看器。

### Knowledge

打开 **Knowledge** 查看你的知识作用域:`global`、每个项目一个,以及任何你创建的集合。
每一行展示条目数、文档数、磁盘占用,以及已建索引的检索模式。**Add collection** 创建一个具名集合
(向量检索的勾选框是唯一与知识相关的选项 —— embedding 模型本身在 **Settings → Embedding**
中整个安装配置一次,而非按作用域配置)。

点击某个作用域,会打开 `/knowledge/:scope`,包含五个标签页:

- **Entries** —— agent(和你)写下的内容。可在此新增、编辑与删除条目。
- **Documents** —— 被摄取并转换为 Markdown 的文件。可拖入文件、阅读、重新转换或删除。
  追踪了外部原件的文档会显示该原件在磁盘上是否已变化。
- **Rules** —— 该作用域的行为规则。按需读取;没有任何东西会把它们推进 agent 会话。
- **Handoff** —— 已保存的工作现场,每个 git 分支一条。
- **Changelog** —— 只追加的记录:整合做了什么、什么时候做的。

旧的 `/memory`、`/memory/:name`、`/knowledge-bases` 和 `/knowledge-bases/:name` URL 会重定向到此处。

### Model providers

打开 `/model-providers` 查看 Coffer 为之持有密钥的厂商端点。一个 provider 是
`{protocol, base_url, credential_ref}`——端点加它的密钥。**模型**既不存在这里，
也不在这里选：agent 的模型在它自己的详情页上选，Coffer 内部引擎的模型在本页下方选。
把某个 provider 标记为 **internal default**，它就成了跑知识 merge、organize、reorg
与语音转写的那条连接。embedding 配置是同一页底部的一张卡片。

这个界面过去在 Settings 下叫「LLM connections」。它挪出来是因为 `provider` 和其他
resource kind 没有区别；它改名是因为旧名字描述的是一个页面，而不是它管理的东西。

### Channels

打开 `/channels` 查看 agent 应答所在的 IM 传输——Telegram 与 SeaTalk。每个 channel
用自己的凭据注册、通过一次性配对码与你配对、并绑定一个默认 agent。它过去在 AGENTS
组下；一个 channel 是金库拥有的、带凭据的传输，因此它属于其他资源那一组。

### Audit log

审计日志没有页面。`/audit` 不再有路由，侧边栏里也没有任何入口指向它。

实际上没人打开过它。人不会专门坐下来浏览「我的金库里改了什么」——人是发现有东西坏了，然后去问那个帮他的角色，而那个角色是 agent。于是这份日志保住了它的读者，丢掉了它的页面。

agent 用 **`coffer__diagnose`** 读它：一次拿回两份记录——审计日志（改了什么、谁改的）与守护进程自己的日志（发生了什么，包括失败）——放在同一条从新到旧的时间线上。你问你的 agent「刚才为什么失败了？」，它手里就有这个工具。

脚本用途不变：`GET /api/v1/audit` 与 `coffer audit` 照旧。

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
