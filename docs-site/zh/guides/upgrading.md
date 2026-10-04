---
title: 升级现有的 Coffer
description: 用 coffer migrate 把 Coffer home 从单一的 coffer.db 数据库迁到保险库布局——先演练、再执行、必要时回滚，并替换你的同步远端。
---

# 升级现有的 Coffer {#upgrading-an-existing-coffer}

Coffer 以前把配置存在一个 SQLite 数据库 `~/.coffer/coffer.db` 里，旁边是知识和技能的文件树。现在它把状态分成[五种存储类别](/zh/architecture/persistence)：保险库 git 仓库、本地 JSON、内容、历史数据库和派生状态。把现有 home 迁过来是一次性的步骤，由你自己用 `coffer migrate` 执行。本页写给用过早期 Coffer、现在要安装带保险库布局的构建的人。全新安装完全不需要这些。

## 你会注意到什么 {#what-you-will-notice}

装好新构建后，如果 home 里仍只有 `coffer.db`，守护进程会拒绝启动：

```text
/Users/you/.coffer/coffer.db was written by a Coffer from before the vault layout. Stop the
daemon and run `coffer migrate` once to move it into ~/.coffer/vault
(`coffer migrate --rehearse` tries it on a copy first).
```

错误码是 `VAULT_MIGRATION_REQUIRED`。此时什么都还没改。守护进程从不代你迁移 home，因为升级要移动的文件树和数据库正是运行中的守护进程所打开的。

