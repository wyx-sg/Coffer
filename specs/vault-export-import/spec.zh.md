# Spec — 仓库导出与导入

> English: [spec.md](./spec.md)

把一个 Coffer 仓库导出到一个目录，再把那个目录导入回来，从而把它搬到用户自己的
另一台机器上；并通过把这些导出推送到用户自有的 git 远端，留下一份可恢复的副本。
仅限单向备份：不收敛、不合并、不在机器之间仲裁。背景与备选方案见
[Vault Export and Import](../../docs/decisions/vault-export-import.md)。

## 为什么

开发者配置一台新笔记本，或者希望台式机从笔记本已经知道的东西开始。今天每台机器
都是一座孤岛：知识、已注册资源与凭据都得手工重建一遍。

本特性把仓库写入用户选定的目录，并能把这样一个目录读回来。因为导出只是普通的
本地文件输出，它不需要对章程的本地优先原则做任何例外。

手工搬运目录扛不住两种故障：硬盘坏了，以及某样东西被删掉却一周后才发现。前者
需要一份在本机之外的副本，后者需要一段足以回溯到失误之前的历史。因此仓库还可以
按定时备份到用户自己拥有的 git 仓库——这是对本地优先原则的一条有界例外
（章程 0.5.0），因为该远端只是备份，永不充当事实记录方。

## 会导出什么

- **知识** —— `~/.coffer/knowledge/<scope>/` 下的 markdown 文件（这些文件本身
  已经是事实来源）。2026-09-10 知识层合并之后只剩一个根；`~/.coffer/memory/`
  已不复存在。
- **技能** —— `~/.coffer/skills/` 下的 skill 主库。
- **配置资源** —— `mcp_server`、`agent`、`skill`、`channel` 定义（记录系统是
  SQLite；为搬运而序列化成文本）。
- **共享状态** —— 由各模块自有、属于仓库而非某一台机器的状态区（例如渠道对端配对、
  knowledge scope 标签、MCP 能力偏好，以及 **agent 插件清单**）。

  插件清单是**清单，不是复制器**：导出写下这台机器上每个 agent 装了哪些插件；
  导入把这份清单存进金库，不往任何 agent 的配置里写任何东西。Coffer 删掉插件写路径
  的理由就是「手写别人的私有配置格式，在格式变动时会静默写坏它」（spec agent-registry），
  而且它本来就没有 install 路径——所以「替我装上」这件事不提供，就算要提供也得从头写。
  这份清单真正给出的，是任何单个 agent 都做不到的事：新笔记本上的 Codex 不可能知道
  旧笔记本装了哪些插件，因为这个事实只存在于装着它们的那台机器上。
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

**密钥以材料本身跨越，而不是以路径跨越。** `POST /sync/key/export` 收空 body，
把 Fernet 密钥文本放在 `material` 字段里返回；`POST /sync/key/import` 收同一个
`material` 字段，返回仍处于锁定状态的 ref。daemon 不再打开任何由调用方指定的文件
系统路径。各个表面自己做文件 I/O：`coffer sync key export <path>` 由 CLI 自己把
材料写到那个路径（权限 `0600`），`coffer sync key import <path>` 也由 CLI 自己读回
文件；Web UI 则把材料交给浏览器下载，导入时从文件选择框读取。

原因在 Web UI。两个方向过去都走守护进程的原生保存/打开对话框——由守护进程代替用户
执行 `osascript`/`zenity` 并返回选中的路径——而那些对话框已被移除。浏览器本来也拿不到
可以交给守护进程的绝对路径，而文件选择框直接交出**文件内容**，这比一个还要往返
一趟的路径严格地更有用。

代价，直说：密钥材料现在会跨过带 token 守卫的 loopback API，而以前不会。这是可以
接受的。要求导出主密钥的人，无论如何都会拿到明文——导出的含义正是如此——而另一条路
是让守护进程代替用户去执行一个原生对话框程序，只为了省掉一次从未离开 `127.0.0.1`
的跳转。

