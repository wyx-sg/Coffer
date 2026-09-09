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
  state/<area>/...yaml       # 模块自有的共享状态（如 channel-peers）
  credentials/<ref>.enc          # Fernet ciphertext blob (never the master key)
  ```

- **Export** —— 将本地 vault 状态写入 workspace（镜像文件、序列化资源、导出密文）。
- **Import** —— 将 workspace 状态应用回本地 vault（文件回镜像 + 重建索引、资源调和进 SQLite、导入密文）。
- **Import reconciliation（导入调和）**（2026-07-10 修订）—— 只调和注册表**行**是不够的：一些资源配置驱动机器本地的副作用，由各 kind 自己的服务在正门执行（连接激活投影进 agent 原生配置文件；agent 的 `disable_native_memory` 改写其 settings；`follow_all_skills` 驱动技能投递）。每次导入之后，声明了**导入后调和钩子**的 kind 会从已收敛的行出发幂等地重放这些副作用，使机器 A 上的变更在机器 B 上真正生效——注册表与磁盘永不分歧。钩子失败记录进该轮的错误并在后续每次导入重试（钩子调和的是当前状态，不是增量）。kind 还 MAY 声明一个**导入门**：导入机在 upsert 文档前运行的校验（agent 的 `config_dir` 在本机不存在/不可写——该 agent 没装在这台机器上）——门失败与其他导入失败一样进入隔离区，每轮重试，agent 装好后自行恢复。门对注册与更新一并生效：被门拒绝的更新使较新的文档进入隔离区，既有的本地行继续以其最后一份可用配置运作；钩子会跳过机器本地前提不再成立的行（消失的配置目录只报告、绝不重建）。
- **Sync run** —— export → `git pull`（merge）→ 合并干净时：`git push` + import。整个过程是一次 `coffer sync` 调用。
- **Conflict** —— 一次 `git merge` 冲突。引擎以确定性策略**自动解决**（2026-07-10 修订）：逐冲突路径，最后触及该路径的 vault 仓库提交较新的一侧获胜。提交时间是变更**被某次同步运行捕获**的时间，不是用户实际编辑的时间——因此语义准确说是「最近同步的编辑获胜」；两台机器都开着近实时自动同步时两者一致，但一台长期离线后回归的机器会把它较旧的编辑作为新提交同步而胜出。策略与机器无关（每台机器选出同一个赢家）；时间戳相同时保留执行合并那台机器的一侧；`manifest.json` 永远取本机一侧（同版本机器间它字节相同，且 schema 门先于导出运行）。只有引擎无法处理的路径才会让运行停在 `conflicted`——此时 UI 指引用户到自己的仓库（如 GitHub）解决，应用内不提供合并界面；`coffer sync resolve` 保留为 CLI 兜底。落败一侧的内容不会丢失——它留在 vault 仓库的历史里。
- **Tombstone（墓碑）** —— 配置资源删除的显式记录
  （`tombstones/resources/<kind>/<name>.json`，携带删除时间与执行机器）。导入
  **仅**在墓碑存在时删除本地资源——资源只是从 workspace 中缺席永远不会导致删除。
  重新注册资源后，该机器的下一次导出会清除其墓碑。墓碑 90 天后过期。
- **Quarantine（隔离）** —— 在本机导入失败的资源（例如其配置含有机器本地路径）。
  其 workspace 文档被原样保留——既不会用失败的本地状态重新导出、也不会被丢弃——
  每次运行重试导入，受影响的 ref 在同步状态中报告。一行在某台机器上无法导入的
  资源 MUST NOT 导致它在任何机器上被删除。隔离期间以远端意图为准：对同一资源的
  本地编辑不会被导出，墓碑也不会移除被保留的文档，直到隔离解除。
- **Auto-sync** —— 可选开启的守护进程 worker，提供近实时收敛。推送侧：资源变更与
  文件树变化（`watchfiles` 监听 knowledge/memory/skills 三棵树——agent 可能经
  symlink 绕过 daemon 直写 memory）触发去抖运行（静默期 5 秒，首次变更后封顶 30
  秒）。拉取侧：每 `poll_remote_seconds` 秒一次轻量 `git ls-remote` HEAD 探测，仅在
  远端真的移动时才执行完整运行。固定间隔轮询保留为兜底（它也兜住运行进行中发生的
  变更——运行期间触发被抑制，导入自身的写入不会再次触发）。默认关闭。两台机器都
  开启时的预期收敛：约 15–30 秒。

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

**Scope（作用域）**（2026-07-10 修订 —— machine × agent scope，
[ADR-045](../../docs/decisions/ADR-045-machine-agent-resource-scope.md)）把机器
身份泛化成一个框架级的、按资源的激活矩阵：每个资源（不在 kind 配置内部）都拥有
一个可选的 `scope` 字段，以机器 ULID（或代表所有机器的 `"*"`）为 key，value 为
`"*"`（所有 agent）或一份 agent 名列表。

```
scope == None                                    # 所有机器、所有 agent 都激活（默认）
scope == {}                                      # 任何机器都不激活（休眠）
scope == {"<ulid>": ["claude-code"], "*": "*"}   # 某台机器：仅 Claude Code；其余每台机器：所有 agent
```

| 规则 | 行为 |
| --- | --- |
| 机器 M 的条目查找 | 精确的 ULID key 优先于 `"*"` key；没有 M 对应的 key → 在 M 上不激活 |
| `machine_in_scope(scope, m)` | 存在 `m` 的条目，且其 value 为 `"*"` 或非空列表 |
| `agent_in_scope(scope, m, agent)` | 该条目的 value 为 `"*"`，或 `agent` 在列表中；`agent=None`（未识别的会话）**仅**匹配 `"*"` 的 value |
| `scope == None` | 永远激活——所有机器、所有 agent |
| 条目中未知的机器 ULID 或 agent 名 | 合法，只是永不匹配（可能是另一台机器尚未同步，或该 agent 稍后才注册） |

每个 kind 自行声明使用哪些轴，并在**自己既有的**把关点执行 scope——不引入新的
中央关卡：

| Kind | 轴 | 把关点 |
| --- | --- | --- |
| `mcp_server` | machine × agent | 网关（spec 001） |
| `skill` | machine × agent | 投递 ∩ follow policy（spec 005） |
| `agent` | 仅 machine | 投影 / 调和 / shim 安装（spec 004） |
| `channel` | 仅 machine | 渠道 runtime（spec 009）；取代 `runs_on` |
| `knowledge_base`、`memory` | 无 | 非空 `scope` 在校验阶段被拒绝 |

仅 machine 轴的 kind，其 scope 条目的 value 只接受 `"*"`（agent 名列表会被拒
绝）。在计算下文 Machines fleet view 的激活切片时，任何指名了 agent 的矩阵还会
与该 **agent 自己的** machine 轴取交集——网关本身信任本机 shim 自行上报的身
份，不会反过来校验该 agent 的 machine 轴，因为本机 shim 只能运行在该 agent 实
际已安装的机器上。

**同步但不激活。** `scope` 随资源文档搭乘既有的 export → merge → import 流水
线、自动冲突解决、墓碑与隔离机制，完全不做改动：一个被 scope 限定的资源仍然同
步到每台机器并在每台机器上可见；在 scope 之外时，它只是不被激活（不拉起、不暴
露、不投递），注册表仍是唯一真相源——scope 可以在任意机器上编辑，与编辑任何其
他资源字段完全一样。给资源文档加入 `scope` 会把 workspace manifest 的
`SCHEMA_VERSION` 从 3 提升到 4，因此尚未升级的构建会被既有的
`SYNC_WORKSPACE_TOO_NEW` 门拦下（见下文「旧构建拒绝更新的 workspace」），而不
是悄悄丢弃或误读这个字段。

## 路径可移植

用户的机器有不同的用户名/home 布局，配置里的绝对路径原样同步会失效。两个机制按序
在导入时应用（共享文档 → `${HOME}` 展开 → 每机覆盖）：

- **`${HOME}` 正规化**（零配置）：导出时把配置中位于本机 home 下的字符串值改写为
  `${HOME}/...`；导入时展开为本机 home。介质中永不出现字面 home 路径。已含字面
  token 的值按原样导出——且与所有 token 一样，导入时在每台机器上展开为本机
  home（token 实际上在任何地方都是活跃的）。
- **每机覆盖**：每资源一个 RFC 7386 JSON Merge Patch，位于
  `machines/<machine-id>/overrides/<kind>/<name>.yaml`（每台机器只写自己的目录——
  无冲突），用于真正逐机不同的值（如 Intel 与 ARM 的 homebrew 路径）。补丁在每次
  导入时应用、在每次导出时**剥离**（被覆盖的键回退为最近的共享值），机器的特化
  永不泄漏进介质；撤销覆盖会立即在本地恢复共享值。表面：
  `coffer sync override list|set|unset` 与 `/api/v1/sync/overrides`。

## Configuration

一行持久化的 sync 配置：

- `remote` —— git remote URL（启用同步所必需）。
- `enabled` —— 同步的总开关。
- `auto` —— 守护进程 auto-sync worker 是否运行。
- `interval_seconds` —— auto-sync 的兜底轮询间隔（默认 300）。
- `poll_remote_seconds` —— auto-sync 用 `git ls-remote` 探测远端 HEAD 的频率
  （默认 15，最小 5）。一次廉价的网络往返；只有 HEAD 移动时才执行完整运行。
- `branch` —— 用于同步的 git 分支（默认 `main`）。它是 Coffer 自身同步仓库里的
  内部 ref 名，并非用户的项目分支；两台机器用同一默认值，因此**不在设置 UI 中暴露**。
  它仍保留在 config/API 中，并可通过 CLI（`coffer sync --branch`）调整，以应对极少数
  在同一 remote 上按分支区分的场景。

git remote 的凭据（SSH key / token）属于用户自己的 git 配置；Coffer 调用 git 并依赖环境中既有的 git credential 设置，与开发者平常 `git push` 的方式完全一致。Coffer 不存储任何 git 凭据、不提供凭据管理 UI；取而代之（2026-07-10 修订）：保存**新的** remote（或启用同步）时用一次无终端的 `git ls-remote` 探测，失败则拒绝保存并返回 `SYNC_REMOTE_UNREACHABLE` 及提示码（`auth` / `not_found` / `network`）；status 端点用同一分类器给 `last_error` 打 `error_hint`，界面据此渲染配置指引（改用 SSH 地址 / 运行 `gh auth setup-git`），而不是原始 git stderr。daemon 无终端运行：HTTPS remote 只有在 credential helper 能无终端应答时才可用。

## Surfaces

- **CLI** —— `coffer sync` 命令组：`init`、`status`、`run`（默认）、`push`、`pull`、`resolve`、`config`、`override list|set|unset`、`key export`、`key import`。`machines`（列出；`--rename` 重命名本机）被提升为顶层的
  `coffer machines` 命令（2026-07-10 修订 —— machine × agent scope，
  [ADR-045](../../docs/decisions/ADR-045-machine-agent-resource-scope.md)）；
  `coffer sync machines` 作为向后兼容的别名保留。新增的顶层
  `coffer scope show|set|clear <kind>:<name>` 用于读取/编辑任意资源的 scope
  （见下文「Machines fleet view」）。
- **REST** —— `/api/v1/sync/*`：获取/设置配置、获取状态、触发一次运行、解决冲突、列出机器 / 重命名本机、管理每机覆盖、导出/导入主密钥。`scope` 在任意资源的创建或更新处
  （框架级 resource CRUD 载荷）按 kind 的轴声明被校验；`GET /api/v1/machines`
  与 `GET /api/v1/machines/{id}/slice`（2026-07-10 修订 —— machine × agent
  scope，ADR-045）分别提供机群列表与某台机器的激活切片——见下文
  「Machines fleet view」。
- **Desktop UI** —— 一个 Sync 设置面板：配置 remote（保存即校验）、切换 auto-sync、查看状态（clean / syncing / conflicted / error、上次同步时间、可行动的错误指引）、触发一次运行，以及一张机器卡片，列出 vault 已知的每台机器（显示名、平台、上次同步、「本机」徽标、重命名）。应用内**没有**冲突解决界面（2026-07-10 修订）：冲突自动解决；罕见的滞留冲突指引用户到自己的仓库处理。Master key 卡片显示 key 的 SHA-256 指纹（绝不显示 key 本身），便于导出/导入后确认两台机器持有同一把 key。完整的机群视图——同步状态条、每台机器一张卡片，以及每台机器的激活切片——移到了新的顶层 Machines
  导航项（2026-07-10 修订 —— machine × agent scope，ADR-045）；这个面板里的机
  器卡片保留为一份更轻量的摘要，并链接到那里（见下文「Machines fleet view」）。

## Machines fleet view（2026-07-10 修订 —— machine × agent scope，[ADR-045](../../docs/decisions/ADR-045-machine-agent-resource-scope.md)）

一个顶层的 `Machines` 导航项（`/machines`）——与 Settings → Sync 分开——列出 vault
中注册的每台机器：一条同步状态条（状态、上次同步时间、手动触发一次运行的按钮、
回到 Settings → Sync 的链接）之上是每台机器一张卡片（显示名、平台、上次同步、
「本机」徽标）。选中某台机器会打开它的**激活切片**——在场的 agent、激活的 MCP
服务器、每个 agent 收到的 skill 投递、绑定的 channel——完全**在本地**根据已同步
的 registry 加上每个资源的 scope 计算得出，因此任意一台机器都能渲染**任意另一
台**机器的切片而无需联系它。每台机器的切片都只是意图——registry 加 scope 运算，
没有本地文件系统/进程检查（即它的 scope 说那台机器上应当激活什么）；远端机器的
切片会额外带一条「仅意图」提示。同步配置本身（remote、auto-sync、master key）
**不**属于这个视图——它仍留在 Settings → Sync；这个视图关心的是激活，不是传输。

- **REST**：`GET /api/v1/machines`（机群列表）与
  `GET /api/v1/machines/{id}/slice`（该机器的激活切片）。
- **CLI**：顶层的 `coffer machines`（从 `coffer sync` 命令组中提升出来；
  `coffer sync machines` 作为向后兼容别名保留），以及用于读取/编辑任意资源
  scope 的 `coffer scope show|set|clear <kind>:<name>`。

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

### Scenario: 冲突的编辑自动解决为最近同步的一侧

- **Given** 机器 A 和 B 自上次共同同步以来都编辑了同一个资源/文件，且 A 已经推送
- **When** 机器 B 运行 `coffer sync`
- **Then** 该次运行把每个冲突路径自动解决为 vault 提交较新的一侧——即最近同步的编辑（相同则保留 B 侧），无需用户操作即完成，且两台机器在各自的下一次运行后收敛到同一个赢家
- **And** 引擎无法处理的路径让运行停在 `conflicted`，界面指引用户到自己的仓库解决（`coffer sync resolve` 保留为 CLI 兜底）

### Scenario: 对已有内容远端的首次同步只合并、绝不删除

- **Given** 一台 vault 为空（或部分填充）的机器，而远端已携带另一台机器的资源、文件树与凭据
- **When** 这台机器的首次同步运行（其导出必然发生在它完成过任何导入之前）
- **Then** 导出 MUST NOT 删除任何它尚未摄入的工作区内容：没有本地行的资源文档除非有墓碑否则不被删除；文件树与凭据的删除在本机完成过一次导入之前不向外传播

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

### Scenario: 导入的配置在本机重放其副作用

- **Given** 一个带导入后调和钩子的 kind（如连接激活、agent 的原生记忆开关），其资源在机器 A 上发生变更
- **When** 机器 B 的同步运行导入该变更
- **Then** B 的钩子从收敛后的行重放机器本地副作用（投影/原生配置写入也发生在 B 上）；钩子失败记录进该轮错误并在下次导入重试

### Scenario: 本机未安装的 agent 在导入时进入隔离区

- **Given** 机器 A 注册了一个 agent，其 `config_dir` 在机器 B 上不存在
- **When** B 的同步运行导入该 agent 资源
- **Then** 导入门在 B 上拒绝它——文档进入隔离区（同步状态中可见），不会创建指向死目录的 agent 行；目录存在后，后续运行的导入自行成功

### Scenario: 旧构建拒绝更新的 workspace

- **Given** 同步 workspace 的 manifest 携带比当前构建更新的 schema 版本
- **When** 一次同步运行到达导入步骤
- **Then** 该次运行以 `SYNC_WORKSPACE_TOO_NEW` 失败，不导入任何内容

### Scenario: 渠道配对状态随 vault 同步

- **Given** 机器 A 有一个已配对 owner 的渠道
- **When** 机器 B 对着同一个 remote 同步
- **Then** B 同时持有该渠道及其配对身份（chat id、sender id、首选 agent）——把渠道
  改绑到 B 无需重新配对
- **And** 每台机器本地的会话指针永不传播

### Scenario: 配置路径跟随各机器的 home

- **Given** 机器 A（home `/Users/alice`）同步了一个配置指向其 home 内路径的资源
- **When** 机器 B（home `/home/bob`）导入它
- **Then** 路径落到 B 的 home 之下，且同步介质中保存的是 `${HOME}/...`，
  绝无字面 home 路径

### Scenario: 每机覆盖在同步往返中保持

- **Given** 一个已同步的资源和机器 B 上的一个每机覆盖
- **When** 两台机器完成同步往返，包括对未被覆盖字段的一次共享编辑
- **Then** B 保持其覆盖值，A 与介质从未见到它们，共享编辑仍到达 B
- **And** 撤销覆盖后，B 的下一次运行恢复共享值

### Scenario: 共享偏好与引擎配置同步

- **Given** 机器 A 禁用了一个 MCP 工具并选择了内置引擎模型
- **When** 机器 B 对着同一个 remote 同步
- **Then** B 上该工具为禁用、模型一致——B 重新启用该工具也会传播回 A
- **And** 全新机器的默认值绝不覆盖舰队配置（本机持久化过该单例后才发布）

### Scenario: 机器在同步后可见

- **Given** 机器 A 和 B 都已对着同一个 remote 完成过一次 sync run
- **When** 用户在 A 上列出机器（设置面板或 `coffer sync machines`）
- **Then** 两台机器都出现，带显示名、平台和上次同步时间，且 A 被标记为本机
- **And** 重命名 A 后，经过下一个往返，B 的机器列表随之更新

### Scenario: 被 scope 限定的资源在其 scope 之外保持休眠

- **Given** 一个 `mcp_server` 资源的 `scope` 仅指名机器 A（`{"<A-id>": "*"}`），
  且已同步到机器 A 与机器 B
- **When** 机器 B 在导入之后执行调和
- **Then** 该资源的文档在 B 上存在（可见、已同步），但 B 的网关从不拉起它的
  upstream，也不会列出它的工具，而机器 A 正常激活它
- **And** Machines fleet view 会把该资源在 B 上显示为未激活

### Scenario: scope 编辑像任何资源编辑一样传播

- **Given** 一个当前仅 scope 到机器 A 的资源
- **When** 用户在机器 A 上把它的 `scope` 编辑为包含机器 B，且两台机器完成一次
  同步往返
- **Then** B 在其下一次调和时激活该资源——经由与任何其他资源编辑相同的
  export → merge → import → 调和钩子 流水线，不引入任何新的同步机制
- **And** 一个 manifest schema 版本早于 `scope` 字段的过时构建会以
  `SYNC_WORKSPACE_TOO_NEW` 拒绝这次导入，而不是悄悄丢弃这个字段

### Scenario: fleet view 能渲染任意机器的激活切片

- **Given** 机器 A 和 B 都已对着同一个 remote 完成过一次 sync run，且它们的资源
  带有不同的 scope 组合
- **When** 用户在机器 A 上打开 Machines fleet view 并选中机器 B 的卡片
- **Then** 详情视图渲染出 B 的激活切片（在场的 agent、激活的 MCP 服务器、每个
  agent 收到的 skill 投递、绑定的 channel），完全在本地根据已同步的 registry
  加上 scope 计算得出，机器 A 无需联系 B
- **And** 因为从 A 的视角看 B 是远端机器，这次渲染带有一条「仅意图」提示；在 B
  自己上面查看（它自己本机的切片）则不出现这条提示

## Out of scope references

本 spec 覆盖同步引擎及其各 surface。知识/记忆的文件格式由 specs 006/007 拥有；凭据存储与主密钥由 spec 006 / credentials 模块拥有；资源模型由 resource framework 拥有。本 spec 复用它们，而不重新定义它们。
