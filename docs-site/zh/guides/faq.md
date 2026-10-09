---
title: 常见问题
description: 关于 Coffer 的常见问题简答——隐私、支持的智能体和平台、模型、费用、多台机器、数据存放位置以及卸载。
---

# 常见问题 {#faq}

对安装 Coffer 前后最常被问到的问题的简短回答，并附上深入介绍每个主题的页面链接。

## 会有东西离开我的机器吗？ {#does-anything-leave-my-machine}

除非你自己配置，否则 Coffer 不会主动这么做。守护进程只监听 `127.0.0.1`，没有遥测，状态都保存在 `~/.coffer` 下。只有你设置的东西才会产生网络流量：

- **你注册的 MCP 服务器。** Coffer 启动 stdio 服务器，或连接你给的 URL 上的 HTTP 服务器；它们会访问什么，由各个服务器决定。
- **模型提供商。** 如果你为 **语音转文字** 选择了提供商，Coffer 会把语音消息发给它转写。你的智能体照常和它们自己的提供商通信。
- **保险库同步。** 如果你配置了远端，同步轮次会向那个 git 仓库推送和拉取。密钥只以密文传输，而且只有你选择开启时才会传；主密钥永远不会。
- **消息渠道。** Telegram 或 SeaTalk 渠道会与对应平台收发消息。

你自己配置的端点——HTTP MCP 服务器、模型或转写的接入地址、同步远端——可以位于你自己的机器或网络上。而 Coffer 只是在你填表时代为探测的 URL（提供商编辑器里的 **测试** 和模型列表），如果解析到私有或链路本地地址，会被拒绝；回环地址则允许，这正是你自己机器上的模型运行时能用的原因。

见[安全模型](/zh/architecture/security)。

## Coffer 支持哪些智能体？ {#which-agents-does-coffer-support}

Coffer 管理 **Claude Code** 和 **Codex**：它会检测它们、把自己的 MCP 条目装进去、投递技能、在它们之间同步记忆、把模型提供商投射到它们的配置中，并能在[对话](/zh/guides/chat)和[消息渠道](/zh/guides/channels)中运行它们。

其他任何能启动 stdio 服务器的 MCP 客户端，也可以运行 `coffer-mcp-shim` 来使用 Coffer 的网关。这类会话不报告智能体身份，所以只能看到生效范围不限于特定智能体的服务器。见[连接客户端](/zh/guides/connect-a-client)。

## 能在 Linux 或 Windows 上用吗？ {#can-i-use-it-on-linux-or-windows}

发布包、一行安装脚本和桌面应用都只为 **Apple 芯片的 macOS** 构建。其他平台既不构建也不测试。开机自启守护进程同样仅限 macOS。见[安装](/zh/start/install)。

## Coffer 会运行语言模型吗？ {#does-coffer-run-a-language-model}

Coffer 内部不运行任何模型，只有一个可选的例外：转写语音消息，它会调用你在 **设置 › 通用 → 语音转文字** 中选择的模型提供商。在你选择之前，语音消息以音频文件的形式交给智能体。整理知识是智能体的工作：知识集上的**整理**会打开一个与你的默认智能体的对话，并把指令发给它。整理记忆是每个智能体自己的事：记忆页上的**立即整理**请智能体用它自己的模型整合它的记忆。

其余一切都是确定性的、本地的。`coffer__search_tools` 按关键词给工具排序，智能体用自己的文件工具查找知识，在自己的记忆里找到记忆，没有任何东西做向量嵌入。见[模型提供商](/zh/guides/providers)。

## 要花多少钱？ {#what-does-it-cost}

Coffer 免费且开源，采用 GNU AGPL v3.0（或更高版本）许可证。唯一的费用是你本来就有的：你的智能体（以及你配置的语音转文字）所调用的模型提供商，以及你为同步远端选择的托管服务。

## 这和在每个智能体的配置里列出 MCP 服务器有什么不同？ {#how-is-this-different-from-listing-mcp-servers-in-each-agent-s-config}

按智能体分别配置时，每个服务器都要在每个智能体里注册、更新和保护一遍。用 Coffer：

- 服务器注册一次，所有智能体都通过同一个 MCP 条目访问它；
- 它的密钥加密保存在 Coffer 的存储中，而不是以明文躺在智能体配置文件里；
- 你可以按服务器选择哪些智能体可以使用它，并关掉单个工具；
- 工具名按服务器加命名空间（`github__search`），两个服务器永远不会冲突；
- 每次调用都会被记录（不含参数），供[活动](/zh/guides/activity)查看；
- 庞大的工具目录会在预算内列出，其余的由智能体通过 `coffer__search_tools` 查找。

技能、知识和模型提供商也是同样的方式：保存一次，投递给每个智能体。记忆则是同步的：一个智能体学到的东西会被复制进其他智能体自己的记忆。见[为什么选择 Coffer](/zh/start/why-coffer)。

## Coffer 会修改我的智能体配置文件吗？ {#does-coffer-change-my-agents-configuration-files}

