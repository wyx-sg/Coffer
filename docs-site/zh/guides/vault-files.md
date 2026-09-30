---
title: 手动编辑保险库
description: Coffer 的配置和内容都是 ~/.coffer/vault 这个 git 仓库里的普通文件——用任何编辑器修改它们，查看 Coffer 如何处理你的改动，并读取、对比和恢复任意版本。
---

# 手动编辑保险库 {#editing-the-vault-by-hand}

Coffer 保存的、你希望带到另一台机器上的一切——MCP 服务器、技能、知识、提供商、消息渠道以及它们的设置——都是 `~/.coffer/vault` 里的普通文件，而这个目录从 Coffer 第一次运行起就是一个 git 仓库。本页写给想直接修改这些文件的人：用编辑器、shell 或智能体自己的文件工具去改，并了解 Coffer 会怎么处理这些改动、怎样撤销。

## 保险库里有什么 {#what-is-in-the-vault}

```text
~/.coffer/vault/
├── resources/<kind>/<name>.json        one file per MCP server, skill, channel, provider, knowledge collection
├── state/mcp-preferences/<server>.json the tools, prompts and resources you switched off on a server
├── state/channel-peers/<channel>.json  who is paired with a channel
├── state/settings/internal-engine.json Coffer's model and upkeep settings
├── knowledge/<collection>/…            knowledge documents (Markdown)
├── skills/<name>/…                     skill folders (SKILL.md and the rest)
├── memory-triggers/<id>.md             memory triggers
├── secret/<ref>.enc                    encrypted secrets (never edit these)
└── machines/<id>.json                  one descriptor per machine that syncs
```

`coffer path vault` 打印它的位置。智能体不在这里：智能体的配置只关乎某一台机器，所以放在 `~/.coffer/local/resources/agent/`。生效范围（本机哪些智能体可以使用某个资源）也不在这里，而是在 `~/.coffer/local/reach.json`。见[文件与目录](/zh/reference/filesystem)。

## 编辑文件 {#edit-a-file}

用任何编辑器打开并保存即可。资源文件是 JSON：

```json
{
  "uid": "5f0c1e9a2b7d4c3e8a6f9b0d1c2e3f4a",
  "kind": "mcp_server",
  "format_version": 1,
  "name": "jira",
  "description": "Company Jira",
  "config": {
    "transport": {
      "type": "stdio",
      "command": "${HOME}/.local/bin/jira-mcp",
      "args": ["--verbose"]
    }
  }
}
```

需要了解的几条规则：

- **保留 `uid`。** 它是资源的身份。你可以给文件改名，或在它所属类型的文件夹内移动，它仍是同一个资源。你新建的文件如果没有 `uid`，Coffer 会分配一个，并用单独一次提交把它写进文件。`uid` 相同的副本会被拒绝并标记出来，原文件继续生效。
- **`name` 是一个标签**，但有些类型在智能体能看到它之后就把它固定了（MCP 服务器的名字是其工具名的一部分）。Coffer 拒绝改名时，请通过 Coffer 来改名。
- **未知的顶层字段会被保留。** 与 `uid`、`kind`、`name`、`config` 并列、但本构建不认识的字段会报一个警告，但绝不会被丢掉，所以更新版本的 Coffer 添加的字段在你编辑后依然存在。
- **`config` 只能包含该类型拥有的设置。** 该类型没有声明的键（笔误，或 Coffer 已废弃的设置）会被拒绝：这次编辑不会提交，问题会指出是哪个键，最后一个有效版本继续生效。类型不允许的名字也一样（MCP 服务器的名字最多 24 个字符且不能含 `__`；技能的名字只能用小写字母、数字和连字符），MCP 服务器、智能体或技能上出现 `title` 也一样，它们没有这个字段。
- **`${HOME}`** 代表你的主目录，所以同一个文件在每台机器上都能用。
- **永远不要编辑 `secret/`。** 这些文件是密文；请用 `coffer secret set`。

知识文档和技能文件夹就是普通文件：像对待任何 Markdown 一样编辑、新增、移动和删除即可。

## 保存之后会发生什么 {#what-happens-when-you-save}

Coffer 会察觉到改动，等文件安静一秒（这样编辑器连续多次保存算作一次改动），然后用和 Web 界面编辑相同的规则检查它。

- **有效的编辑会被提交**为一个由 `disk` 写入的版本（界面中显示为「在磁盘上编辑」），在审计日志中以 `vault_file_edited` 记录为人为操作，并随即生效：调和器会把变化的部分重新投射到你的智能体中。
- **无效的编辑不会被应用。** 它留在文件里、不提交，最后一个有效版本继续生效。它会被标记在待处理列表上，并可通过以下命令列出：

  ```sh
  coffer vault problems
  ```

  修好文件再保存，或者恢复到上一个版本（见下文）。

Coffer 还会每分钟以及启动时扫描一次保险库，所以守护进程停止期间做的编辑在它启动后也会被接收。判断依据是文件内容，从不看修改时间。

你正在编辑某个文件时，Coffer 不会覆盖它：通过 Web 界面对同一文件的保存会因过期（`VAULT_FILE_STALE`）而被拒绝，而不是悄悄丢失；会改动它的同步轮次也会等你。

## 历史与恢复 {#history-and-restore}

保险库的每一次被接受的改动都是一个版本，记录时间、写入者（你、在磁盘上编辑、智能体、Coffer、整理或同步）以及哪台机器。任何文件或文件夹都有历史：

```sh
coffer vault history resources/mcp_server/jira.json
coffer vault history skills/pdf/                 # a folder ends in /
coffer vault diff resources/mcp_server/jira.json <version>
coffer vault show resources/mcp_server/jira.json <version>
coffer vault restore skills/pdf/ <version>
```

路径相对于保险库。`<version>` 来自 `history`。恢复会把那个版本的内容作为一个**新**版本放回去，标注为从旧版本恢复，并经过和其他写入相同的检查：不会原地改写任何东西，所以你还可以恢复这次恢复。恢复文件夹会整体放回，删除那个版本里没有的文件。恢复前会先询问；`--yes` 跳过询问。密钥没有可读的历史，不能这样恢复。

在 Web 界面里，技能的 **历史** 标签页列出它的各个版本及每个版本的写入者，逐文件展示每个版本的改动，并在询问后恢复某个版本。知识文档在 **知识** 页面上有同样的历史。

你也可以直接用 git 读历史（`git -C ~/.coffer/vault log`）。但做改动时请编辑文件、让 Coffer 来提交：它的提交带有标明写入者的 trailer，而且它会校验所提交的内容。

## 相关内容 {#related}

- [持久化](/zh/architecture/persistence)：写入者模型与五种存储类别
- [保险库同步](/zh/guides/vault-sync)：把保险库带到其他机器
- [技能](/zh/guides/skills) · [知识](/zh/guides/knowledge) · [文件与目录](/zh/reference/filesystem)
- 决策记录：[Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md)
