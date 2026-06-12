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

首次访问时 index (`/`) 重定向到 `/agents`，你会看到：

- 重设计后的侧栏——基于角色的分组：**Agents**（`/agents`——你使用的 agent）、**Resources**（**MCP servers**，位于 `/mcp-servers`）、**System**（**Audit log** 位于 `/audit`、**Settings**）。当前路由高亮。点击收起手柄在完整与图标态之间切换；选择跨刷新持久化。（`/resources` 仍可用——它是指向 `/mcp-servers` 的 legacy 重定向。）
- Agents 欢迎卡片，介绍 Coffer 是什么，并给出一个主行动：**Add agent**。对应的 **Add MCP server** 欢迎卡片在 **MCP servers**（`/mcp-servers`），一步可达。

如果 daemon 没在跑（你跳过了 `make dev`，或它崩了），你会看到一个 "Daemon not running" 视图，带一个「重新加载」恢复操作（桌面应用提供「重启」）。把 daemon 拉起来，视图会在下一次渲染就自动恢复——不需要手动刷页（见 `daemon-offline banner` acceptance scenario）。

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
- 标记哪些 `env` 值是 secret。secret 会加密进凭据存储 (`/api/v1/credentials`)，而不是 resource 配置里。顺序是**先注册、再写凭据存储**——这样一旦注册失败，也不会留下孤儿凭据条目（详见 spec scenario）。

点 **Add** 完成。成功后对话框关闭；如果只有一台服务器，app 会跳到 `/mcp-servers/mcp_server/<name>` 的 Overview tab。新服务器立刻出现在列表中，健康状态先是 "unknown"，约 10 秒内变为 "healthy"。

如果 JSON 解析失败或形状不对，对话框不关并显示一条可读的错误，说明问题在哪；不向后端发任何请求（见 `JSON import shows readable error for malformed JSON` scenario）。

## 4. 挑选能力

在服务器详情页切换 tab：

- **Overview** — 健康、最近一次见到、传输方式、命名空间。
- **Tools / Resources / Prompts** — 每个能力一行，行内带启用 / 禁用开关。搜索框过滤；切换立即生效并重拉列表。
- **Invocations** — 分页表格：时间、类型、能力、状态、时延。可按状态过滤。点任意行展开它的原始日志——该次 invocation 完整的底层 JSON 记录，以等宽、可滚动的代码块美化呈现。在客户端通过 coffer 调任意工具之前，这里是 "No invocations yet" 空态，提示如何触发。

要看到 invocation 落库，按 [`specs/001-mcp-gateway/quickstart.zh.md`](../001-mcp-gateway/quickstart.zh.md) 中 "Wire Coffer into your MCP client" 一节把 MCP 客户端接到 coffer，触发一次工具调用（比如让 Claude Code 读个文件），然后刷新 **Invocations** tab。

## 5. 审计日志与 Settings

- `/audit` — 审计日志视图（在 **System** 分组下）。按时间范围与 actor 过滤；点任意行展开它的原始日志——该条目完整的底层 JSON 记录，以等宽、可滚动的代码块美化呈现。legacy `/observability` URL 仍能解析并重定向到这里。（Observability——系统健康 / 指标——是另一个预留给未来的独立界面，不是这个审计日志。）
- `/settings` — tabs 侧栏打开在 **General**（默认每页条数偏好），另有 **Data**（retention 策略、手动清理、备份）与 **About**（版本 / 许可证 / 源代码）。桌面构建还多一个 **App** tab（开机自启）。

相比 v0 壳，刻意删掉的三处地方：

- 没有 "Daemon" tab，也没有 daemon 状态面板。daemon 是实现细节；它挂了，靠 daemon-offline banner 一处提示就够。
- 没有 "Shutdown daemon" 按钮——它会杀掉你正在用的那张页面；要关 daemon 用 CLI 的 `coffer daemon stop`。
- 没有 "Rotate token" 按钮——用 `coffer daemon rotate-token`。

## Where things live

- daemon 状态：`~/.coffer/coffer.db` 与 `~/.coffer/daemon.json`（与 spec 001 一致）。
- UI 偏好：只在 `localStorage`——`coffer.language`（语言）与 `coffer.nav.collapsed`（侧栏态）。
- UI 源码：`frontend/src/`——目录见 [`plan.md`](./plan.md)。
