# Spec 010 — 仓库导出与导入

> English: [spec.md](./spec.md)

把一个 Coffer 仓库导出到一个目录，再把那个目录导入回来，从而把它搬到用户自己的
另一台机器上。没有传输介质、没有远程、没有后台复制。背景与备选方案见
[ADR-016](../../docs/decisions/ADR-016-vault-export-import.md)。

## 为什么

开发者配置一台新笔记本，或者希望台式机从笔记本已经知道的东西开始。今天每台机器
都是一座孤岛：知识、已注册资源与凭据都得手工重建一遍。

本特性把仓库写入用户选定的目录，并能把这样一个目录读回来。至于怎么把那个目录弄到
另一台机器上——`scp`、U 盘、他们自己的 git 仓库——是用户自己的事，不在本 spec
范围内。因为导出只是普通的本地文件输出，它不需要对章程的本地优先原则做任何例外。

## 会导出什么

- **知识** —— `~/.coffer/knowledge/<scope>/` 下的 markdown 文件（这些文件本身
  已经是事实来源）。2026-09-10 知识层合并之后只剩一个根；`~/.coffer/memory/`
  已不复存在。
- **技能** —— `~/.coffer/skills/` 下的 skill 主库。
- **配置资源** —— `mcp_server`、`agent`、`skill`、`channel` 定义（记录系统是
  SQLite；为搬运而序列化成文本）。
- **共享状态** —— 由各模块自有、属于仓库而非某一台机器的状态区（例如渠道对端配对、
  knowledge scope 标签）。
- **凭据** —— **仅** Fernet **密文**，且仅在明确要求时。

## 不会导出什么（仅本机）

日志、`coffer.db`（可重建的索引）、`daemon.json`、PID 文件、端口分配、聊天历史、
审计日志，以及任何运行时产物。主密钥**永不**写入导出物。

## 概念

- **导出包（export bundle）** —— 由用户命名的一个目录。其布局：

  ```
  manifest.json                  # bundle schema version + creation time
  knowledge/                     # mirror of ~/.coffer/knowledge
  skills/                        # mirror of ~/.coffer/skills (master skill store)
  resources/<kind>/<name>.yaml   # one deterministic file per config resource
  state/<area>/...yaml           # module-owned shared state
  credentials/<ref>.enc          # Fernet ciphertext blob, opt-in; never the master key
  ```

- **导出（export）** —— 把本机仓库状态写入一个 bundle 目录（镜像文件、序列化资源、
  在被要求时导出密文）。
- **导入（import）** —— 把一个 bundle 应用回本机仓库（把文件镜像回去并重建索引、
  把资源对账进 SQLite、导入密文）。
- **导入落地（import reconciliation）** —— 只对账注册表行是不够的：有些资源配置会
  驱动仅本机的副作用，而这些副作用由各 kind 自己的服务在自己的门口执行（provider
  激活会投影进 agent 的原生配置文件；一个 agent 的注册会安装它的 shim 与会话 hook；
  一个 skill 绑定会物化出一个符号链接）。导入会运行每个 kind 的导入后钩子，使导入
  进来的资源和在本机手工注册的资源一样可用。

## 确定性

资源序列化**必须**是确定性的——键排序、时间戳归一化、剥离仅本机字段。对一个未发生
变化的仓库导出两次，产生的文件字节一致。正是这一点让 bundle 可 diff：用户能读到自己
即将带走的究竟是什么，也能 `diff` 两个 bundle 看出两台机器之间有什么差别。

## 路径可移植

在一台机器上写出的导出物，必须能在 home 目录不同的另一台机器上导入。`$HOME` 下的
绝对路径在导出时以 `~` 哨兵相对存储，导入时对着导入方机器的 home 展开。`$HOME` 之外
的路径原样存储；它们在另一台机器上可能解析不到，这会以该资源的导入错误呈现出来，
而不是变成一次静默的错配。

## 导入语义

- **bundle 说了算。** 对 bundle 中包含的每个资源，导入方仓库采用 bundle 里的那个
  版本。不存在仲裁，因为不存在并发写入方：用户在敲下命令时就选定了方向。
- **导入从不删除。** 本机仓库有、而 bundle 里没有的资源保持原样不动。一个 bundle 是
  某一台机器的快照，而不是对"哪些东西应当到处都存在"的断言。
- **逐资源的失败被报告，而不致命。** 无法在本机应用的资源（例如某个 agent 的
  `config_dir` 并不存在）会带着它的 ref 与原因出现在导入结果里；其余每个资源照常
  导入。
- **更新的 bundle 会被拒绝。** 若某个 bundle 的 `manifest.json` 声明的 schema 版本
  是本构建不认识的，则以清晰的错误快速失败，而不是导入一个只被部分理解的 bundle。

## 凭据

凭据材料以 Fernet 密文随行，且**仅在用户主动要求时**：不给 `--with-credentials`
时导出会略过凭据，因为一个导出目录很容易被随手落在什么地方。

主密钥永不写入 bundle。它经带外途径通过 `coffer sync key export` /
`coffer sync key import` 引导到另一台机器上。只有密文而没有密钥的机器会报
`credentials_locked` 并拒绝拉起受影响的资源——它绝不静默地解密失败。

## Scope

