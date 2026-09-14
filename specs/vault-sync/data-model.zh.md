# 数据模型——仓库同步

> English: [data-model.md](./data-model.md)

同步的持久化分布在三个地方，而谁放什么正是整个设计：

| 在哪 | 放什么 | 为什么在那 |
| --- | --- | --- |
| SQLite | 那唯一一个同步远端的配置 | 它是用户输入的配置，和别的配置一样 |
| 一个本地 JSON 文件 | pointer、重试集、「本机不适用」集 | 它必须在数据库打开之前就可读，而且**绝不**能随行 |
| 工作树 | 每一份 vault 文档，以及机器注册表 | 那是 git 要合并的东西 |

vault 本身保持它既有的事实记录方：知识与技能是文件、配置资源是经
`ResourceService` 够到的行、凭据是密文行。同步不拥有其中任何一个。

## SQLite —— `sync_remotes`

与备份远端时相比没有变化，靠构造保证只有一行（`id = 1` 是一条检查约束，不是约定）。
双向收敛不需要新增任何列：一轮的 base 是 pointer，而 pointer 在本地；注册表就是那棵树。

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `id` | int | 钉死为 1 |
| `url` | str | 用户自己的仓库 |
| `branch` | str | 默认 `main` |
| `credential_ref` | str? | 指向凭据库的**引用**，绝不是密钥本身 |
| `include_credentials` | bool | 密文是否随行；默认关 |
| `interval_seconds` | int | 默认 3600，由检查约束保证 `> 0` |
| `enabled` | bool | 用户配置远端之前，同步是关着的 |
| `worktree_path` | str | 默认 `~/.coffer/sync` |
| `last_run_at` | ts? | 最近一轮 |
| `last_status` | str? | 见下面的词汇表 |
| `last_error` | str? | 写入之前已抹除推送凭据 |
| `last_commit` | str? | 上一轮落到的提交 |
| `updated_at` | ts | |

因为 `credential_ref` 是引用，整行都可以原样读进 API 响应或日志行而无需脱敏。

`last_status` 采用轮次的词汇表：`ok`、`no_change`、`joined`、`conflict`、
`awaiting_confirmation`、`push_failed`、`error`。这些 `last_*` 列描述的是最近一轮
而不是一段历史——远端上的 git 历史才是「改了什么」的真正记录，而下面说的应用前快照
才是「本机应用了什么」的记录。

## SQLite —— `sync_convergence_state` 与 `sync_held_paths`

指针与它的两个伴生集合。它们落在 `coffer.db` 里，因为这个数据库本来就是机器
本地的、本来就不进工作树，于是不必再多一处存储需要推理——而且**指针绝不能
上路**：它是这台机器对"自己吸收到哪里"的断言，另一台机器把它当成自己的 base，
正是本规范要防的那种互删形状。

`sync_convergence_state` 是单行固定行：

| 列 | 含义 |
| --- | --- |
| `pointer` | 这个 vault 确实吸收到的那个 commit，是每次 diff 的 base。`NULL` 表示**正在加入**，这一情形由回合自己对着远端注册表识别并解决，在动任何东西之前 |
| `pending_json` | 被挡下的一轮——熔断方向、它到达的 commit、它是针对哪个远端 tip 抬起的、各 area 的越界数与路径。没有挂起时为 `NULL` |

`sync_held_paths` 用一张表承载两个集合，靠 `applicable` 区分：

| `applicable` | 含义 |
| --- | --- |
| `true` | **重试集** —— 树里有、而这个 vault 还没吸收的路径。每轮重试、作为错误上报、成功即移出 |
| `false` | **本机不适用** —— 在这台机器上根本无法应用的路径（例如 `config_dir` 在本机不存在的 `agent`）。同样被保留，但不重试、不报错——关于这台机器的一个事实，不该变成用户学会忽略的错误 |

无论哪一种，导出都**不得**删除被保留的路径。删掉它就会把"这个 vault 没能吸收
它"变成"用户删掉了它"——正是整个设计要防的那种混淆，只是换了一扇门进来。