## 备份

备份远端至多只有一个，且在用户设置之前处于关闭状态。一旦设置，一个 worker 便按
间隔执行备份——daemon 启动时立即跑一次，之后每隔 `interval`（默认一小时）一次
——用户也可以手动触发。

一次运行使用与任何其他导出相同的序列化器和相同的规则导出到工作树，然后：

- 如果导出结果与工作树中已有内容一致，本次运行**不产生提交**。确定性正是这一点
  可靠的前提：未发生变化的仓库产出未发生变化的 bundle，于是备份历史记录的是变化
  而不是心跳。`manifest.json` 是上文确定性规则本就点明的唯一例外——每次导出都会
  给它重新盖上创建时间——所以一个只触及它的暂存差异是被重新盖章的 manifest，
  而不是变化，不值得一次提交。
- 否则提交，提交信息里写明各区的变更计数。
- 然后推送到配置的分支。

**提交绝不因为推送失败而回滚。** 本地历史是恢复的第一层，下一次运行会把积压的
提交推上去。无法认证、够不着网络或被远端拒绝的运行会记录失败并把它呈现出来；
它绝不会杀死 worker，也不会阻塞下一次运行。

备份是否携带凭据密文在配置远端时就已固定，而不是每次运行再决定——与手动导出时
`--with-credentials` 参数所表达的是同一个显式选择。无论如何设置，主密钥都不会被
推送。

推送凭据在推送时从凭据库解析。它绝不写入该仓库的 git 配置，绝不作为命令行参数
传递，并在任何错误文本被记录之前从中抹除。

远端以**引用**而非值来指认这个凭据：密钥先被放进凭据库
（`coffer credentials set <ref> <secret>`），远端只记下这个 ref。因此每一个
展示远端的表面——CLI、HTTP、UI——都可以原样展示而无需脱敏，重新配置远端也不必
重新输入一遍 token。

### 恢复

恢复永远是显式的；任何东西都不会被自动导入。它会拉取远端（工作树尚不存在时先
clone），可选地移动到更早的修订，然后跑普通的导入——沿用上文已经规定的导入语义，
包括绝不删除 bundle 中不存在的任何东西。

由于备份对删除的镜像与对新增一样忠实，远端顶端的 bundle 无法把上周删掉的东西还
回来。要恢复那样东西，就得指定一个修订号或日期，它会被解析成该时间点或之前的
最后一次提交。

## Scope

资源的 `scope`（一个 agent 名字列表，
[Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)）作为资源文档的
一部分原样穿过导出与导入——它是一个普通字段，没有任何专属机制。一个在本机对所有
agent 都不在 scope 内的资源，仍会被注册、仍然可见，只是不被激活。

## 表面

| 表面 | 操作 |
| --- | --- |
| CLI | `coffer sync export <dir> [--with-credentials]` · `coffer sync import <dir>` · `coffer sync key export <file>` / `coffer sync key import <file>` |
| CLI（备份） | `coffer sync remote set <url> [--branch] [--interval] [--with-credentials] [--credential-ref]` · `coffer sync remote show` · `coffer sync remote clear` · `coffer sync push` · `coffer sync restore [--at <rev\|日期>] [--from <url>]` · `coffer sync status` |
| HTTP | `POST /api/v1/sync/export` · `POST /api/v1/sync/import` · `GET /api/v1/sync/key/fingerprint` · `POST /api/v1/sync/key/export` · `POST /api/v1/sync/key/import` |
| HTTP（备份） | `GET\|PUT\|DELETE /api/v1/sync/remote` · `POST /api/v1/sync/push` · `POST /api/v1/sync/restore` · `GET /api/v1/sync/status` |
| UI | 设置 → Sync：一个导出按钮和一个导入按钮，各自打开由守护进程托管的原生**目录**选择器（spec agent-registry FR-042），外加主密钥卡片——后者用浏览器自己的下载与 `<input type="file">`，不走守护进程对话框 |
| UI（备份） | 设置 → Sync：一张形状照搬保留策略卡的备份卡——开关、远端地址、分支、间隔、是否携带凭据、上次运行状态及其错误，以及一个「立即备份」按钮 |

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

