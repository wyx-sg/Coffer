# Quickstart — Coffer UI Shell

> English: [quickstart.md](./quickstart.md)

一份 5 分钟走查：从一份干净的 checkout 起，在浏览器里看到重设计后的 UI，通过 GUI 注册一台 MCP 服务器，并看到首次 invocation 出现。这是面向 **GUI** 的走查；CLI + shim 路径见 [`specs/001-mcp-gateway/quickstart.zh.md`](../001-mcp-gateway/quickstart.zh.md)。

## Prerequisites

- 一份可工作的 Coffer dev checkout。backend 依赖装好 (`backend/` 内 `uv sync`)，frontend 依赖装好 (`frontend/` 内 `pnpm install` 或 `npm install`)。
- 一台可注册的 MCP 服务器。走查用 `@modelcontextprotocol/server-filesystem`（需要 `npx`）。
- 一个 MCP 客户端 (Claude Code / Claude Desktop / Cursor)——如果想在 UI 里看到 invocation 落库。Add-MCP-server 流程本身不依赖客户端。

## 1. 启动 dev 栈

在 repo 根目录：

```bash
make dev
```

`make dev` 启动两个进程：

- daemon (`coffer daemon start`)，在 8000–8009 之间挑一个空闲端口，写出 `~/.coffer/daemon.json`。
- Vite dev server，监听 `http://localhost:5173/`。Vite 的 dev 专用 token 注入插件 (`frontend/vite.config.ts`) 读 `~/.coffer/daemon.json` 并把 daemon token 注入页面——不需要手动粘贴 token。

## 2. 看到工作台

在任意现代浏览器打开 `http://localhost:5173/`。

首次访问时 URL 解析到 `/resources`，你会看到：

- 重设计后的侧栏——两个分组：**Resources** 与 **System**（MCP servers / Observability / Settings）。当前路由高亮。点击收起手柄在完整与图标态之间切换；选择跨刷新持久化。
- 一张欢迎卡片，介绍 Coffer 是什么，并给出一个主行动：**Add MCP server**。

如果 daemon 没在跑（你跳过了 `make dev`，或它崩了），你会看到一个 "Daemon not running" 视图，附带一条可复制的 `coffer daemon start` 命令。把 daemon 拉起来，视图会在下一次渲染就自动恢复——不需要手动刷页（见 `daemon-offline banner` acceptance scenario）。

侧栏底部的语言切换器可在 English 与 中文 之间切换。切换在下一次渲染内生效，并以 `coffer.language` 为 key 存进 `localStorage`。

## 3. 添加第一台 MCP 服务器

在欢迎卡片上点 **Add MCP server**（之后从 MCP servers 列表也能点）。会弹出一个对话框。

把标准的 `mcpServers` JSON 块粘进去——就是每台 MCP server 的 README 给的那块。以 filesystem 举例：

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

一次粘一台或多台都可以。点 **Review**。对话框对每台服务器走一屏，让你：

- 确认服务器名。
- 标记哪些 `env` 值是 secret。secret 会写到 OS keychain (`/api/v1/keychain`)，而不是 resource 配置里。顺序是**先注册、再写 keychain**——这样一旦注册失败，也不会留下孤儿 keychain 条目（详见 spec scenario）。

点 **Add** 完成。成功后对话框关闭；如果只有一台服务器，app 会跳到 `/resources/mcp_server/<name>` 的 Overview tab。新服务器立刻出现在列表中，健康状态先是 "unknown"，约 10 秒内变为 "healthy"。

如果 JSON 解析失败或形状不对，对话框不关并显示一条可读的错误，说明问题在哪；不向后端发任何请求（见 `JSON import shows readable error for malformed JSON` scenario）。

## 4. 挑选能力

在服务器详情页切换 tab：

- **Overview** — 健康、最近一次见到、传输方式、命名空间。
- **Tools / Resources / Prompts** — 每个能力一行，行内带启用 / 禁用开关。搜索框过滤；切换立即生效并重拉列表。
- **Invocations** — 分页表格：时间、类型、能力、状态、时延。可按状态过滤。在客户端通过 coffer 调任意工具之前，这里是 "No invocations yet" 空态，提示如何触发。

要看到 invocation 落库，按 [`specs/001-mcp-gateway/quickstart.zh.md`](../001-mcp-gateway/quickstart.zh.md) 中 "Wire Coffer into your MCP client" 一节把 MCP 客户端接到 coffer，触发一次工具调用（比如让 Claude Code 读个文件），然后刷新 **Invocations** tab。

## 5. Observability 与 Settings

- `/observability` — Observability section 下的审计日志视图。按时间范围与 actor 过滤；点任意行展开它的原始详情（绝对时间、事件类型、payload）。legacy `/audit` URL 仍能解析并重定向到这里。
- `/settings` — tabs 侧栏分 **Data**（retention 策略、手动清理、备份）和 **About**（版本 / 许可证 / 源代码）。

相比 v0 壳，刻意删掉的三处地方：

- 没有 "Daemon" tab，也没有 daemon 状态面板。daemon 是实现细节；它挂了，靠 daemon-offline banner 一处提示就够。
- 没有 "Shutdown daemon" 按钮——它会杀掉你正在用的那张页面；要关 daemon 用 CLI 的 `coffer daemon stop`。
- 没有 "Rotate token" 按钮——用 `coffer daemon rotate-token`。

## Where things live

- daemon 状态：`~/.coffer/coffer.db` 与 `~/.coffer/daemon.json`（与 spec 001 一致）。
- UI 偏好：只在 `localStorage`——`coffer.language`（语言）与 `coffer.sidebar.collapsed`（侧栏态）。
- UI 源码：`frontend/src/`——目录见 [`plan.md`](./plan.md)。