与挂起一同存下的**远端 tip**，是让"确认"具有确切含义的东西。被确认的一轮是
**重新推导**而不是续跑——序列化是确定性的，同一个 vault 对同一个远端必然产出
用户看过的那份 diff——而删除熔断只对那个确切的 tip 豁免。远端在这期间动过，
熔断就会再次运行，这一轮被重新挂起。

`EMPTY_TREE`（git 的空树哈希）是**新机器**起步时的指针。它在这一列里就是一个
普通取值、不是标志位，这正是"新机器不可能删掉任何东西"成为结构性质、而非代码
里一个特例分支的原因。

十个 apply 前快照以 git tag 保存在工作树里（`coffer/pre-apply/<时间戳>`），而不是
存成数据行：tag 的树**就是** apply 之前 vault 的样子，所以回滚就是同一套应用器
反向跑一遍那个 diff。

## 工作树 —— `~/.coffer/sync`

vault 被序列化进去的那个目录，同时也是 git 工作树。那里已存在的 git 仓库会被连同历史
一起接管。

```
manifest.json                  tree schema version
knowledge/                     mirror of ~/.coffer/knowledge
skills/                        mirror of ~/.coffer/skills (master skill store)
resources/<kind>/<name>.yaml   one deterministic file per config resource
state/<area>/...yaml           module-owned shared state docs
credentials/<ref>.enc          Fernet ciphertext, base64 text; never the key
machines/<machine_id>.yaml     one descriptor per machine
```

只有当远端被配置为携带密文时，`credentials/` 才会存在。

对这棵树的每一次写入都是**差分的**：写入发生变化的文档、移除 vault 不再持有的文档，
任何目录都不会被清空重写。正是这条规则让「我从来没有过它」与「我把它删了」在 git 看到
的 diff 里保持可区分。

### `manifest.json`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | int | 树的布局发生不兼容变更时递增 |

当前版本：**1**。这棵树是一个有自己版本谱系的新格式；无论是已撤销的 git workspace 的
版本（当时已到 3）还是导出 bundle 的版本，都不会延续过来。

`schema_version` 在一轮应用任何东西之前被校验：比运行中的构建更新的树会以
`SYNC_TREE_TOO_NEW` 快速失败，与数据库的 `DB_SCHEMA_TOO_NEW` 规则一致。bundle manifest
过去携带的 `created_at` **没有了**——一个每轮都被重盖的时间戳会让「只改了 manifest」的
差异成为唯一永远在变的东西，而确定性正是让一轮无话可说时干脆不产生提交的前提。应用
diff 时 `manifest.json` 在两个方向上都被忽略。

### 资源序列化（`resources/<kind>/<name>.yaml`）

`Resource` 的确定性投影：

```yaml
kind: mcp_server
name: confluence
description: "..."
enabled: true
scope:
  agents: [claude-code]
  machines: ["a3f21c9e4b7d2610"]
config: { ... }          # the validated, json-mode config; keys sorted
```

- `created_at` / `updated_at` / 本地 `id` 被**排除**——它们仅属于本机，且会让每一轮
  都产生一次提交。
- 映射的键是排序的；每个资源恰好一个文档，因此未发生变化的 vault 产出未发生变化的树。
- 本机 home 之下的字符串值被归一化为 `${HOME}/...`，并在应用时对着应用方机器的 home
  展开（见下）。

应用一条新增或修改，会经由 kind 无关的 `ResourceService` 按 `<kind>:<name>` upsert，
并跑该 kind 的导入门禁；应用一条删除则删除该资源，从而释放没有其他资源引用的凭据。
整个 diff 应用完毕后，每个 kind 的导入后钩子会依据当前状态重新执行它仅本机的副作用
——原生配置投影、shim、skill 投递。

### `scope_json` —— 从一个列表变成两条轴

持久化形态发生变化，并由一条 migration 改写每一行：

