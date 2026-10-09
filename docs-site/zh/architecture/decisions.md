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

每份记录都标着自己的状态，下面列出的每一份都是 `Accepted`：已经生效，陈述的是现行设计。[目录 README](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/README.md) 是权威索引；本页与某份记录自己的 `Status` 行不一致时，以记录为准。

## 资源框架与持久化 {#resource-framework-persistence}

详见：[资源框架](/zh/architecture/resource-framework)、[持久化](/zh/architecture/persistence)、[调和器](/zh/architecture/reconciler)、[平台端口](/zh/architecture/platform)。

| 决定 | 记录 |
| --- | --- |
| 资源框架是核心领域，在第二种类型出现之前就设计好 | [`resource-framework-upfront`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/resource-framework-upfront.md) |
| 一种类型以一条冻结的可选 Hook 记录接入：写入前做校验，写入后做响应 | [`kind-plugin-contract`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/kind-plugin-contract.md) |
| 资源的身份是它文件里的 `uid`；路径和名称只是位置和标签 | [`identity-is-the-uid-inside-the-file`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/identity-is-the-uid-inside-the-file.md) |
| 智能体能看到的名称是固定的 | [`names-visible-to-agents-are-fixed`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/names-visible-to-agents-are-fixed.md) |
| 按智能体划分的资源作用范围是框架中的一份白名单，由各类型自行执行 | [`per-agent-resource-scope`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/per-agent-resource-scope.md) |
| 生效范围归本机：按 uid 存在 `local/reach.json` 中，从不同步 | [`reach-is-machine-local-stored-by-uid-never-synced`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/reach-is-machine-local-stored-by-uid-never-synced.md) |
| 代码按层优先布局，每种类型一个子目录 | [`code-layout-layer-first`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/code-layout-layer-first.md) |
| 各类型由唯一的组合根显式装配，没有全局注册表 | [`composition-root-explicit-wiring`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/composition-root-explicit-wiring.md) |
| 存储按性质分五类；某一类是否同步是策略 | [`storage-is-five-classes-by-nature`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/storage-is-five-classes-by-nature.md) |
| 历史记录是一个 SQLite 文件，只由守护进程写入，开机时经唯一一条 Alembic 迁移链向前迁移 | [`history-is-one-sqlite-file-written-only-by-the-daemon`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/history-is-one-sqlite-file-written-only-by-the-daemon.md) |
| 每个保险库文件都带着自己的格式版本；布局升级由一台所有者机器提交 | [`every-vault-file-carries-its-format-version`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/every-vault-file-carries-its-format-version.md) |
| 每次保险库写入都是一次经过校验、比较并交换、写明写入者的提交 | [`every-vault-write-is-a-validated-commit-naming-its-writer`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md) |
| 每次改动都连同执行者一起审计，调用日志不记载荷，按表清理 | [`audit-and-retention`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/audit-and-retention.md) |
| 一个电平触发的调和器收敛 Coffer 在数据库之外写下的一切，比较的是参数 | [`one-level-triggered-reconciler-compares-parameters`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/one-level-triggered-reconciler-compares-parameters.md) |
| 线上契约由 Pydantic 模型生成，前端客户端再由契约生成 | [`wire-contract-generated-from-the-pydantic-models`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/wire-contract-generated-from-the-pydantic-models.md) |
| 后台工作受监督运行，每条记录都带同一个关联 id | [`background-work-runs-supervised-and-correlated`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/background-work-runs-supervised-and-correlated.md) |
| 平台差异都在一个平台端口之后；只发布 macOS | [`platform-differences-live-behind-one-platform-port`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/platform-differences-live-behind-one-platform-port.md) |

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
| 侧边栏按人来做的事分组：智能体、运行、能力、上下文、系统 | [`sidebar-grouped-by-what-the-person-comes-to-do`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md) |

## MCP 网关 {#mcp-gateway}

详见：[MCP 网关](/zh/architecture/mcp-gateway)。

| 决定 | 记录 |
| --- | --- |
| 每个下游客户端会话一套上游子进程 | [`session-subprocess-model`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/session-subprocess-model.md) |
| MCP 能力状态：偏好存在保险库中，列表向上游实时查询 | [`mcp-capability-state-preferences-in-the-vault-lists-live-queried-from-upstream`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/mcp-capability-state-preferences-in-the-vault-lists-live-queried-from-upstream.md) |
| 工具过多：列出按用量排序的一部分，其余靠搜索 | [`tool-overload-tier-the-list-search-the-rest`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/tool-overload-tier-the-list-search-the-rest.md) |
| 评测：选择性捕获、人工整理，以及确定性的回归门禁 | [`eval-capture-and-regression-gate`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/eval-capture-and-regression-gate.md) |

