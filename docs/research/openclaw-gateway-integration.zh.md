# OpenClaw 集成设计（暂缓）

> English: [openclaw-gateway-integration.md](openclaw-gateway-integration.md)
>
> **状态：仅设计、未实现。** [ADR-040](../decisions/ADR-040-re-widen-agent-registry.zh.md) 把 `opencode` / `hermes` / `cursor` 作为受管叶子 agent 重新加回，但特意把 **openclaw** 留在 agent 注册表之外。本文即 ADR-040 承诺的"独立设计轨道"：当有真实需求时，Coffer *应当* 如何集成 openclaw，以及它为何不是一个 `AgentType`。

## OpenClaw 是什么

OpenClaw（`openclaw/openclaw`，docs.openclaw.ai）是一个自托管、多渠道的**个人 agent 网关**——不是编码 CLI。它是 Coffer 的对等物，而非其下的叶子。它自带：

- **agent 运行时 + 多 agent 路由**——它自己 *运行* agent 并在其间路由；
- **编码 agent 编排**——它自己把 Claude Code CLI、Codex CLI、OpenCode 当子工具驱动；
- **持久记忆**——每 agent 一个 SQLite（`agents/<id>/agent/openclaw-agent.sqlite`）+ `MEMORY.md`，嵌入 + sqlite-vec；
- **MCP**——它既是 MCP *host*（消费 server）也是 MCP *server*（`openclaw mcp serve`）；
- **hooks**——内部 `HOOK.md` + `handler.ts` 系统（`agent:bootstrap`、`session:compact:*`、`gateway:startup`…），没有外部"session-start"事件；
- **渠道**——Slack / Discord / Telegram / WhatsApp / … 插件由一个网关统一服务；
- **配置**——`~/.openclaw/openclaw.json`（JSON5）。

## 为什么 openclaw 不是受管叶子 agent

Coffer 的受管 agent 模型是"Coffer 拥有共享底座，agent 是被 Coffer 投影配置的叶子"。具体而言一个叶子 agent 得到：**MCP 注入**（Coffer 把 `coffer` server 写进 agent 配置）、**session-start hook**（Coffer 在开轮时注入规则/记忆）、**provider 投影**（Coffer 把 agent 指向选定的 LLM 连接）、**原生记忆关闭**（Coffer 成为唯一记忆存储）。这些都套不上 openclaw：

| Coffer 叶子 facet | openclaw 现实 | 结论 |
| --- | --- | --- |
| MCP 注入 | openclaw 自身就是 MCP host + server；往它自己拥有的配置里写 `coffer` 条目会重复/成环 | **N/A** |
| Session-start hook（规则/记忆） | 没有外部 session-start 事件；hook 是 openclaw 自己在 `~/.openclaw/` 里写的 `HOOK.md`/`handler.ts` | **N/A** |
| 原生记忆关闭 | openclaw 的记忆（SQLite + 嵌入）是其运行时核心，无法从外部逐轮开关 | **N/A / 冲突** |
| Provider 投影 | openclaw 完全支持自定义 base URL + key（`openclaw onboard --custom-base-url … --custom-api-key …`） | **支持，但见下** |
| Skills / plugins | ClawHub skills + `openclaw.plugin.json`——不同模型，openclaw 自管 | **N/A** |

把 openclaw 硬塞进 `AgentType` 意味着六个 facet 里有四个是永久缺口，且记忆/MCP 层会与 openclaw 自己的主动冲突。那是错误的抽象。

## 推荐集成：作为 OpenAI 兼容的 LLM 连接端点

唯一自洽的接缝，是 openclaw 已经为机器暴露的那个：它的**网关 OpenAI 兼容 HTTP API**。跑 `openclaw gateway`（默认端口 `18789`），开启 `gateway.http.endpoints.chatCompletions`，它就以 Bearer token 应答 `POST /v1/chat/completions`（及 OpenResponses `POST /v1/responses`），通过 `model` 字段（`openclaw/<agentId>`）选择目标 openclaw agent，`stream:true` → SSE。

这干净地映射到 Coffer 的 **LLM 连接** 机器（统一连接注册表，[ADR-032](../decisions/ADR-032-provider-switching.zh.md)），而**不是** agent 注册表：

- **把 openclaw 加为一个 Coffer LLM 连接**：`base_url = http://127.0.0.1:18789/v1`，协议 `openai`（chat-completions），凭据 = 存在 OS keychain 里的网关 Bearer token（绝不明文）。连接的 model 列表就是 `openclaw/<agentId>` 值。
- **谁消费它**：和消费任何 Coffer 连接的一样——内置的 Coffer chat/console，以及用户路由到它的任何受管 agent。实际上 openclaw 成了 Coffer 能对话的*又一个模型 provider*，背后是网关后面一个完整的 agent。
- **Coffer 不做什么**：不注入 MCP、不注入 session hook、不关闭原生记忆、不投影 instructions——这些 openclaw 自己拥有。Coffer 把该网关当作一个不透明的 OpenAI 兼容模型。

这让关系保持诚实：openclaw 是对等控制面，Coffer 就像消费任何别的 OpenAI 兼容端点那样消费它。

## 以后（如果需要）建什么

要让上面今天就能用，除文档外无需任何东西——用户现在就能在 `/settings/llm-connections` 手动把 openclaw 网关加为一个自定义 OpenAI 兼容连接。未来一个便利 slice *可以* 加：

1. **一个识别器**，使 `base_url` 是 openclaw 网关的连接在 UI 里被标为 "OpenClaw"，其 model 选择器从 `GET /v1/models` 拉取并提供 `openclaw/<agentId>` 值。
2. **一键 onboard**，shell 调用 `openclaw onboard --non-interactive` / 读 `~/.openclaw/openclaw.json` 来预填连接。

两者都是对连接注册表的增量，不碰任何 agent 注册表代码。

## 暂缓的决策 / 开放问题

- **Auth 生命周期**——网关 Bearer token 轮换 vs Coffer 的 keychain 引用。
- **流式形状**——确认 openclaw 的 SSE 帧与 Coffer 的 OpenAI-chat 流式解析器匹配（它已处理 `[DONE]`）。
- **建设触发点**——只在首个真实用户需求时才实现识别器/onboard（YAGNI）；在那之前，手动自定义连接的路径就够了。

## 参考

- [ADR-040：重新放宽 agent 注册表](../decisions/ADR-040-re-widen-agent-registry.zh.md)——openclaw 留在叶子注册表之外的决策。
- [ADR-032：provider 切换](../decisions/ADR-032-provider-switching.zh.md)——openclaw 会接入的 LLM 连接 / 凭据隔离机器。
- OpenClaw 网关 OpenAI HTTP API——`docs.openclaw.ai/gateway/openai-http-api`、`.../gateway/configuration`、`.../cli/onboard`。