升级之后有一件事看起来像故障，其实不是：**每个密钥都要等你批准一次**。升级会把你的密钥带过来，但不带任何批准，而密钥只有在你批准之后才会发往某个目的地。所以模型提供方、MCP 服务器、消息渠道或同步远端第一次需要它的密钥时，会在 Coffer 应用里（[密钥页](/zh/guides/secrets#approvals)）等你批准，批准前保持空闲——例如消息渠道会显示“等待批准”而不是连接，配对和设置都保留。每一处批准一次即可，之后它会在下一次尝试时自行启动，无需重启。

## 开始之前 {#before-you-start}

- **停止守护进程。** 如果你用桌面应用，先退出它，再运行 `coffer daemon stop`。守护进程运行时 `coffer migrate` 会拒绝执行。
- **准备好 `git`。** 保险库是一个 git 仓库，所以 `PATH` 上必须有 git 2.40 或更高版本。如果没有，Coffer 的 `GIT_MISSING` 错误会提供一段提示词，把安装 git 交给你的智能体。
- **如果要演练（见下文），确保磁盘能放下一份 `~/.coffer` 的副本。** 升级本身是移动文件树而非复制，只额外增加一份数据库副本。

## 先演练 {#rehearse-it}

```sh
coffer migrate --rehearse
```

演练会把 `~/.coffer` 复制到一个临时 home，在那里执行升级，检查之前统计过的每一项在升级后仍然存在，再把副本回滚，逐字节与原始内容比对，最后删除副本。你的 home 只会被读取。结束时输出 `rehearsal passed`，或者列出出错的地方并提示 `do not migrate this home yet`。`--home PATH` 可以演练另一个 home。

## 执行升级 {#run-it}

```sh
coffer migrate
```

升级按顺序：

1. 把 `coffer.db`（连同 `-wal` 和 `-shm` 文件）备份为 `coffer.db.pre-vault`，把 `daemon-config.json` 备份到 `~/.coffer/pre-vault/`。备份此后再也不会以写方式打开。
2. 读取旧表，创建 `vault/`、`local/`、`content/` 和 `derived/`。
3. **移动**（重命名，从不复制）各个文件树：

   | 之前 | 之后 |
   | --- | --- |
   | `~/.coffer/knowledge/` | `~/.coffer/vault/knowledge/` |
   | `~/.coffer/skills/` | `~/.coffer/vault/skills/` |
   | `~/.coffer/skills/coffer-guide/` | `~/.coffer/derived/skills/coffer-guide/` |
   | `~/.coffer/memory/` | `~/.coffer/derived/memory/` |
   | `~/.coffer/chat-media/`、`channel-media/`、`workspace/` | `~/.coffer/content/…` |
   | `~/.coffer/cache/agent/` | `~/.coffer/derived/cache/agent/` |

4. 把知识历史（`knowledge/.git`）并入保险库仓库的 `knowledge/` 下，保留每个提交的消息、作者和日期。旧的 `.git` 保存为 `pre-vault/knowledge.git`。
5. 移除知识文档里旧的整理戳记（原件保存在 `pre-vault/knowledge-stamped/`），并在 `local/curation.json` 中记下哪些文档已定稿。
6. 把数据库中的一切写成文件：每个资源写成 `vault/resources/<kind>/<name>.json`（智能体写到 `local/resources/agent/`），MCP 能力开关、消息渠道配对和引擎设置写到 `vault/state/` 下，每个密钥的密文写成 `vault/secret/<ref>.enc`，生效范围、保留策略、密钥边界和同步远端以 JSON 写到 `local/` 下。所有这些在保险库里只产生**一个**提交，写入者为 `daemon`。
7. 把 `coffer.db` 重命名为 `runs.db` 并升级它：从此它只存历史（审计、调用、对话、同步轮次、用量），以 uid 为键。

每一次移动发生时都记录在 `local/migration.json` 中，所以即使中途失败，回滚也能把它撤回。报告会打印每个类别的数量、未能迁移的内容，以及需要你处理的事项：

- **指向已移动文件树的链接。** `~/.claude` 和 `~/.codex` 中指向旧位置的链接。Coffer 投递的技能链接会在守护进程下次启动并调和时修复；你自己创建的链接需要你自己改指向。
- **已移动文件树内嵌套的 git 仓库。**
- **如果你有同步远端，第一台升级的机器会替换它**（见下文）。
- **等待批准的密钥。** home 里有密钥时，报告会给出数量，并说明每个密钥在每个目的地的首次使用都要在 Coffer 应用里等你批准一次。

然后照常启动 Coffer。**设置 → 数据** 会显示保险库现在所在的位置（**保险库**和**本地内容**各自列出它们的位置）。

## 回滚 {#roll-it-back}

在守护进程停止的情况下：

```sh
coffer migrate --rollback
```

回滚会把 home 逐字节恢复原状：带戳记的知识原件和知识 `.git` 放回来，每一次记录在案的移动都被撤回，`vault/` 和 `local/` 被挪到一边，命名为 `vault.rolled-back-<timestamp>` 和 `local.rolled-back-<timestamp>`（所以你升级后做的任何改动都保留在那个仓库的历史里），`runs.db` 被挪到一边，`coffer.db.pre-vault` 被复制回 `coffer.db`，`daemon-config.json` 也被恢复。然后安装之前的 Coffer 构建。

回滚会留下一个暂停标记 `~/.coffer/MIGRATION_ROLLED_BACK`，防止新构建背着你再次升级这个 home：它的守护进程会拒绝启动并提示 `--resume`。当你想再次升级时：

```sh
coffer migrate --resume
coffer migrate
```

如果升级中途停下，`coffer migrate` 会拒绝再次运行并提示 `--rollback`：先回滚，再重新运行。

## 替换同步远端 {#replace-your-sync-remote}

早期 Coffer 写入的远端是旧布局。它从不会被原地转换；升级后的保险库是事实来源，由它替换远端。不会有任何拒绝：第一台升级机器的下一轮同步或加入操作，就会替换旧远端。

1. **升级第一台机器。** 在 **同步** 页点 **加入并拉取**：预览会按区域列出将推送什么、哪些只有旧远端有的文件会被移除（列出前 100 个，并给出确切总数）、谁在何时推送了旧的顶端，以及仍在旧布局上的机器必须升级。确认后即替换远端。推送是一次快进，所以旧历史仍保留在远端的 git 日志里。

   你原来的远端设置已迁到 `local/sync/remote.json`，无需重新输入。保险库里的明文密钥仍会阻止推送，远端保持旧的顶端。

2. **逐台升级其他机器**，然后加入被替换的远端。它会作为新机器加入：取并集、不删除任何东西，内容不同的文件留给你选择（**同步** 页 **状态** 标签上的 **选择版本**）。仍在旧版 Coffer 上的机器只读取布局数字，在升级之前会拒绝被替换的远端。

只有旧远端带有密钥时，密钥密文才会提交到远端；否则想要时请打开 **包含加密的密钥**。

## 相关内容 {#related}

- [持久化](/zh/architecture/persistence) · [文件与目录](/zh/reference/filesystem)
- [保险库同步](/zh/guides/vault-sync) · [手动编辑保险库](/zh/guides/vault-files)
- 决策记录：[Storage Is Five Classes by Nature](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/storage-is-five-classes-by-nature.md)、[Every Vault File Carries Its Own Format Version](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/every-vault-file-carries-its-format-version.md)