| | 之前 | 之后 |
| --- | --- | --- |
| 不受限 | `null` | `null` |
| 只限 agent | `["claude-code"]` | `{"agents": ["claude-code"], "machines": null}` |
| 只限机器 | —— | `{"agents": null, "machines": ["a3f21c9e4b7d2610"]}` |
| 两者都限 | —— | `{"agents": ["claude-code"], "machines": ["a3f21c9e4b7d2610"]}` |
| 休眠 | `[]` | `{"agents": [], "machines": null}` |

两条轴是 `AND` 的关系，且各自 `null` 表示不受限，因此每一行既有数据都是**只增不减**
地迁移过去：`machines: null` 精确复现今天的行为。迁移是一次性的，不留任何加载期垫片
——`Scope.from_json` 只接受对象形态。

机器轴以 `machine_id` 为键，绝不以显示名为键，因此重命名一台机器毫无代价。未知的
machine id 是合法的，只是永远匹配不上，与今天未知的 agent 名字完全一样。scope 编辑器
从注册表构建机器列表，而不是接受自由文本，因此一个敲错的 id 不可能静默地让某个资源
失效。

### 机器描述符（`machines/<machine_id>.yaml`）

每台机器一个文档。每台机器**只写自己的**，因此这些文档占据互不相交的路径、不可能冲突；
git 轻而易举地合并它们。注册表就是 `machines/*.yaml` 此刻持有的内容——一个派生视图，
不是一张同步的表。

```yaml
machine_id: a3f21c9e4b7d2610
name: Desktop
os: darwin
hostname: studio.local
coffer_version: 0.5.0
last_converged_at: 2026-09-13
last_converged_commit: <40-hex commit sha>
key_fingerprint: <12-hex sha256 of the master key>
agents: [claude-code, codex]
```

| 字段 | 说明 |
| --- | --- |
| `machine_id` | `sha256("coffer-machine:" + raw)` 截断到 16 个十六进制字符。原始主机标识符——macOS 上的 `IOPlatformUUID`、Linux 上的 `/etc/machine-id`——是硬件标识符，**不得**写进这里。两者都读不到时，raw 是一次性生成并写入 `~/.coffer/machine-id`（权限 `0600`）的 UUID；那一种撑不过删除 `~/.coffer`，机器页面会如实说明 |
| `name` | 用户的标签，默认取自 hostname。任何时候都可改、且毫无代价，因为没有任何东西以它为键 |
| `os`、`hostname`、`coffer_version` | 描述性字段，供机器表格展示 |
| `last_converged_at` | 一个**日期**，每个自然日最多重盖一次，因此一台开着但闲置的机器不会每轮都提交一次心跳。UI 说的是「上次收敛的那一天」，不是「上次收敛于」 |
| `last_converged_commit` | 这台机器的 pointer，被发布出去，好让远端能把它交还回来。每轮都重盖。这正是一台**回归**机器在本地 pointer 丢失后恢复 base 的依据 |
| `key_fingerprint` | 与 `GET /sync/key/fingerprint` 返回的同一个短哈希，因此机器表格可以直接说明另一台机器的凭据在本机解不开 |
| `agents` | 该机器上已注册的 agent 名字 |

id 被缓存在 `daemon-config.json` 里、丢了就重新算；名字住在这里，因此它会同步。这种
不对称很要紧：`machine_id` 是描述符的文件名、是 `scope.machines` 的引用、是表格的键，
而一台以新身份回来的机器会变成幽灵——所有 scope 到旧身份的东西都会悄无声息地停掉。

应用 diff 时对 `machines/*.yaml` 在两个方向上都**什么都不做**：注册表是从树里读出来的，
绝不投影进任何本地的东西。

### 状态区（`state/<area>/...yaml`）

由各模块自有、属于 vault 而非某一台机器的共享状态。每个模块实现 `SyncedStatePort`，
由组合根注册这些 provider——sync 切片从不 import kind 模块。当前的状态区：

- `channel-peers/<channel>/<chat>.yaml` —— 配对身份（chat_id、sender_id、显示名、
  首选 agent、paired_at；仅本机的 `active_conversation_id` 永不随行）。引用了本机
  不存在的 channel 的文档会被报为逐路径失败并进入重试集。
