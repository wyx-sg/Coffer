---
title: 升级现有的 Coffer
description: 用 coffer migrate 把 Coffer home 从单一的 coffer.db 数据库迁到保险库布局——先演练、再执行、必要时回滚，并重建你的同步远端。
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

## 开始之前 {#before-you-start}

- **停止守护进程。** 如果你用桌面应用，先退出它，再运行 `coffer daemon stop`。守护进程运行时 `coffer migrate` 会拒绝执行。
- **准备好 `git`。** 保险库是一个 git 仓库。在 macOS 上运行 `xcode-select --install`。
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
- **旧的同步工作树** `~/.coffer/sync`，原地保留，不再使用。确认没问题后可以删除。
- **如果你有同步远端，需要重建它**（见下文）。

然后照常启动 Coffer。`coffer path` 会打印新的各个根目录。

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

## 重建同步远端 {#rebuild-your-sync-remote}

早期 Coffer 写入的远端是旧布局，新构建会拒绝它：同步轮次以 `remote too old` 结束。它从不会被原地转换，因为其他机器可能仍在往里推旧布局。请改为重建，一次一台机器：

1. **升级第一台机器**，把它指向一个**空**分支或空仓库，然后加入。加入空远端会推送这台机器的整个保险库：

   ```sh
   coffer sync remote set https://github.com/you/coffer-vault.git --branch vault
   coffer sync join
   ```

   你原来的远端设置已迁到 `local/sync/remote.json`，所以只需修改 URL 或分支。`--secret-ref` 保持原样。

2. **逐台升级其他机器**，指向同一个分支或仓库，然后加入。它会作为新机器加入：取并集、不删除任何东西，内容不同的文件留给你选择（`coffer sync choose`）。

只有旧远端带有密钥时，密钥密文才会提交到新远端；否则想要时请传 `--with-secret`。旧的分支或仓库保持不动；所有机器都迁过来之后再删除它。

## 相关内容 {#related}

- [持久化](/zh/architecture/persistence) · [文件与目录](/zh/reference/filesystem)
- [保险库同步](/zh/guides/vault-sync) · [手动编辑保险库](/zh/guides/vault-files)
- 决策记录：[Storage Is Five Classes by Nature](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/storage-is-five-classes-by-nature.md)、[Every Vault File Carries Its Own Format Version](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/every-vault-file-carries-its-format-version.md)
