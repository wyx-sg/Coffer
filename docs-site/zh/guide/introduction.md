# 简介

Coffer 是一个本地优先 (local-first) 的 **AI agent 保险库** —— 为你机器上的每个 AI agent 提供一个安全、共享的统一接口。

Coffer 是一个守护进程 (daemon) + CLI + 桌面应用。它起初是一个统一的 **MCP 网关** —— 把上游 MCP 服务器聚合起来,再通过一个带命名空间的接口重新暴露给 MCP 客户端(Claude Code、Codex)—— 并成长为一个还管理你的**技能**、**知识库**、共享**记忆**、已注册**agents** 与**对话**的保险库,可通过**渠道**触达,并由**同步**在多台机器间保持一致。配置一次,每个 agent 看到的都是同一个保险库。所有状态都保存在你自己的机器上 —— 没有云账号,没有厂商锁定。

## 为什么选择 Coffer?

在 Coffer 出现之前,每个 AI 客户端各自维护一份孤立的配置。增加一个 MCP 服务器、一个技能、或一条记忆,都意味着要分别更新 Claude Code、Codex 及未来的每个客户端 —— 同一样东西反复注册,一处修改也绝不会传播到别处。

Coffer 转而成为唯一事实来源。在 Coffer 里**只配置一次** —— 注册一个工具、投递一个技能、整理一个知识库、或写下一条记忆 —— 接入的每个 agent 都能看到。密钥在静态时由你掌控的主密钥加密,每个动作都被审计,除非你把它同步到自己拥有的 git 远端,否则一切都不离开你的机器。

### Coffer 管理什么

| 类别                                    | 是什么                                                                           |
| --------------------------------------- | -------------------------------------------------------------------------------- |
| [MCP 服务器](/zh/guide/register-server) | 聚合上游 MCP 服务器;通过一个端点带命名空间地重新暴露其工具。                     |
| [Agents](/zh/guide/agents)              | 检测并注册 Claude Code / Codex;编辑其配置、投递技能、安装 Coffer 的 MCP 服务器。 |
| [技能](/zh/guide/skills)                | 一份主技能库,投递给你选定的 agent。                                              |
| [知识库](/zh/guide/knowledge-base)      | agent 可检索(grep / keyword / vector)但不可写入的文档存储。                      |
| [记忆](/zh/guide/memory)                | 跨所有 agent 的一份共享事实集,原生投影进每个 agent。                             |
| [对话](/zh/guide/chat)                  | 与 Coffer 内置 agent 对话,或驱动 Claude Code / Codex。                           |
| [渠道](/zh/guide/channels)              | 从 Telegram 或 SeaTalk 触达你的 agent。                                          |

外加两项横切能力:[加密凭证库](/zh/guide/credentials)和[多机同步](/zh/guide/sync)。

### 本地优先的设计

所有用户状态都驻留在你的机器上。云服务仅作为 LLM 与工具的提供方 —— 它们绝不充当任何仓库状态的事实记录方。HTTP API 仅绑定到 `127.0.0.1`。你的配置、凭证和审计历史只属于你自己;密钥在静态时加密,仅在你选择同步时以密文形式传输。

[开始使用 →](/zh/guide/getting-started)