### Scenario: 配置一个备份远端

- **Given** 一个尚未配置备份的仓库，
- **When** 用户运行 `coffer sync remote set <url> --with-credentials`，
- **Then** 远端、分支、间隔与凭据选项被保存，备份被启用，命令打印出一次推送会
  包含哪些内容，且 `coffer sync status` 报告该远端且尚无运行记录。

### Scenario: 未发生变化的仓库不产生备份提交

- **Given** 一个已配置的备份，其上次运行结果已经提交，
- **When** 仓库没有任何变化时发生一次备份运行，
- **Then** 导出被写出，不产生任何提交，本次运行被记为成功，仓库历史保持不变。

### Scenario: 发生变化的仓库被提交并推送

- **Given** 一个已配置的备份，以及仓库中新增的一篇知识文档，
- **When** 发生一次备份运行，
- **Then** 工作树持有新的导出，产生一次写明各区计数的提交，该提交被推送到配置的
  分支，本次运行的状态与提交号被记录。

### Scenario: 推送失败但保留提交

- **Given** 一个已配置的备份，其远端不可达，
- **When** 在发生变化的仓库上执行一次备份运行，
- **Then** 提交在本地存在，本次运行被记为失败并带上原因，worker 继续运行，且
  下一次成功的运行会把积压的提交推上去，而不会把它变成第二次提交。

### Scenario: 恢复上周被删掉的资源

- **Given** 一个备份，其历史中包含某个后来在本地被删除、并已把删除镜像上去的
  skill，
- **When** 用户运行 `coffer sync restore --at <删除之前的日期>`，
- **Then** 工作树移动到该时间点或之前的最后一次提交，从它执行导入，该 skill 重新
  被注册，而仓库自那时以来新增的一切原封不动。

### Scenario: 在没有工作树的机器上恢复

- **Given** 一台其仓库尚无备份工作树的机器，
- **When** 用户运行 `coffer sync restore --from <url>`，
- **Then** 仓库被 clone，bundle 被导入，凭据无法解密的资源被报告为
  `credentials_locked` 而不是让整次恢复失败。

### Scenario: 推送凭据绝不进入仓库

- **Given** 一个配置了推送凭据的备份，
- **When** 一次备份运行执行推送，
- **Then** 该凭据不出现在仓库的 git 配置中、不出现在 git 进程的命令行参数中，
  也不出现在任何被记录的错误文本或审计负载中。

### Scenario: 只有远端这样配置时凭据才随行

- **Given** 一个未开启凭据选项的备份远端，
- **When** 发生一次备份运行，
- **Then** 被推送的 bundle 中没有 `credentials/` 目录；而把该选项打开后，下一次
  运行会包含密文——两种情况下主密钥都不在 bundle 中。

## 不在范围内

- **手工把 bundle 在机器之间搬运。** `scp` 或 U 盘仍然是用户自己的事；Coffer 只会
  把 bundle 运送到它被配置的那一个备份远端。
- **多于一个备份远端。** 一个就足以扛住硬盘损坏；第二个是一个没有对应故障的
  扇出问题。
- **自动恢复。** Coffer 绝不会自行从远端导入，daemon 启动时也不会。恢复会覆盖
  本地状态，永远是人的决定。
- **持续收敛。** 两台机器可以逐渐分叉，Coffer 不会察觉、也不会去调和；解决办法是手工
  重新导出一次（[Vault Export and Import](../../docs/decisions/vault-export-import.md)）。
- **合并两个已分叉的仓库。** 导入是逐资源的最后写入者胜出，不是三方合并。
- **托管的同步端点。** 那需要一次章程修订。
