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
  manifest.json              # workspace schema 版本（在所有机器上字节一致）
  machines/<machine-id>.json # 每机注册项（每台机器只写自己的那个文件）
  knowledge/                 # mirror of ~/.coffer/knowledge
  memory/                    # mirror of ~/.coffer/memory
  skills/                    # mirror of ~/.coffer/skills（skill 主库）
  resources/<kind>/<name>.yaml   # one deterministic file per config resource
  tombstones/resources/<kind>/<name>.json  # 显式删除记录（90 天 TTL）
  credentials/<ref>.enc          # Fernet ciphertext blob (never the master key)
  ```

- **Export** —— 将本地 vault 状态写入 workspace（镜像文件、序列化资源、导出密文）。
- **Import** —— 将 workspace 状态应用回本地 vault（文件回镜像 + 重建索引、资源调和进 SQLite、导入密文）。
- **Sync run** —— export → `git pull`（merge）→ 合并干净时：`git push` + import。整个过程是一次 `coffer sync` 调用。
- **Conflict** —— 一次 `git merge` 冲突。该次运行停在 `conflicted` 状态；在用户解决冲突前不会导入任何内容。两边都不会被丢弃。
- **Tombstone（墓碑）** —— 配置资源删除的显式记录
  （`tombstones/resources/<kind>/<name>.json`，携带删除时间与执行机器）。导入
  **仅**在墓碑存在时删除本地资源——资源只是从 workspace 中缺席永远不会导致删除。
  重新注册资源后，该机器的下一次导出会清除其墓碑。墓碑 90 天后过期。
- **Quarantine（隔离）** —— 在本机导入失败的资源（例如其配置含有机器本地路径）。
  其 workspace 文档被原样保留——既不会用失败的本地状态重新导出、也不会被丢弃——
  每次运行重试导入，受影响的 ref 在同步状态中报告。一行在某台机器上无法导入的
  资源 MUST NOT 导致它在任何机器上被删除。隔离期间以远端意图为准：对同一资源的
  本地编辑不会被导出，墓碑也不会移除被保留的文档，直到隔离解除。
- **Auto-sync** —— 一个可选开启的守护进程 worker，在文件/资源变更时（去抖）以及按固定间隔执行 sync run。默认关闭。

## Machine identity（机器身份）

每个安装实例在守护进程首次启动时铸造一个稳定的**机器 id**（ULID），持久化在本机
（一个 DB 单例——它是*关于*这台机器的状态，永不作为 vault 数据同步）。人类友好的
**显示名**默认取主机名，可编辑。

workspace 的 `machines/` 区为每台机器保存一个 JSON 注册项：显示名、平台、操作系统
版本、Coffer 版本、上次同步时间。**每台机器只写自己的注册项**，因此该区在构造上就
不会冲突。写入抖动控制：仅当本次运行的提交本就非空、或注册项已超过 24 小时（心跳）
时才重写自己的注册项——空闲机器 MUST NOT 产生无休止的纯注册项提交链。

机器身份的存在是为了让用户看到 vault 关联的每台机器（本节），并为后续修订提供锚点
（按资源的运行时亲和、每机配置覆盖、墓碑溯源——见
[ADR-043](../../docs/decisions/ADR-043-sync-machine-identity-near-real-time.md)）。
它**不是**记录级版本方案。

## Configuration

一行持久化的 sync 配置：

- `remote` —— git remote URL（启用同步所必需）。
- `enabled` —— 同步的总开关。
- `auto` —— 守护进程 auto-sync worker 是否运行。
- `interval_seconds` —— auto 拉/推间隔（默认 300）。
- `branch` —— 用于同步的 git 分支（默认 `main`）。它是 Coffer 自身同步仓库里的
  内部 ref 名，并非用户的项目分支；两台机器用同一默认值，因此**不在设置 UI 中暴露**。
  它仍保留在 config/API 中，并可通过 CLI（`coffer sync --branch`）调整，以应对极少数
  在同一 remote 上按分支区分的场景。

git remote 的凭据（SSH key / token）属于用户自己的 git 配置；Coffer 调用 git 并依赖环境中既有的 git credential 设置，与开发者平常 `git push` 的方式完全一致。

## Surfaces

- **CLI** —— `coffer sync` 命令组：`init`、`status`、`run`（默认）、`push`、`pull`、`resolve`、`config`、`machines`（列出；`--rename` 重命名本机）、`key export`、`key import`。
- **REST** —— `/api/v1/sync/*`：获取/设置配置、获取状态、触发一次运行、解决冲突、列出机器 / 重命名本机、导出/导入主密钥。
- **Desktop UI** —— 一个 Sync 设置面板：配置 remote、切换 auto-sync、查看状态（clean / syncing / conflicted / error、上次同步时间）、触发一次运行、解决冲突，以及一张机器卡片，列出 vault 已知的每台机器（显示名、平台、上次同步、「本机」徽标、重命名）。

## Credential bootstrap

主密钥从不在同步媒介中传输。在一台新机器上，用户以带外（out-of-band）方式将其携带过来，仅此一次：

- `coffer sync key export <path>` 把当前机器的主密钥写入一个文件，用户通过自己信任的渠道转移它。
- `coffer sync key import <path>` 在新机器上安装它（依据该机器的设置，存入文件存储或 keychain）。

在桌面 UI 中，主密钥卡片 MUST 让用户通过原生对话框选择文件，而非手输路径——导出用
原生「存文件」对话框，导入用原生「选文件」对话框（打包应用用 OS 对话框；Web 经 daemon
选择器，见 spec 004 FR-042 / ADR-036）。仅当宿主没有原生对话框工具时，才出现手输路径框
作为回退。

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

### Scenario: 删除以墓碑传播

- **Given** 机器 A 和 B 共享一个已同步的 `mcp_server` 资源
- **When** A 删除该资源，且两台机器各完成一次同步往返
- **Then** 该资源在 B 上消失，workspace 中留下它的墓碑而非资源文档
- **And** 若 B 之后重新注册同名资源，它在两台机器上重新出现，墓碑被清除

### Scenario: 导入失败绝不导致资源在别处被删除

- **Given** 机器 A 同步了一个在机器 B 上无法导入的资源（配置含机器本地路径）
- **When** B 执行一次同步（该资源导入失败），随后两台机器再完成一次往返
- **Then** 该资源在 A 上和 workspace 中仍然存在，B 在同步状态中将该 ref 报告为
  已隔离，并在每次运行时重试导入

### Scenario: 旧构建拒绝更新的 workspace

- **Given** 同步 workspace 的 manifest 携带比当前构建更新的 schema 版本
- **When** 一次同步运行到达导入步骤
- **Then** 该次运行以 `SYNC_WORKSPACE_TOO_NEW` 失败，不导入任何内容

### Scenario: 机器在同步后可见

- **Given** 机器 A 和 B 都已对着同一个 remote 完成过一次 sync run
- **When** 用户在 A 上列出机器（设置面板或 `coffer sync machines`）
- **Then** 两台机器都出现，带显示名、平台和上次同步时间，且 A 被标记为本机
- **And** 重命名 A 后，经过下一个往返，B 的机器列表随之更新

## Out of scope references

本 spec 覆盖同步引擎及其各 surface。知识/记忆的文件格式由 specs 006/007 拥有；凭据存储与主密钥由 spec 006 / credentials 模块拥有；资源模型由 resource framework 拥有。本 spec 复用它们，而不重新定义它们。
