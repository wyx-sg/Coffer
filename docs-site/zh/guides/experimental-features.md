---
title: 实验功能
description: Coffer 如何发布尚未就绪的能力——注册表、决定默认值的发布通道，以及在设置、命令行或 COFFER_FEATURES 中按机器开关。目前没有任何实验功能。
---

# 实验功能 {#experimental-features}

Coffer 的所有能力都在同一条开发主线上。当一项新能力还没准备好给所有人用时，它依然随每个构建发布，但作为**实验功能**：在发布构建中默认关闭，在源码构建中默认开启，并且可以在每台机器上单独开关。本页解释这套机制，让你在某个功能是实验功能时知道会发生什么。

::: info 目前没有任何实验功能
注册表是空的。同步、知识和记忆在 1.0 之前是实验功能，已在 1.0 转正：它们在每个构建中都始终开启，没有开关。**设置 → 通用** 中不显示实验功能区块，侧边栏也没有任何条目带 **实验** 标签，`coffer config list feature.` 什么也不列出。
:::

## 发布通道 {#release-channels}

每个 Coffer 构建都带有一个发布通道：

| 通道 | 哪些构建 | 实验功能默认 |
| --- | --- | --- |
| `stable` | 发布流程从 tag 构建出来的：桌面应用和发布归档 | 关 |
| `dev` | 其他所有构建，包括源码安装和本地桌面构建 | 开 |

查看你所在的通道：

```sh
coffer daemon status
```

```text
status:  ready
version: 1.0.0
channel: stable
port:    8000
pid:     41822
```

通道只决定实验功能的默认值。注册表为空时，两个通道表现完全相同。

## 开关某个功能 {#switch-a-feature-on-or-off}

某个功能注册后，会出现在以下几处：

- **设置 → 通用** 会多出实验功能区块，每个功能一个开关。
- **侧边栏** 会给该功能的入口加上 **实验** 标签，免得有人把它当成产品中已完成的部分。
- **该功能的页面** 在功能关闭时会显示一条提示，带 **开启**（与设置 → 通用中的开关作用相同，并立即打开页面）和 **打开设置** 两个按钮。被 `COFFER_FEATURES` 固定的功能会改为说明这一点，且没有按钮。
- **`coffer config`** 会多出一个 `feature.<key>` 键：

```sh
coffer config list feature.            # every feature, its state, and what decided it
coffer config set feature.<key> on
coffer config set feature.<key> off
coffer config unset feature.<key>      # back to the channel default
```

开关立即生效，无需重启，并且只保存在本机的 `~/.coffer/daemon-config.json` 中。它从不同步，所以在笔记本上打开某个功能不会影响台式机。同样的开关对应 `PUT /api/v1/daemon/features/{key}`，对该路径执行 `DELETE` 则回到通道默认值。`feature.*` 键要经过运行中的守护进程，因为只有它能让开关立即生效。

注册表中没有声明的键会被拒绝：REST 路由返回 `FEATURE_UNKNOWN`，`coffer config set feature.<key>` 报告未知设置。知识已经转正，所以现在运行 `coffer config set feature.knowledge off` 得到的就是这个回答。

## 功能状态如何决定 {#how-a-feature-s-state-is-decided}

对每个功能，以下各项中第一个给出答案的胜出：

1. 守护进程所在进程的 `COFFER_FEATURES` 环境变量中的**固定值**。
2. **本机设置**，由上面的开关写入。
3. **通道默认值**：`stable` 上关，`dev` 上开。

### 用 `COFFER_FEATURES` 固定功能 {#pin-a-feature-with-coffer-features}

`COFFER_FEATURES` 在一个守护进程的整个生命周期内固定功能状态，适合测试和脚本化部署：

```sh
COFFER_FEATURES=<key>=on,<other-key>=off coffer daemon restart
```

条目是逗号分隔的 `key=value`；`on`、`true` 和 `1` 表示开启，`off`、`false` 和 `0` 表示关闭。未知的键或格式错误的条目会记一条警告并被忽略，所以指向已转正功能的旧固定值不会造成问题。

被固定的功能无法切换：写入会返回 `409 FEATURE_PINNED`。这个变量必须位于启动守护进程的那个进程的环境中。守护进程由最先需要它的入口启动（命令行、智能体的 MCP shim、桌面应用、开机自启服务），所以在某个 shell 里导出的变量，到不了从别处启动的守护进程。

## 「关闭」意味着什么 {#what-off-means}

关闭一个功能会在本机的所有入口上关掉它：

- **REST**：它的路由返回 `404`，错误码为 `FEATURE_DISABLED`，并带上功能的键。该功能拥有的类型的资源也会从通用的 `/api/v1/resources` 路由中隐藏。
- **命令行**：它的命令打印一行提示 `coffer config set feature.<key> on`，并以退出码 1 退出。
- **MCP**：属于该功能的内置工具从工具列表中移除，调用它会按未知工具应答。
- **Web 界面**：它的侧边栏入口消失，它的页面显示一条提示，写明重新开启的命令。
- **后台任务**：它的后台任务跳过每一轮。

如果某个功能在智能体面前放置了东西，例如智能体配置中的一个 Hook，关闭时会撤回，开启时会放回。

::: tip 什么都不会被删除
关闭一个功能从不删除、移动或改写它所保存的内容。重新开启后，它会从原来的状态接着工作。数据库迁移无论开关如何都会执行，所以开启一个功能永远不需要改 schema。
:::

## 功能如何加入和退出 {#how-a-feature-joins-and-leaves}

一个功能**加入**的方式是往注册表 [`backend/coffer/domain/features.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/domain/features.py) 中添加一条。该条目写明功能的键、它拥有的 REST 路由前缀和资源类型。所有入口都读这一份列表：这些前缀下的路由和这些类型的资源会被管控，标明该功能的内置 MCP 工具在关闭时离开工具列表，标明该功能的侧边栏入口带上「实验」标签并在关闭时隐藏，它的后台任务每一轮都检查它。设置区块和 `coffer config list feature.` 会自动识别它，无需额外工作。

一个功能**退出**的方式是在就绪后转正。它的注册表条目被删除，所有引用它的管控都被删除，并由一次迁移从 `daemon-config.json` 中剥掉它存储的设置。从此它就是 Coffer 的普通组成部分，它的旧键变为未知。同步、知识和记忆就是在 1.0 以这种方式退出的。

## 工作原理 {#how-it-works}

把未完成的工作放在注册表条目后面、而不是单独的发布分支上，这一决定记录在 [Experimental Features Instead of a Release Branch](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/experimental-features-instead-of-a-release-branch.md) 中。架构见[分发与发布](/zh/architecture/distribution#experimental-features)。

## 相关内容 {#related}

- [运行守护进程](/zh/guides/daemon)
- [配置参考](/zh/reference/configuration)
- [错误码](/zh/reference/error-codes)
- 规格：[experimental-features](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/experimental-features/spec.md)