- `mcp-preferences/<server>.yaml` —— 每个服务器上被**禁用**的能力（启用是默认值；
  seen 时间戳仅属本机）。
- `agent-plugins/<agent>.yaml` —— 插件清单：每台机器上每个 agent 装了哪些插件与
  marketplace。这是**清单，不是复制器**——应用它不会往任何 agent 的配置里写任何东西。
- `settings/internal-engine.yaml` —— 内部引擎单例：`model`、`auto_tidy_enabled`，
  现在再加 `tidy_owner_machine_id`。owner 这个字段正是让一个无人值守的改写器在多台
  机器上也安全的东西：除 owner 之外的每台机器上，一趟 tidy 都是空操作。只有在本机
  已经在本地持久化过这个单例之后，该文档才会被导出，因此一台全新的机器绝不会用自己的
  默认值盖掉整队已配置好的值。

Skill 投递绑定（`skill_agent_bindings`）按决策保持仅本机：投递是针对各机器不同的目录
执行的、有副作用的文件操作。

### 凭据密文块（`credentials/<ref>.enc`）

`ref` 对应的 Fernet 密文，以 base64 文本存放。没有主密钥、没有明文，除了 ref（即路径）
之外没有任何元数据。

`ref` 可以带斜杠命名空间（例如 `channel/seatalk/app-secret`），因此密文块位于对应的
嵌套路径。回来时会从相对路径重建出完整的带斜杠 ref。

这些密文块永远不会进入文本合并。Fernet token 在明文里带着自己的加密时间，因此同一个
ref 的两份密文**无需密钥**就能排序，更新的那次加密胜出。这条规则只适用于这里，别处
一概不适用。

被应用到一台没有对应主密钥的机器上的密文原样存储，并被报为 `credentials_locked`；
受影响的资源会拒绝拉起，而不是静默地解密失败。密钥经带外途径引导
（`coffer sync key export` / `coffer sync key import`），且永不进入该仓库。这两条命令
通过 loopback API 传递密钥**材料** —— `POST /sync/key/export` 返回 `{material}`，
`POST /sync/key/import` 接收它 —— 文件 I/O 各表面自己做：CLI 自己写、自己读那个文件
（权限 `0600`），Web UI 用浏览器下载与 `<input type="file">`。守护进程不打开任何由调用方
指定的路径。

## 路径可移植

在一台机器上写出的文档，必须能在 home 目录不同的另一台机器上应用。

| 路径形态 | 写成 | 应用为 |
| --- | --- | --- |
| `$HOME` 之下 | `${HOME}/...` | 对着应用方机器的 home 展开 |
| `$HOME` 之外 | 原样 | 原样；在本机可能解析不到 |

一个在本机并不存在的原样路径会呈现为逐路径失败——轮次报告里给出路径加原因——既不会是
静默的错配，也不会让整轮致命失败。

## 仅本机、绝不进入树

`~/.coffer/logs/`、`coffer.db`、`daemon-config.json`、PID 与端口
文件、聊天历史、会话、审计日志、MCP 调用记录，以及主密钥文件 / 钥匙串条目。

会话与审计日志是被刻意排除的：它们是*在某台机器上*发生了什么的记录，而把两台机器的
活动历史合并起来，会是一个形状完全不同的另一个特性。

## 派生文件（排除并重建）

排除集**今天是空的**，而这一点值得明说而不是留作默契：`knowledge/` 与 `skills/` 下的
一切都是事实来源，隐藏条目也包括在内——一个 collection 的 `.raw/` 原件、以及一趟 tidy
移进 `.history/` 的旧版本，与笔记本身一样都是另一台机器该拿到的东西。知识层的目录是
每次调用现生成的，不是文件，因此那里没有什么需要排除。

规则本身为将来准备着：一个由事实来源文件*重新生成*出来的文件应被排除在镜像之外，因为
把它带上会让一份陈旧的副本盖掉刚刚重建出来的那份。这个集合与树的布局一起定义在
`infrastructure/sync/` 中。