## 智能体与提供商 {#agents-providers}

详见：[智能体](/zh/guides/agents)、[模型提供商](/zh/guides/providers)、[智能体切面](/zh/architecture/agent-facets)、[模型代理](/zh/architecture/model-proxy)。

| 决定 | 记录 |
| --- | --- |
| 各智能体的行为放在每个智能体一条的描述记录里 | [`agent-descriptor-manifest`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/agent-descriptor-manifest.md) |
| 智能体机制是描述符上的可选切面，投射是一张注册表 | [`agent-mechanisms-are-optional-facets-on-the-descriptor`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/agent-mechanisms-are-optional-facets-on-the-descriptor.md) |
| 安全地写入智能体原生配置 | [`writing-agent-native-config-safely`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/writing-agent-native-config-safely.md) |
| Coffer 的智能体 Hook 按标记划定范围、显式安装、有审计，过期时会被修复 | [`agent-hook-installation`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/agent-hook-installation.md) |
| LLM 连接被投影进每个智能体自己的配置文件 | [`provider-connections-projected-into-agent-config`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/provider-connections-projected-into-agent-config.md) |
| API 密钥类提供商经由一个独立的本地模型代理访问，代理原样转发字节 | [`api-key-providers-are-reached-through-a-separate-local-model-proxy`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/api-key-providers-are-reached-through-a-separate-local-model-proxy.md) |
| 用量在代理处计量；订阅制智能体不计量 | [`usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota.md) |
| 模型目录从已安装的智能体读回 | [`model-catalogue-read-from-the-agent`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/model-catalogue-read-from-the-agent.md) |
| 语音转文字的模型是一项设置；它的接入地址借自一个被标记的连接 | [`internal-engine-settings`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/internal-engine-settings.md) |

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
| 消息渠道中的切换：换智能体开新对话，换模型下一轮生效 | [`channel-switches-structural-vs-parametric`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-switches-structural-vs-parametric.md) |
| 消息渠道的轮次在有预览界面的平台上显示进度，回复只含答案 | [`channel-live-surface-strategy`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-live-surface-strategy.md) |
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
| 整理知识与记忆是智能体的工作 | [`tidying-knowledge-and-memory-is-the-agents-job`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/tidying-knowledge-and-memory-is-the-agents-job.md) |
| 聚合智能体的记忆，从不写回 | [`aggregate-agent-memory-never-write-it`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/aggregate-agent-memory-never-write-it.md) |
| 记忆在三个时刻进入会话：开始时一份索引、每次提示时检索、踩到已知陷阱前一道防护 | [`memory-reaches-a-session-at-prompt-time-and-before-a-known-trap`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/memory-reaches-a-session-at-prompt-time-and-before-a-known-trap.md) |

## 同步与密钥 {#sync-secrets}

详见：[保险库同步](/zh/architecture/vault-sync)、[安全模型](/zh/architecture/security)。

| 决定 | 记录 |
| --- | --- |
| 同步只拉取和推送保险库仓库；干净的合并直接应用，任何冲突都停下来交给人 | [`sync-applies-clean-merges-and-stops-on-any-conflict`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-applies-clean-merges-and-stops-on-any-conflict.md) |
| 会丢失过多内容的一轮同步会被保留，双向都是如此，统计的是丢失而不是移动 | [`sync-deletion-breaker`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-deletion-breaker.md) |
| 机器由其主机自身 ID 的哈希标识，并在目录树中拥有一个描述文件 | [`sync-machine-identity`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-machine-identity.md) |
| 同步不携带派生输出；每台机器自己渲染 | [`sync-withholds-derived-output`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/sync-withholds-derived-output.md) |
| 主密钥存放在只有 Coffer 签名二进制能读取的钥匙串访问组中；密钥在保险库里仍以信封加密保存 | [`master-key-lives-in-the-macos-keychain`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/master-key-lives-in-the-macos-keychain.md) |
| 资源以不透明引用来引用密钥，只在使用的那一刻解析 | [`credential-references`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/credential-references.md) |
| 密钥只以密文形式跨机器传递；主密钥和推送令牌从不进入仓库 | [`secrets-cross-machines-only-as-ciphertext`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/secrets-cross-machines-only-as-ciphertext.md) |
| 独立密钥是具名的 `coffer://secret/` 引用，只注入一个子进程 | [`standalone-secrets-are-named-references-injected-into-one-child`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/standalone-secrets-are-named-references-injected-into-one-child.md) |
| 智能体可以配置 Coffer；只有在场的人能看到密钥明文或把它发往新的地方 | [`only-a-present-human-sees-a-secret-or-sends-it-somewhere-new`](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md) |
