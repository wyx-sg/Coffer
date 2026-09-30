---
title: 决策记录
description: Coffer 架构决策记录的索引，按领域分组，每条写明它所记录的决定。
---

# 决策记录 {#decision-records}

Coffer 把每一个结构性的技术决定都写成一份架构决策记录（ADR），放在 [`docs/decisions/`](https://github.com/wyx-sg/Coffer/tree/main/docs/decisions) 中。本页按领域为它们建立索引。想知道设计某一部分背后的*原因*，或者准备提出一个会推翻某项决定的改动之前，先读对应的记录。

## 决策如何记录 {#how-decisions-are-recorded}

Coffer 保留三类设计文本，各司其职：

| 产物 | 存放位置 | 回答的问题 |
| --- | --- | --- |
| 规格 | [`openspec/specs/`](https://github.com/wyx-sg/Coffer/tree/main/openspec/specs) | 产品必须做*什么*：需求，每条需求都带有测试覆盖的场景。 |
| 变更提案 | `openspec/changes/<change-id>/` | 一次改动*如何*规划：提案、设计、任务和规格增量。 |
| 决策记录 | [`docs/decisions/`](https://github.com/wyx-sg/Coffer/tree/main/docs/decisions) | 一个技术选择*为什么*这样做，每个认真考虑过的选项都有论证。 |

一个决定值得写成记录，是当它以后很难改、约束不止一个模块、带有未来贡献者会质疑的取舍，或者偏离了某条约定或[原则](/zh/architecture/principles)中的某一条。产品范围属于规格，项目流程属于 `.agents/`，都不写进决策记录。

每份记录只陈述**一个**决定，分四个标题——**Context**、**Options Considered**（包括最终选中的选项，每个都就其本身论证）、**Decision** 和 **Consequences**——并以 kebab case 形式的标题命名，从不用编号。这个目录记录的是现行设计：决定改变时，拥有它的那份记录会被重写，读起来就像今天写的一样，被取代的设计作为其中一个选项加以论证；它所决定的东西被移除时，记录也随之删除。编写规则见[目录 README](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/README.md)。

这里列出的每份记录都是 `Accepted` 状态。


## 资源框架与持久化 {#resource-framework-persistence}

详见：[资源框架](/zh/architecture/resource-framework)、[持久化](/zh/architecture/persistence)。

| 决定 | 记录 |
| --- | --- |
| 资源框架是核心领域，在第二种类型出现之前就设计好 | [`resource-framework-upfront`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/resource-framework-upfront.md) |
| 一种类型以一条冻结的可选 Hook 记录接入：写入前做校验，写入后做响应 | [`kind-plugin-contract`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/kind-plugin-contract.md) |
| 资源身份是不可变的 `uid`，而不是名称 | [`resource-identity-is-an-immutable-uid`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/resource-identity-is-an-immutable-uid.md) |
| 按智能体划分的资源作用范围是框架中的一份白名单，由各类型自行执行 | [`per-agent-resource-scope`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/per-agent-resource-scope.md) |
| 资源生效范围只属于本机，从不收敛 | [`resource-reach-is-machine-local`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/resource-reach-is-machine-local.md) |
| 代码按层优先布局，每种类型一个子目录 | [`code-layout-layer-first`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/code-layout-layer-first.md) |
| 各类型由唯一的组合根显式装配，没有全局注册表 | [`composition-root-explicit-wiring`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/composition-root-explicit-wiring.md) |
| 控制面状态是一个 SQLite 文件，只由守护进程写入，启动时沿唯一一条 Alembic 迁移链向前迁移 | [`sqlite-alembic-persistence`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sqlite-alembic-persistence.md) |
| 每次改动都连同执行者一起审计，调用日志不记载荷，按表清理 | [`audit-and-retention`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/audit-and-retention.md) |

## 守护进程、外壳与分发 {#daemon-shell-distribution}

详见：[守护进程与进程](/zh/architecture/daemon)、[分发与发布](/zh/architecture/distribution)。

| 决定 | 记录 |
| --- | --- |
| 任何界面都能找到守护进程，找不到就启动它 | [`daemon-detect-or-spawn`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-detect-or-spawn.md) |
| 守护进程绑定固定端口，拿不到就拒绝启动 | [`daemon-binds-a-fixed-port`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-binds-a-fixed-port.md) |
| 守护进程常驻：从不因空闲退出，登录服务只在崩溃后重启它 | [`daemon-is-a-resident-login-service`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-is-a-resident-login-service.md) |
| 每次启动一个令牌，由托管页面的一方交给页面，并有回环地址主机守卫 | [`daemon-auth-and-origin-guard`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-auth-and-origin-guard.md) |
| 智能体通过 stdio shim 到达网关，而不是原生 HTTP 条目 | [`stdio-shim-bridge`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/stdio-shim-bridge.md) |
| 桌面外壳托管共享的前端，只负责浏览器做不到的事 | [`desktop-shell-over-a-shared-frontend`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/desktop-shell-over-a-shared-frontend.md) |
| 回环守护进程替界面执行操作系统的文件操作 | [`daemon-proxies-os-file-actions`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/daemon-proxies-os-file-actions.md) |
| 分发——三个 PyInstaller 二进制，以 CLI 压缩包和桌面应用两种形式发布 | [`distribution-pyinstaller`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/distribution-pyinstaller.md) |
| 用实验功能代替发布分支 | [`experimental-features-instead-of-a-release-branch`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/experimental-features-instead-of-a-release-branch.md) |
| 侧边栏按角色分组：智能体、资源、系统 | [`sidebar-grouped-by-role`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sidebar-grouped-by-role.md) |

## MCP 网关 {#mcp-gateway}

详见：[MCP 网关](/zh/architecture/mcp-gateway)。

| 决定 | 记录 |
| --- | --- |
| 每个下游客户端会话一套上游子进程 | [`session-subprocess-model`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/session-subprocess-model.md) |
| MCP 能力状态——偏好存数据库，列表实时向上游查询 | [`capability-state-model`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/capability-state-model.md) |
| 工具过多：列出按用量排序的一部分，其余靠搜索 | [`tool-overload-tier-the-list-search-the-rest`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/tool-overload-tier-the-list-search-the-rest.md) |
| 评测：选择性捕获、人工整理，以及确定性的回归门禁 | [`eval-capture-and-regression-gate`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/eval-capture-and-regression-gate.md) |

## 智能体、提供商与内部引擎 {#agents-providers-the-internal-engine}

详见：[智能体](/zh/guides/agents)、[模型提供商](/zh/guides/providers)。

| 决定 | 记录 |
| --- | --- |
| 各智能体的行为放在每个智能体一条的描述记录里 | [`agent-descriptor-manifest`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/agent-descriptor-manifest.md) |
| 安全地写入智能体原生配置 | [`writing-agent-native-config-safely`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/writing-agent-native-config-safely.md) |
| Coffer 的智能体 Hook 按标记划定范围、显式安装、有审计，过期时会被修复 | [`agent-hook-installation`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/agent-hook-installation.md) |
| LLM 连接被投影进每个智能体自己的配置文件 | [`provider-connections-projected-into-agent-config`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/provider-connections-projected-into-agent-config.md) |
| 提供商的 API 密钥 从不落进智能体的原生配置 | [`provider-keys-never-land-in-native-config`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/provider-keys-never-land-in-native-config.md) |
| 模型目录从已安装的智能体读回 | [`model-catalogue-read-from-the-agent`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/model-catalogue-read-from-the-agent.md) |
| Coffer 自己的模型是内部引擎，不是角色，也不是工具 | [`coffer-model-is-an-internal-engine`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/coffer-model-is-an-internal-engine.md) |
| 引擎拥有自己的模型；它的接入地址借自一个被标记的连接 | [`internal-engine-settings`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/internal-engine-settings.md) |

## 对话与消息渠道 {#chat-channels}

详见：[对话与轮次](/zh/architecture/chat)、[消息渠道](/zh/guides/channels)。

| 决定 | 记录 |
| --- | --- |
| Coffer 通过 Agent SDK 驱动 Claude Code，通过 `codex app-server` 驱动 Codex | [`driving-agents-through-sdk-and-app-server`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/driving-agents-through-sdk-and-app-server.md) |
| 托管的智能体以完整权限运行；所有者配对就是那道门 | [`managed-agents-run-with-full-permissions`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/managed-agents-run-with-full-permissions.md) |
| 对话是单一所有者的实时镜像 | [`chat-single-owner-live-mirror`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/chat-single-owner-live-mirror.md) |
| 消息渠道是共享核心之上的薄传输适配器，在守护进程内受监管 | [`channel-adapter-framework`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-adapter-framework.md) |
| 消息渠道只回应已配对的所有者，在群组中默认拒绝 | [`channel-owner-gate`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-owner-gate.md) |
| 消息渠道对话以（渠道、聊天、线程）为键，并以其所在线程和引用为上下文 | [`channel-conversation-identity-and-context`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-conversation-identity-and-context.md) |
| 消息渠道中的切换：换智能体开新对话，换模型和推理强度下一轮生效 | [`channel-switches-structural-vs-parametric`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-switches-structural-vs-parametric.md) |
| 消息渠道的回复在同一个实时界面上增长，节奏由传输层决定 | [`channel-live-surface-strategy`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-live-surface-strategy.md) |
| 消息渠道附件：字节存磁盘，消息里放引用，发送时按智能体具体化 | [`channel-attachments`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-attachments.md) |
| 对话页面先上传文件再发送其 id，文件存进一个同级的媒体目录 | [`chat-attachment-uploads`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/chat-attachment-uploads.md) |
| SeaTalk 入站是一条出站 WebSocket，通过运维方提供的 SDK | [`seatalk-websocket-inbound`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/seatalk-websocket-inbound.md) |
| Telegram 入站是长轮询，分发之后才提交 offset | [`telegram-long-polling`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/telegram-long-polling.md) |

## 技能、知识与记忆 {#skills-knowledge-memory}

详见：[知识](/zh/architecture/knowledge)、[记忆](/zh/architecture/memory)、[技能](/zh/guides/skills)。

| 决定 | 记录 |
| --- | --- |
| 技能以指向唯一主目录的目录链接到达智能体 | [`cross-platform-skill-delivery`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/cross-platform-skill-delivery.md) |
| Coffer 把自己的说明书作为技能资源随包发布 | [`coffer-ships-its-own-skill`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/coffer-ships-its-own-skill.md) |
| 知识是一个 Markdown 文件目录，而不是索引 | [`knowledge-is-plain-files`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-plain-files.md) |
| 知识整理把新材料合并进文档 | [`knowledge-curation`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-curation.md) |
| 聚合智能体的记忆，从不写回 | [`aggregate-agent-memory-never-write-it`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/aggregate-agent-memory-never-write-it.md) |

## 同步与密钥 {#sync-secrets}

详见：[保险库同步](/zh/architecture/vault-sync)、[安全模型](/zh/architecture/security)。

| 决定 | 记录 |
| --- | --- |
| 保险库与一个用户自有的 git 远端收敛，由 git 的合并来裁决 | [`vault-sync`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/vault-sync.md) |
| 会丢失过多内容的一轮同步会被保留，双向都是如此，统计的是丢失而不是移动 | [`sync-deletion-breaker`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-deletion-breaker.md) |
| 机器由其主机自身 ID 的哈希标识，并在目录树中拥有一个描述文件 | [`sync-machine-identity`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-machine-identity.md) |
| 无人值守地改写已同步内容的任务，只在一台指定的所有者机器上运行 | [`single-owner-machine-for-unattended-rewrites`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/single-owner-machine-for-unattended-rewrites.md) |
| 同步不携带派生输出；每台机器自己渲染 | [`sync-withholds-derived-output`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-withholds-derived-output.md) |
| 信封加密的凭据存储 | [`envelope-encrypted-credential-store`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/envelope-encrypted-credential-store.md) |
| 资源以不透明引用来引用密钥，只在使用的那一刻解析 | [`credential-references`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/credential-references.md) |
| 凭据只以密文形式跨机器传递；主密钥和推送令牌从不进入仓库 | [`credentials-across-machines`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/credentials-across-machines.md) |
