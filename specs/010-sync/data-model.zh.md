# Spec 010 — 数据模型

> English: [data-model.md](./data-model.md)

## 持久化状态

**没有。** 导出与导入是对活着的仓库执行的一次性操作；它们不拥有任何表。没有需要持久化
的同步配置（用户每次调用都自己给出目录）、没有需要用来仲裁的上次运行状态、没有机器
注册表、也没有墓碑账本——持续同步以及为它服务的一切都已被撤销
（[ADR-016](../../docs/decisions/ADR-016-vault-export-import.md)）。

因此 `infrastructure/sync/` 不贡献任何 ORM 模型，除了那次删除已撤销的 `sync_config`、
`sync_state`、`machine_identity` 与 `sync_tombstones` 表的迁移之外，也没有自己的迁移。

导出携带的凭据密文来自既有的 `credentials` 表；资源文档经由 `ResourceService` 来自
既有的资源表。SQLite 仍是本机的事实记录方。

## 文件系统状态（导出包）

一个 bundle 就是用户在每次导出时命名的一个普通目录。Coffer 不在两次运行之间管理它：
不记住关于它的任何信息、不在后台往里写入任何东西，它与其他任何 bundle 也没有关系。

```
manifest.json                  bundle schema version + creation time
knowledge/                     mirror of ~/.coffer/knowledge
skills/                        mirror of ~/.coffer/skills (master skill store)
resources/<kind>/<name>.yaml   one deterministic file per config resource
state/<area>/...yaml           module-owned shared state docs
credentials/<ref>.enc          Fernet ciphertext, base64 text; never the key
```

只有当导出带了 `--with-credentials` 时，`credentials/` 才会存在。

### `manifest.json`

| 字段             | 类型   | 说明                                       |
| ---------------- | ------ | ------------------------------------------ |
| `schema_version` | int    | bundle 布局发生不兼容变更时递增。          |
| `created_at`     | String | 写出该 bundle 的时间，ISO-8601。           |

当前版本：**1**。bundle 是一个有自己版本谱系的新格式；已撤销的 git workspace 的
`schema_version`（当时已到 3）不会延续过来，因为这个格式从未产出过那种布局的 bundle。

`schema_version` 在导入时被校验：比运行中的构建更新的 bundle 会在任何东西被应用之前
以 `SYNC_BUNDLE_TOO_NEW` 快速失败，与数据库的 `DB_SCHEMA_TOO_NEW` 规则一致。
`created_at` 仅供参考——它是同一个未发生变化的仓库两次导出之间唯一合理会不同的字段，
因此确定性比对会排除它。

### 资源序列化（`resources/<kind>/<name>.yaml`）

`Resource` 的确定性投影：

```yaml
kind: mcp_server
name: confluence
description: "..."
enabled: true
scope: ["claude-code"]   # omitted when null (active for every agent)
config: { ... }          # the validated, json-mode config; keys sorted
```

- `created_at` / `updated_at` / 本地 `id` 被**排除**——它们仅属于本机，且会让每次导出
  都与上一次不同。
- 映射的键是排序的；每个资源恰好一个文档，因此一个未发生变化的仓库两次导出字节一致。
- `scope`（[ADR-045](../../docs/decisions/ADR-045-per-agent-resource-scope.md)）是一个
  普通字段——一个 agent 名字列表——原样穿过导出与导入。没有任何专属机制；一个对所有
  本机 agent 都不在 scope 内的资源照样导入，只是不被激活。