只有在你要求时才会，而且每次改动都记录在审计日志里。把智能体接入 Coffer，会往智能体配置里写一个 MCP 服务器条目。投递技能会在智能体的技能目录中放一个指向它的链接（对 Claude Code 来说是 `~/.claude/skills`）。切换模型提供商会把提供商的设置写进智能体自己的配置。开启实验性的记忆功能后，[记忆同步](/zh/guides/memory)会把你其他智能体的记忆副本写进每个智能体的记忆，放在 Coffer 自己拥有的文件里，从不改动智能体自己写的记忆；**撤销同步…**会移除这些副本。见[智能体](/zh/guides/agents)。

## 我需要自己启动守护进程吗？ {#do-i-have-to-start-the-daemon-myself}

不需要。任何需要守护进程的 `coffer` 命令、通过 `coffer-mcp-shim` 连接的智能体以及桌面应用，在守护进程没运行时都会启动它。`coffer daemon status` 是例外：它只报告状态，会说 `not running` 而不是启动一个。在 macOS 上，**设置 → 守护进程 → 开机自启动** 会让它开机启动，并在崩溃后重启。见[运行守护进程](/zh/guides/daemon)。

## 我的数据在哪里？ {#where-is-my-data}

在每台机器的 `~/.coffer` 中：

| 路径 | 内容 |
| --- | --- |
| `vault/` | 存放你的配置和内容的 git 仓库：每个资源一个 JSON 文件、知识集、记忆中心库、技能文件夹、加密密钥 |
| `local/` | 只属于本机的设置：智能体、生效范围、保留策略、同步远端 |
| `content/` | 附件和聊天工作目录 |
| `runs.db` | 历史：对话、审计和调用日志、同步轮次、用量 |
| `derived/` | Coffer 可重建的内容，例如它自己的指南技能和 MCP 服务器健康状态 |
| `logs/` | 守护进程、shim 和 MCP 服务器日志 |
| `bin/` | 已部署的二进制（发布版安装） |

完整列表见[文件与目录](/zh/reference/filesystem)。

## 我的密钥是怎么存储的？ {#how-are-my-secrets-stored}

密钥用 Fernet 加密，每个密钥一个文件，位于 `~/.coffer/vault/secret/` 下。主密钥放在 macOS 钥匙串中，只有 Coffer 的签名二进制能读取。资源通过引用来指明密钥，从不直接写值。见[密钥存储](/zh/guides/secret-store)。

## 两台机器能共用一个保险库吗？ {#can-two-machines-share-one-vault}

可以，通过[保险库同步](/zh/guides/vault-sync)。每台机器把自己的保险库仓库推送到、拉取自你拥有的私有 git 仓库。知识、技能和资源定义会同步。智能体、生效范围（某个资源在某台机器上是否启用、对哪些智能体启用）、对话和日志留在各自的机器上。

## 能从手机或另一台电脑打开 Web 界面吗？ {#can-i-open-the-web-ui-from-my-phone-or-another-computer}

不能。守护进程只绑定回环地址，所以它的界面和 API 只能在运行它的机器上访问，别处都不行。要从手机访问你的智能体，请用[消息渠道](/zh/guides/channels)：Telegram 或 SeaTalk。

## 为什么是 38470 端口，能改吗？ {#why-port-38470-and-can-i-change-it}

固定端口能让书签一直可用，也能保住浏览器为界面存储的偏好设置。用 `coffer config set daemon.port <port>` 修改，然后运行 `coffer daemon restart`。见[选择端口](/zh/guides/daemon#choose-the-port)。

## 怎么升级？ {#how-do-i-upgrade}

桌面应用会在**设置 › 关于**里自我更新。用一行安装脚本安装的，运行 `coffer update`：它会安装最新发布，并让守护进程以新版本重启。源码安装则拉取代码、重新安装，再运行 `coffer daemon restart`。见[安装 → 升级](/zh/start/install#upgrade)。上一个构建保留在 `~/.coffer/bin` 中以便回滚，历史数据库在任何迁移之前都会先复制一份。另见[升级与回滚](/zh/guides/daemon#upgrades-and-rollback)。

## 怎么卸载 Coffer？ {#how-do-i-uninstall-coffer}

在桌面应用的**设置 › 关于**里选择**卸载 Coffer…**，或者运行 `coffer uninstall`。Coffer 会断开你的智能体，让运行在提供商上的智能体回到它们自己的登录，移除它投递的技能链接、终端启动文件、开机自启动、它的二进制和 `PATH` 行以及应用本身，并保留 `~/.coffer` 以便重新安装。是否同时删除数据是单独的选择，需要 Touch ID。见[安装 → 卸载](/zh/start/install#uninstall)。

如果你用过保险库同步，远端仓库不受影响，仍保存着你保险库里的文档。

## 在哪里报告 bug？ {#where-do-i-report-a-bug}

在 [GitHub Issues](https://github.com/wyx-sg/Coffer/issues)。[故障排查](/zh/guides/troubleshooting#collect-information-for-a-bug-report)列出了需要附上的信息。安全问题请按[安全策略](/zh/contributing/security)中的说明私下报告。
