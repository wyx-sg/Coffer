---
title: 实验功能
description: 默认关闭的四项能力——知识、记忆、同步和模型提供商——以及如何在设置、命令行或 COFFER_FEATURES 中按机器开启，和功能关闭时看起来是什么样。
---

# 实验功能 {#experimental-features}

Coffer 只发布一个构建，里面包含所有能力。其中少数能力尚未经过充分验证，所以它们一开始是**关闭**的，由你按机器决定要试用哪些。本页介绍这四个实验功能，以及某个功能关闭时你会看到什么。

稳定版和源码构建在这方面行为一致：每个实验功能在你开启之前都是关闭的。

## 四个功能 {#the-four-features}

| 键 | 名称 | 涵盖内容 |
| --- | --- | --- |
| `knowledge` | 知识 | 知识页面及其文件、`coffer__write` 工具，以及 `coffer-guide` 技能中的知识部分。 |
| `memory` | 记忆 | 记忆页面、智能体中的记忆投递 Hook，以及渠道对话中的记忆。 |
| `sync` | 同步 | 保险库同步到你自己的 git 远端。 |
| `models` | 模型提供商 | 模型提供商、本地模型代理和用量，以及把连接投射到智能体自己配置文件中的做法。 |

其余一切始终开启：应用外壳、总览、智能体、MCP 网关和自定义工具、技能、密钥、活动、设置、对话和消息渠道。智能体列表及其模型目录、Coffer 自己的模型设置、保险库以及智能体自己的会话记录和记忆文件也不受这些开关控制。

### 功能之间的关系 {#how-the-features-relate}

没有哪个功能需要另一个功能。某个功能关闭时，其他功能照常工作：

| 关闭的功能 | 会怎样 |
| --- | --- |
| `knowledge` | 知识页面及其 API 消失，`coffer__write` 被隐藏，`coffer-guide` 技能没有知识目录，整理跳过，渠道的 `/kb` 回答知识已关闭。记忆不受影响。 |
| `memory` | 记忆页面及其 API 消失，握手信息不再提到记忆根目录，记忆 Hook 从智能体中撤出（开启后放回），提炼和聚合跳过，渠道对话不带记忆。知识不受影响。 |
| `sync` | 整理把保险库当作单机保险库。 |
| `models` | 本地代理和用量消失，Coffer 的密钥从智能体自己的配置中撤出，智能体改用它们自己的登录。知识和记忆继续使用已经为 Coffer 引擎选好的模型连接。 |

## 开关某个功能 {#switch-a-feature-on-or-off}

每个功能默认关闭。你可以在两个地方为本机开启它：

- **设置 → 功能** 列出四个功能，每个都带**实验**标记、一行说明和一个开关。这个标签页在每个构建中都有。如果功能被固定（见下文），开关会被禁用并说明原因。
- **`coffer config`** 为每个功能提供一个 `feature.<key>` 键：

```sh
coffer config list feature.            # every feature, its state, and what decided it
coffer config set feature.models on
coffer config set feature.models off
coffer config unset feature.models     # back to off
```

```text
feature.knowledge = off (default)
feature.memory = on (setting)
feature.sync = off (pin)
feature.models = off (default)
```

开关立即生效，无需重启，并且只保存在本机的 `~/.coffer/daemon-config.json` 中。它从不同步，所以在笔记本上打开某个功能不会影响台式机。同样的开关对应 `PUT /api/v1/daemon/features/{key}`，对该路径执行 `DELETE` 则回到关闭。

指向 Coffer 不认识的功能的设置会被忽略，请求未知的键会被拒绝并返回 `FEATURE_UNKNOWN`。

## 功能状态如何决定 {#how-a-feature-s-state-is-decided}

对每个功能，以下各项中第一个给出答案的胜出：

1. 守护进程所在进程的 `COFFER_FEATURES` 环境变量中的**固定值**。
2. **本机设置**，由上面的开关写入。
3. **默认值**，每个功能都是关。

列表会显示每个功能由哪一项决定：`pin`、`setting` 或 `default`。

### 用 `COFFER_FEATURES` 固定功能 {#pin-a-feature-with-coffer-features}

`COFFER_FEATURES` 在一个守护进程的整个生命周期内固定功能状态，适合测试和脚本化部署：

```sh
COFFER_FEATURES=knowledge=on,models=off coffer daemon restart
```

条目是逗号分隔的 `key=value`；`on`、`true` 和 `1` 表示开启，`off`、`false` 和 `0` 表示关闭。未知的键或格式错误的条目会记一条警告并被忽略。

被固定的功能无法切换：写入会返回 `409 FEATURE_PINNED`。这个变量必须位于启动守护进程的那个进程的环境中。守护进程由最先需要它的入口启动（命令行、智能体的 MCP shim、桌面应用、开机自启服务），所以在某个 shell 里导出的变量，到不了从别处启动的守护进程。

## 「关闭」时是什么样 {#what-off-looks-like}

关闭的功能看起来就像不存在。网页界面中没有任何地方提到它：

- **网页界面**：它的侧边栏入口消失（入口都没了的分组标题也一并消失），它不在命令面板中，总览上没有它的卡片和首次使用引导，其他页面也没有为它保留的区块。直接打开它的页面链接会显示标准的「未找到」页面。除了设置 → 功能之外，没有任何提示，也没有**开启**按钮。
- **REST**：它的路由返回 `404`，错误码为 `FEATURE_DISABLED`，并带上功能的键。该功能拥有的类型的资源也会从通用的 `/api/v1/resources` 路由中隐藏。
- **命令行**：它的命令打印一行提示 `coffer config set feature.<key> on`，并以退出码 1 退出。
- **MCP**：属于该功能的内置工具从工具列表中移除，调用它会按未知工具应答。
- **后台任务**：它的后台任务跳过每一轮。

功能开启期间，它的侧边栏入口带有**实验**标签，免得有人把它当成产品中已完成的部分。

::: tip 什么都不会被删除
关闭一个功能从不删除、移动或改写它所保存的内容。重新开启后，它会从原来的状态接着工作。数据库迁移无论开关如何都会执行，所以开启一个功能永远不需要改 schema。
:::

## 工作原理 {#how-it-works}

把未完成的工作放在注册表条目后面、而不是单独的发布分支上，这一决定记录在 [Experimental Features Instead of a Release Branch](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/experimental-features-instead-of-a-release-branch.md) 中。架构见[分发与发布](/zh/architecture/distribution#experimental-features)。

## 相关内容 {#related}

- [运行守护进程](/zh/guides/daemon)
- [配置参考](/zh/reference/configuration)
- [错误码](/zh/reference/error-codes)
- 规格：[experimental-features](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/experimental-features/spec.md)