- 导出方机器 home 之下的字符串值被归一化为 `${HOME}/...`，并在导入时对着导入方机器的
  home 展开（见[路径可移植](#路径可移植)）。

导入时资源经由 kind 无关的 `ResourceService` 按 `<kind>:<name>` upsert，并运行该 kind
的导入后钩子，从而执行仅本机的副作用（安装 shim、投影原生配置、物化 skill 符号链接）。
本地资源**绝不**会因为一次导入而被删除：某个资源不在 bundle 中不代表任何含义，因为
一个 bundle 是某一台机器的快照，而不是对"哪些东西应当到处都存在"的断言。

### 路径可移植

在一台机器上写出的导出物，必须能在 home 目录不同的另一台机器上导入。

| 路径形态       | 导出时                     | 导入时                             |
| -------------- | -------------------------- | ---------------------------------- |
| `$HOME` 之下   | 存为 `${HOME}/...`         | 对着导入方的 home 展开             |
| `$HOME` 之外   | 原样存储                   | 原样使用；在本机可能解析不到       |

一个在导入方机器上并不存在的原样路径，会呈现为逐资源的导入失败（该资源的 ref 加上
原因出现在导入结果里），既不会是静默的错配，也不会让整次运行致命失败。

### 状态区（`state/<area>/...yaml`）

由各模块自有、属于仓库而非某一台机器的共享状态。每个模块实现 `SyncedStatePort`
（确定性 YAML 文档的导出/导入），由组合根注册这些 provider——sync 切片从不 import
kind 模块。当前的状态区：

- `channel-peers/<channel>/<chat>.yaml` —— 配对身份（chat_id、sender_id、显示名、
  首选 agent、paired_at；仅本机的 `active_conversation_id` 永不随行）。导入执行
  upsert；引用了本机不存在的 channel 的文档，会作为逐文档失败被报告并跳过。
- `mcp-preferences/<server>.yaml` —— 每个服务器上被**禁用**的能力（启用是默认值；
  seen 时间戳仅属本机）。导入把本机存在的服务器对账成与 bundle 一致。
- `settings/embedding.yaml` + `settings/internal-engine.yaml` —— 两个引擎单例。只有在
  导出方机器已经在本地持久化过它们之后才会被导出，因此一台未曾配置过的机器绝不会用
  自己的默认值盖掉另一台机器已配置好的值。
- `memory-labels/<store>.yaml` —— 记忆 store 的用户自设显示标签（spec 007 FR-017c），
  这样一个 `project-<ULID>` store 在导入之后读起来是它的名字，而不是"未命名 store"。
  被清空的标签以一个显式的空标签文档（`{label: ""}`）随行，而不是靠文档缺失——后者
  导入方无法与"从未设置过"区分开。

Skill 投递绑定（`skill_agent_bindings`）按决策保持仅本机：投递是针对各机器不同的目录
执行的、有副作用的文件操作。导入 skill 主库之后，请在每台机器上通过既有的 skill 表面
各自采纳。

### 凭据密文块（`credentials/<ref>.enc`）

`ref` 对应的 Fernet 密文，以 base64 文本存放。没有主密钥、没有明文，除了 ref（即路径）
之外没有任何元数据。

`ref` 可以带斜杠命名空间（例如 `channel/seatalk/app-secret`、`provider/agnes/key`），
因此密文块位于对应的嵌套路径 `credentials/channel/seatalk/app-secret.enc`。导出会创建
父目录；导入递归遍历并从相对路径重建出完整的带斜杠 ref。

被导入到一台没有对应主密钥的机器上的密文原样存储，并被报为 `credentials_locked`；
受影响的资源会拒绝拉起，而不是静默地解密失败。密钥经带外途径引导
（`coffer sync key export` / `coffer sync key import`），且永不出现在 bundle 里。
这两条命令通过 loopback API 传递密钥**材料** —— `POST /sync/key/export` 返回
`{material}`，`POST /sync/key/import` 接收它 —— 文件 I/O 各表面自己做：CLI 自己写、
自己读那个文件（权限 `0600`），Web UI 用浏览器下载与 `<input type="file">`。守护进程
不打开任何由调用方指定的路径。

## 仅本机、绝不进入 bundle

`~/.coffer/logs/`、`coffer.db`、`daemon.json`、PID/端口文件、聊天历史、审计日志，以及
主密钥文件 / 钥匙串条目。

## 派生索引（排除并重建）

那些由事实来源文件*重新生成*出来的文件被排除在镜像之外——把它们带上会让一份陈旧的
副本盖掉刚刚重建出来的那份。记忆 store 的 `MEMORY.md` 索引就是当前的例子：逐条事实的
`<slug>.md` 文件随行，而 `MEMORY.md` 由导入进来的事实重建。这个集合与 bundle 布局一起
定义在 `infrastructure/sync/` 中。
