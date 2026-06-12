# Spec 010 — 多机同步

> English: [spec.md](./spec.md)

借助用户自己拥有的 git 仓库作为同步媒介，让一个 Coffer vault 在用户的多台机器之间保持一致。该能力由 constitution 0.3.0 对 Principle I 的修订（用户掌控的同步媒介例外）启用。背景与备选方案见
[ADR-016](../../docs/decisions/ADR-016-multi-machine-sync.md)。

## Why

一位开发者在不止一台电脑（笔记本、台式机）上使用 Coffer。如今每台机器都是一座孤岛：知识、记忆、已注册的资源和凭据各自分叉。本特性让用户把本地 vault 状态推送到自己掌控的 git remote，并在另一台机器上拉取，从而让每台机器都收敛到同一个 vault——既不依赖任何由厂商掌控的云，主密钥也永不离开机器。

## What syncs

- **知识库 + 记忆** —— `~/.coffer/knowledge/` 和 `~/.coffer/memory/` 下的 markdown 文件（这些文件本身已是事实来源）。
- **配置资源** —— `mcp_server`、`agent`、`skill`、`channel` 定义（记录系统是 SQLite；为传输而序列化为文本）。
- **凭据** —— **仅** Fernet **密文**。

## What does not sync (machine-local)

日志、`coffer.db`（可重建的索引）、`daemon.json`、PID 文件、端口分配，以及任何运行时产物。主密钥**永不**写入同步媒介。

## Concepts

- **Sync remote** —— 用户自己拥有的 git URL（例如一个私有的 GitHub 仓库或自托管的 git 服务器）。Coffer 不提供任何托管端点。
- **Sync workspace** —— 由 Coffer 维护的一个 git 工作树（默认
  `~/.coffer/sync/`），与实时运行时目录保持分离。其布局：

  ```
  manifest.json              # schema version + machine id + last-sync metadata
  knowledge/                 # mirror of ~/.coffer/knowledge
  memory/                    # mirror of ~/.coffer/memory
  resources/<kind>/<name>.yaml   # one deterministic file per config resource
  credentials/<ref>.enc          # Fernet ciphertext blob (never the master key)
  ```

- **Export** —— 将本地 vault 状态写入 workspace（镜像文件、序列化资源、导出密文）。
- **Import** —— 将 workspace 状态应用回本地 vault（文件回镜像 + 重建索引、资源调和进 SQLite、导入密文）。
- **Sync run** —— export → `git pull`（merge）→ 合并干净时：`git push` + import。整个过程是一次 `coffer sync` 调用。
- **Conflict** —— 一次 `git merge` 冲突。该次运行停在 `conflicted` 状态；在用户解决冲突前不会导入任何内容。两边都不会被丢弃。
- **Auto-sync** —— 一个可选开启的守护进程 worker，在文件/资源变更时（去抖）以及按固定间隔执行 sync run。默认关闭。

## Configuration

一行持久化的 sync 配置：

- `remote` —— git remote URL（启用同步所必需）。
- `enabled` —— 同步的总开关。
- `auto` —— 守护进程 auto-sync worker 是否运行。
- `interval_seconds` —— auto 拉/推间隔（默认 300）。
- `branch` —— 用于同步的 git 分支（默认 `main`）。

git remote 的凭据（SSH key / token）属于用户自己的 git 配置；Coffer 调用 git 并依赖环境中既有的 git credential 设置，与开发者平常 `git push` 的方式完全一致。

## Surfaces

- **CLI** —— `coffer sync` 命令组：`init`、`status`、`run`（默认）、`push`、`pull`、`resolve`、`config`、`key export`、`key import`。
- **REST** —— `/api/v1/sync/*`：获取/设置配置、获取状态、触发一次运行、解决冲突、导出/导入主密钥。
- **Desktop UI** —— 一个 Sync 设置面板：配置 remote、切换 auto-sync、查看状态（clean / syncing / conflicted / error、上次同步时间）、触发一次运行、解决冲突。

## Credential bootstrap

主密钥从不在同步媒介中传输。在一台新机器上，用户以带外（out-of-band）方式将其携带过来，仅此一次：

- `coffer sync key export <path>` 把当前机器的主密钥写入一个文件，用户通过自己信任的渠道转移它。
- `coffer sync key import <path>` 在新机器上安装它（依据该机器的设置，存入文件存储或 keychain）。

在一台机器上密钥到位之前，导入的密文保持**锁定**：引用它的资源无法启动，状态报告
`credentials_locked` 并附带受影响的 refs。

## Acceptance Scenarios

### Scenario: 对着用户的 remote 初始化同步

- **Given** 一台拥有 vault、且未配置任何同步的机器
- **When** 用户运行 `coffer sync init <git-remote>`
- **Then** Coffer 创建 sync workspace，在 sync 配置中记录该 remote，执行首次 sync run，并报告状态 `clean`

### Scenario: 将 vault 状态往返同步到第二台机器

- **Given** 机器 A 已同步了知识、记忆、一个已注册的 `mcp_server` 以及一份凭据
- **When** 机器 B 对着同一个 remote 运行 `coffer sync`（主密钥已完成 bootstrap）
- **Then** 机器 B 的 vault 包含相同的知识/记忆文件、相同的 `mcp_server` 资源，并且能够解密该凭据

### Scenario: 密钥 bootstrap 之前凭据被锁定

- **Given** 机器 B 已拉取密文，但尚未导入主密钥
- **When** 机器 B 运行 `coffer sync status`
- **Then** 状态报告 `credentials_locked` 并列出受影响的 refs
- **And** 在执行 `coffer sync key import <path>` 之后，下一次 status 不再列出它们

### Scenario: 主密钥从不进入媒介

- **Given** 任意一次 sync run 已完成
- **When** 检查 sync workspace 的内容
- **Then** 没有任何文件包含主密钥；`credentials/` 中只存放 Fernet 密文

### Scenario: 冲突的编辑会停下运行以待解决

- **Given** 机器 A 和 B 自上次共同同步以来都编辑了同一个资源/文件，且 A 已经推送
- **When** 机器 B 运行 `coffer sync`
- **Then** 该次运行停在 `conflicted` 状态，不导入任何内容，并列出发生冲突的路径
- **And** `coffer sync resolve`（取 ours/theirs/path）清除冲突，随后的一次运行得以完成

### Scenario: 只有共享状态会被同步

- **Given** 一个含有日志、`coffer.db` 和 `daemon.json` 的 vault
- **When** 一次 sync run 完成
- **Then** sync workspace 只包含知识、记忆、资源和凭据文件——没有日志、数据库文件或守护进程运行时文件

### Scenario: auto-sync 在变更后收敛

- **Given** 机器 A 和 B 都启用了 auto-sync
- **When** A 注册了一个新资源
- **Then** A 在去抖窗口内推送该变更，B 在其下一次间隔拉取时导入它，两台机器都无需任何手动命令

## Out of scope references

本 spec 覆盖同步引擎及其各 surface。知识/记忆的文件格式由 specs 006/007 拥有；凭据存储与主密钥由 spec 006 / credentials 模块拥有；资源模型由 resource framework 拥有。本 spec 复用它们，而不重新定义它们。
