# Web UI

Coffer 内置了一个基于浏览器的网关管理界面。你可以通过它添加、编辑、启用和禁用
MCP 服务器；浏览审计日志与调用日志；调整设置 —— 全程无需使用 CLI。

## Web UI 是什么

Web UI 是一个建立在守护进程 REST API 之上的 React/Vite 单页应用，是日常 MCP 网关
管理工作的主要可视化界面。侧边栏分为两组：

```
RESOURCES
  MCP servers      管理已注册的服务器
  Agents           管理已注册的 AI 编码助手
SYSTEM
  Observability    审计日志与调用日志
  Settings
```

对于最终用户，Web UI **内嵌在[桌面应用](/zh/guide/desktop)中**发布，无需单独安装或
启动服务器。对于从 checkout 工作的开发者，它以 Vite 开发服务器方式运行（见下文）。

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

> **最终用户：** Web UI 已打包进桌面应用。安装方法请参阅
> [桌面应用指南](/zh/guide/desktop)。

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

Review 步骤让你标记哪些 `env` 值是 secret；这些值会写入 OS keychain，不存在
resource 配置中。

在服务器详情页可切换以下标签：

- **Overview** — 健康状态、最近一次在线、传输方式、命名空间。
- **Tools / Resources / Prompts** — 每个能力一行，带启用/禁用开关和搜索框。
- **Invocations** — 分页表格，展示每次调用的时间戳、类型、能力、状态和延迟。
  点击任意行可展开其原始调用 JSON。

### Agents

打开 **Agents** 管理已注册的 AI 编码助手（`claude_code` 和 `codex`）。点击 **Detect**
扫描已安装的 agent；检测对话框列出找到的结果，每一个都需要你确认后才会被注册 ——
不会自动注册任何东西。

agent 详情页让你在编辑器中打开该 agent 任意经过策展的配置文件。保存时会校验文件格式
（格式错误的 JSON/TOML 会被拒绝，文件保持不变），以原子方式写入并保留 `.bak` 备份，
并提供一个可滚动到匹配项的查找/替换框。**Install Coffer MCP** 开关会将 Coffer 自身的
`coffer` MCP 服务器条目写入（或从中移除）该 agent 的配置，并配有实时状态指示。文件夹
选择器用于设置 agent 的 skill 目录。

### Observability

打开 `/observability` 查看审计日志 —— 以口语化活动描述（如"Enabled demo-fs"）
记录每一个生命周期事件。可按时间范围和 actor 过滤；点击任意行展开原始日志 JSON。
旧版 `/audit` URL 会重定向到此处。

### Settings

打开 `/settings` 可访问 **Data**（retention 策略、手动清理、备份）和
**About**（版本、许可证、源代码）。没有"Daemon"标签，也没有 daemon 状态面板 ——
守护进程是实现细节，只有在出现问题时才会通过离线横幅呈现给用户。

### 语言

在侧边栏底部的语言切换器中可在 English 与 中文 之间切换。切换立即生效，并以
`coffer.language` 为 key 存入 `localStorage`。

## 下一步

- [注册 MCP server →](/zh/guide/register-server)
- [桌面应用 →](/zh/guide/desktop)