资源的 `scope`（一个 agent 名字列表，
[ADR-045](../../docs/decisions/ADR-045-per-agent-resource-scope.md)）作为资源文档的
一部分原样穿过导出与导入——它是一个普通字段，没有任何专属机制。一个在本机对所有
agent 都不在 scope 内的资源，仍会被注册、仍然可见，只是不被激活。

## 表面

| 表面 | 操作 |
| --- | --- |
| CLI | `coffer sync export <dir> [--with-credentials]` · `coffer sync import <dir>` · `coffer sync key export` / `coffer sync key import` |
| HTTP | `POST /api/v1/sync/export` · `POST /api/v1/sync/import` · `GET /api/v1/sync/key/fingerprint` · `POST /api/v1/sync/key/export` · `POST /api/v1/sync/key/import` |
| UI | 设置 → Sync：一个导出按钮和一个导入按钮，各自打开由守护进程托管的原生目录选择器（spec 004 FR-042 / [ADR-036](../../docs/decisions/ADR-036-daemon-native-file-and-save-dialogs.md)），外加主密钥卡片 |

两个操作都会报告一份摘要：各状态区的计数、失败的资源，以及 bundle 路径。

## Acceptance Scenarios

### Scenario: 把仓库导出到一个目录

- **Given** 一个含有知识、技能与已注册资源的仓库，
- **When** 用户运行 `coffer sync export <dir>`，
- **Then** 该目录中含有 `manifest.json`、镜像过来的文件树、每个配置资源一个确定性
  YAML，且**没有** `credentials/` 目录，命令并报告各状态区的计数。

### Scenario: 未发生变化的仓库导出结果字节一致

- **Given** 一个已经导出到某目录的仓库，
- **When** 用户把这个未发生变化的仓库再次导出到第二个目录，
- **Then** 两个目录中的每个文件都字节一致，除了 manifest 里的创建时间。

### Scenario: 把 bundle 导入一个空仓库

- **Given** 一个从另一台机器导出的 bundle，以及一个没有任何资源的仓库，
- **When** 用户运行 `coffer sync import <dir>`，
- **Then** 知识与技能树被镜像进来，SQLite 索引据此重建，每个配置资源都被注册，
  且每个 kind 的导入后钩子都已运行，因此这些资源无需进一步操作即可使用。

### Scenario: bundle 覆盖已存在的本地资源

- **Given** 一个本地的 `mcp_server:files`，其配置与 bundle 中的那份不同，
- **When** 用户导入该 bundle，
- **Then** 事后本地资源与 bundle 中的版本一致，且该变更被审计记录。

### Scenario: 导入从不删除仅存在于本地的资源

- **Given** 一个 bundle 中并不包含的本地 `mcp_server:local-only`，
- **When** 用户导入该 bundle，
- **Then** `mcp_server:local-only` 仍然处于注册状态且未被改动。

### Scenario: 配置路径跟随各机器的 home

- **Given** 一个在 home 为 `/Users/a` 的机器上导出的 bundle，其中含有一个
  `config_dir` 曾为 `/Users/a/.claude` 的 agent，
- **When** 它在 home 为 `/home/b` 的机器上被导入，
- **Then** 导入后该 agent 的 `config_dir` 是 `/home/b/.claude`。

### Scenario: 在本机无法应用的资源被报告而不致命

- **Given** 一个 bundle，其中含有一个 `config_dir` 在本机并不存在的 agent，以及另外
  三个可导入的资源，
- **When** 用户导入该 bundle，
- **Then** 那三个资源导入成功，且结果中给出失败 agent 的 ref 及其原因。

### Scenario: 未被要求时不导出凭据

- **Given** 一个持有凭据的仓库，
- **When** 用户在不带 `--with-credentials` 的情况下导出，
- **Then** bundle 中没有 `credentials/` 目录，且导入它不会改动本机的凭据存储。

### Scenario: 主密钥绝不进入 bundle

- **Given** 一次带 `--with-credentials` 的导出，
- **When** 检查该 bundle，
- **Then** 其中只有 Fernet 密文块、没有任何密钥材料；把它导入到一台没有密钥的机器上，
  相关资源处于 `credentials_locked` 状态，而不是静默地解密失败。

### Scenario: 旧构建拒绝更新的 bundle

- **Given** 一个 `manifest.json` 声明的 schema 版本比本构建所知更新的 bundle，
- **When** 用户导入它，
- **Then** 导入以清晰的错误快速失败，且什么都不会被应用。

### Scenario: 被 scope 限定的资源导入后保持休眠

- **Given** 一个 bundle，其中的 `mcp_server` 被 scope 到一个在本机并未注册的 agent，
- **When** 用户导入该 bundle，
- **Then** 该服务器被注册且可见，而网关不会把它的工具暴露给本机上的任何会话。

## 不在范围内

- **把 bundle 在机器之间搬运。** `scp`、U 盘，或者用户自己的 git 仓库——Coffer 只
  写出和读入一个目录，不负责搬运它。
- **持续收敛。** 两台机器可以逐渐分叉，Coffer 不会察觉、也不会去调和；解决办法是手工
  重新导出一次（[ADR-016](../../docs/decisions/ADR-016-vault-export-import.md)）。
- **合并两个已分叉的仓库。** 导入是逐资源的最后写入者胜出，不是三方合并。
- **托管的同步端点。** 那需要一次章程修订。
