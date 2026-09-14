# Spec — 仓库同步

> English: [spec.md](./spec.md)

让用户自己的每一台机器都与一个他拥有的 git 仓库收敛，从而在多台机器上维持
同一个 vault。一个后台 worker 把本 vault 的内容提交上去，交给 git 与远端做
三路合并，再把合并得出的差异应用回来——删除也一样。背景与备选方案见
[Vault Sync](../../docs/decisions/vault-sync.md)。

## 为什么

开发者在笔记本和台式机上做同一个项目。两台机器都会产生 vault 状态：知识文件、
skill、MCP 注册、agent 配置、凭据。不收敛的话每台机器都是一座孤岛；而所谓的
解法——这边导出、把目录搬过去、那边导入——是一件没人会勤快到让两台机器始终
保持一致的杂活。

与用户自有的 git 远端收敛，是对章程本地优先原则（0.6.0）的一条有界例外：远端
是**汇合点，不是记录系统 (system of record)**。每台机器的 vault 都保持完整且
权威，因此远端可以被删掉，再从任意单台机器重建，不会丢失任何东西。

## 同步什么

- **知识**——`~/.coffer/knowledge/<collection>/` 下的 markdown 文件。
- **Skill**——`~/.coffer/skills/` 下的主 skill 存储。
- **配置类 resource**——`mcp_server`、`agent`、`skill`、`channel`、`knowledge`、
  `provider` 的定义（记录系统是 SQLite；序列化为文本）。
- **共享状态**——归 vault 而非归某一台机器所有的模块自管区域：channel 的 peer
  配对、MCP 能力偏好、内部引擎设置，以及 agent 的插件清单。

  插件清单是**清单，不是复制器**：它记录每台机器上每个 agent 装了哪些插件，
  不会往任何 agent 的配置里写任何东西。
- **凭据**——**只有 Fernet 密文**，且仅在用户主动开启时。
- **机器描述符**——每台机器一份小文档，见下文。

## 不同步什么（本机专属）

日志、`coffer.db` 本身、`daemon-config.json`、PID 文件、端口分配、聊天历史、
对话、审计日志、MCP 调用记录，以及任何运行时产物。主密钥**永远不会**被写进
仓库。

对话和审计日志是被刻意排除的：它们记录的是*在某台机器上*发生了什么，而把两台
机器的活动合并成一段历史，那是另一个形态完全不同的特性（见 `/activity`）。

## 概念

- **同步远端 (sync remote)**——至多一个用户拥有的 git 仓库，本 vault 与之收敛。
  配置项包括 URL、分支、推送凭据引用、间隔，以及凭据密文是否随行。用户配置
  之前一直处于停用状态。
- **工作树 (working tree)**——vault 被序列化进去的目录，同时也是 git 的工作树。
  默认 `~/.coffer/sync`。如果那里已有一个仓库，则连同其历史一起沿用。
- **Vault 文档**——vault 中某一项状态在工作树某个路径上的序列化形态：一个知识
  文件、一个 skill 文件、一份 resource YAML、一份 state YAML、一个凭据 blob、
  一份机器描述符。
- **收敛轮次 (converge round)**——一个完整周期：序列化本地状态、与远端合并、
  应用合并带回来的东西、推送。详见下文。
- **Pointer**——本 vault 已被证实吸收 (absorb) 的那个 commit，存在本机。它是
  每一次 diff 的基点，也是算法唯一需要的机器身份。它从不外传。
- **重试集 (retry set)**——工作树里有、但本 vault 尚未吸收的路径。与 pointer 一起
  存在本机。导出器不得删除它们。
- **机器 (machine)**——一次 Coffer 安装，由一个从宿主机派生的稳定 id 标识，
  并带一个用户可随意更改的显示名。

## 机器这一维度

### 身份是派生的，名字只是标签

一台机器有两样彼此独立的东西：

| | `machine_id` | `machine_name` |
| --- | --- | --- |
| 来源 | 从宿主 OS 派生 | 用户选定，默认取 hostname |
| 是不是键？ | **是**——描述符文件名、`scope` 引用、表键 | 否 |
| 可变？ | 否 | **是，随时改，零代价** |
| 存放 | 缓存在 `daemon-config.json`，丢了就重算 | 存在该机器的描述符里，因此会同步 |

`machine_id` 必须能扛过 Coffer 的重装与卸载，因为一台以新身份回来的机器会变成
幽灵：所有 scope 到旧 id 的东西都会悄无声息地失效。因此它从宿主机派生，而不是
由 Coffer 生成：

- **macOS**——取 `IOPlatformExpertDevice` 的 `IOPlatformUUID`。
- **Linux**——取 `/etc/machine-id`，回退到 `/var/lib/dbus/machine-id`。
- **回退**——两者都读不到时，生成一次 UUID 并存到 `~/.coffer/machine-id`
  （权限 `0600`）。这一种**不能**扛过删除 `~/.coffer`，机器页面会明确写出来，
  因为这样的机器会以新 id 重新出现，旧描述符必须手工删掉。

宿主机的原始标识符不得被写进仓库——它是硬件标识符。真正外传的是
`sha256("coffer-machine:" + raw)` 截断到 16 位十六进制字符。

### 注册表是派生视图，不是被同步的表

每台机器只写一份文档，位于 `machines/<machine_id>.yaml`，并且**不写任何别的
机器的**。因为每台机器占据互不相交的路径，这些文档不可能冲突；git 能轻松合并
它们。注册表就是 `machines/*.yaml` 当前的内容。

一份描述符携带：`name`、`os`、`hostname`、`coffer_version`、
`last_converged_at`、`last_converged_commit`、`key_fingerprint`，以及该机器上
已注册的 agent 名字。

`last_converged_commit` 就是这台机器的 pointer，发布出去是为了让远端能把它还
回来。pointer 本身是本机状态，是可能丢的——丢给一次重装、一次被抹掉的
`~/.coffer`、一块从别处恢复回来的磁盘——而一台没带着它重新加入的机器，正是
下一节要处理的那个危险情形。

`key_fingerprint` 与 `GET /sync/key/fingerprint` 返回的是同一个短哈希，因此机器
表可以直接说明另一台机器的凭据在本机解不开，而不必让用户手工比对指纹。

`last_converged_at` **每个自然日至多重盖一次**，这样一台开着但没事干的机器不会
每轮都提交一次心跳。因此它的含义是「本机最后一次收敛是哪天」，UI 也这么写。

### Scope 多出一个机器轴

`scope` 变成两个彼此独立、`AND` 在一起的列表，各自为 `null` 表示不限制：

```yaml
scope:
  agents: [claude-code]
  machines: ["a3f21c9e4b7d2610"]
```

一个 resource 在机器位于 `machines` **且**会话的 agent 位于 `agents` 时才是活跃
的。未知的机器 id 处于休眠状态，正如今天未知的 agent 名字一样。

这能表达「只要台式机上那个 Claude Code」，而不需要 0.3.0 设计里那张机器 × agent
矩阵：只有当要在一个 resource 上说「台式机的 Claude Code *加上*笔记本的 Codex」
时才需要成对矩阵，而已观察到的用法里没有这种需求。`machines: null` 精确复现
今天的行为，因此既有行只需增量迁移。

scope 编辑器必须把机器做成从注册表构建的选择列表，绝不能是自由文本，这样打错
一个 id 就不会悄悄停掉一个 resource。当某个 resource 在本机不活跃时，UI 必须
说明是哪一个轴把它排除掉的。

`enabled` 继续同步。一个 resource 在哪里运行只由 `scope` 表达——一套机制，
不是两套。

## 收敛轮次

一轮共七步，而其顺序正是本规格最重要的内容：它就是 2026-07-10 那次互相删除
得以避免的原因。

```
0  Repair    — if the working tree's HEAD is not the pointer, reset to the pointer
1  Serialize — export the vault into the tree (differentially), commit as L
2  Merge     — fetch, then merge origin/<branch> into L with base merge-base(L, R) → M
3  Diff      — D := git diff L..M
4  Guard     — circuit-breaker check on D; tag L as the pre-apply snapshot
5  Apply     — apply D to the vault, path by path
6  Publish   — push M; pointer := M; unapplied paths join the retry set
```

### 为什么本地状态要在合并之前提交

先拉再应用会丢掉本地改动。当工作树停在 pointer 上且没有本地 commit 时，一次
fetch 会直接快进，git 根本没机会做三路合并，于是应用远端改动就会覆盖掉 vault
在同一路径上的任何修改。

先提交本地状态，等于把 git 需要的三个输入都给了它——base `P`、本地 `L`、
远端 `R`——于是同一文件的不同 hunk 能合并、相同 hunk 会冲突，而 diff `L..M`
里装的**恰好就是远端贡献的那部分**。此刻 vault 等同于 `L`，因此把 `L..M`
应用上去就把它落到了 `M`，同时本地改动完好无损。

### 为什么删除是安全的

删除只在它作为一次删除出现在 `D` 里时才会被应用，而一次删除之所以能进到 `D`，
只可能是因为某台机器确实相对共享 base 删掉了那份文档。一台仅仅是*没有*某份
文档的机器，相对它自己的 base 并没有做出任何改动，而 git 把「未改动」视为一句
什么都没断言的话。

这正是 0.3.0 设计给不出的保证，因为它的导出是拿本地状态整体重写整棵树的——
这让「我从来就没有过它」和「我把它删了」在 git 看到的 diff 里无法区分。

有两条规则维护着那份 diff 的诚实性，且二者都是规范性 (normative) 的：

- **导出必须是差分写入。** 它写入变化了的文档，并移除 vault 不再持有的文档。
  它**不得**清空并重写一个目录。
- **导出绝不删除重试集里的路径。** 一份本 vault 没能吸收的文档是待处理，不是
  被删除。

### Pointer 只在吸收之后前进

一轮完成时 pointer 可以前进到 `M`。任何应用失败的路径会进入重试集，下一轮重试，
成功后离开该集合。如果一条路径失败的原因是它在本机根本无法应用——比如某个
`agent` 的 `config_dir` 在这台机器上不存在——则记为**本机不适用**而非待处理：
它像重试集路径一样被保留，但不重试、也不报为错误，并且 UI 会提示把它 scope 到
它真正该去的机器上。

### 加入一个远端

一台没有 pointer 的机器正在加入。加入者有两种，而它们需要的处理恰好相反，
因此本轮必须在做任何事之前把它们区分开。它做得到：远端的注册表要么持有这台
机器的 id，要么没有——这正是把机器 id 做成**派生**的所换来的东西。

**新机器取并集。** 它的 id 不在注册表里。pointer 被置为 git 的空树，于是 `D`
是一份从「无」出发的 diff，只可能包含新增。这台机器会拿走远端持有的一切、
保留自己已有的一切，而下一轮把二者一并发布。删除在这里是结构上不可能，而不
只是被规避掉了。

**回归的机器找回自己的 base。** 它的 id 在注册表里，说明它此前收敛过，而它的
描述符写明了它当时到达的 commit。那个 commit 成为 pointer，本轮按一次普通的
陈旧机器轮次推进：三路合并接受远端的删除、保留这台机器的编辑，什么都不会
复活。

把一台回归的机器当成新机器，正是这条规则要防的那种失效。它的 vault 里仍然
装着它丢掉 pointer 之前装着的东西，于是一次取并集会把其它机器在它离开期间
删掉的状态重新发布出去——所有删除一次性被撤销，而且不会有任何冲突，因为
取并集根本没有 base 可供分歧。

**一台 vault 已经没了的回归机器，绝不能把这次损失发布出去。** 找回来的 base
只有在 vault 仍然大致持有那个 commit 所持有的东西时才是正确的。一次连
`~/.coffer` 一起带走的重装，留下的是一个空 vault 加一个有效的 pointer，而合并
会把这读成「这台机器把一切都删了」——还是 2026-07-10 那个形状，只是从另一个
方向到达。Coffer 分辨不出被抹掉的磁盘和一次有意的清空，所以它不去试：由下文
发布侧的熔断器停下本轮并发问。

因此加入是一个显式的、有上报的动作。无论属于哪一种，各界面都会在应用任何东西
之前说明发现了什么——是哪一种情形、这台机器上次收敛是什么时候、此后远端改了
多少份文档、本 vault 又改了多少。

**受损的机器有第三个答案。** 在发布侧熔断挡下一轮的地方，确认和拒绝对一个丢了
文件的 vault 都是错的：确认会把损失扩散到其他每一台机器，拒绝则让它永远卡在
同一轮上。**重建**用远端的内容替换本机 vault，丢弃只有这台机器持有的文档，并且
什么都不推送。它是刻意破坏性的，而且非用户指名索要不会走到。

回归机器若其记录的 base 已不在远端历史里，同样没有安全默认——当成新机器会复活
别人删掉的东西，直接重建会丢掉只有它有的东西——所以这种情形会被拒绝，直到用户
选一个。

只要某一轮在没有 pointer 的情况下开始，这套判别就会跑，而不仅仅是在
`coffer sync adopt` 之下，这样在一台已经忘掉 pointer 的机器上配置远端，也绕不
过去。

## 应用 diff

| 路径 | 新增 / 修改 | 删除 |
| --- | --- | --- |
| `knowledge/**`、`skills/**` | 写文件 | 删文件 |
| `resources/<kind>/<name>.yaml` | 经 resource 服务 upsert，展开 `${HOME}` 并跑该 kind 的导入闸门 | 删除该 resource |
| `state/<area>/**` | 由该区域的 provider 应用该文档 | 由该区域的 provider 移除它 |
| `credentials/<ref>.enc` | 写入密文，受下文的新鲜度规则约束 | 删除该凭据 |
| `machines/*.yaml` | 不做任何事——注册表是从树上读的 | 不做任何事 |
| `manifest.json` | 忽略 | 忽略 |

删除一个 resource 会释放已无任何剩余 resource 引用的凭据，与其它任何删除一样。
diff 应用完之后，每个 kind 的导入后钩子会依据当前状态重新施加它的本机副作用
——原生配置投射、shim、skill 投递。

逐路径的失败会被上报，且绝不中断本轮。

## 冲突

绝大多数并发编辑并不是冲突：git 无需帮忙就能合并同一文件的不同 hunk。下面讲的
是剩下那部分。

1. **凭据 blob 永远不进文本合并。** 一个 Fernet token 以明文携带它的加密时间，
   因此同一个 ref 的两份密文无需密钥就能排出先后。更新的那次加密胜出。本规则
   只适用于 `credentials/*.enc`，不适用于任何别的东西。
2. **agent 可以试着处理其余部分。** 当配置了内部模型时，会有一次有界的处理去
   解决剩余冲突，且**只在工作树里**进行，绝不针对活的 vault。它的产出必须通过
   一道校验闸门——文档能解析、resource 文档能校验通过、且不残留任何冲突标记
   ——才会被当成普通的合并结果。无论成功与否，解决结果连同路径都会被上报，
   因为一台机器悄悄合并了用户自己的笔记，恰恰是用户最想知道的事。
3. **否则本轮停止。** 若没有配置模型，或该处理失败、或其产出没通过闸门，本轮
   中止：vault 不被触碰，pointer 不前进，各个界面会点名冲突路径以及持有它们的
   工作树。用户用自己的 git 工具解决，下一轮继续。

一次冲突会在两台机器上同时阻塞收敛。这是有意为之：两台机器就同一份文档悄悄
各执一词，比两台机器一起等着更糟。

## 安全

双向收敛会在没有人类介入的情况下写 vault，因此有两道规范性的护栏。

- **应用前快照。** 第 4 步给 `L` 打 tag，按构造其树就是应用之前那一刻 vault 的
  状态。回滚就是同一套机械反着跑一遍——应用 `M..L`。保留最近十个快照。
- **熔断器 (circuit breaker)，双向生效。** 某一轮的 diff 若会删掉超过配置比例的
  文档——默认超过某个区域内文档数的 20%，或超过 20 份文档——则不予推进。它会
  被记为需要确认，各界面列出它将移除的内容，由用户接受或拒绝。

  这道护栏既适用于本轮将要**应用到 vault** 的内容，也同等适用于本轮自己的导出
  将要**作为删除发布出去**的内容。当受损的正是这台机器时，起作用的是第二个
  方向：一个因为重装、一次失败的恢复或一条失手的 `rm -rf` 而丢了文件的 vault，
  否则就会把这次损失当作一次普通删除发布出去，把其它机器一起拖下水。以新机器
  身份加入的机器在两个方向上都没有删除，因此不受影响。

这两道护栏都不能取代基于 diff 的应用；它们只是给其中的缺陷划定损失上限。

## 无人值守的改写器

一个在无人审阅 diff 的情况下改写 vault 内容的 worker，在一台机器上是安全的，
在多台机器上就不安全了。知识层的 **tidy** 就是今天已经存在的这种情况：它合并
重复笔记、拆分过长的笔记，并删掉内容已经搬去别处的那个文件。

在两台机器上对同一个语料跑，它会产生一种 git 看不见的失效。两台机器都把笔记
`n1` 和 `n2` 合成了一份主题文档，但合成的是*不同*的文档——这边叫 `t1`，那边叫
`t2`。合并是干净的：两台机器都认为 `n1` 和 `n2` 被删除了，而 `t1` 和 `t2` 是在
不同路径上的新增。结果 vault 把同一份知识存了两遍，而全程没有任何冲突。

由此得出三条规则，且都是规范性的。

- **同步内容的无人值守改写器必须指定唯一一台 owner 机器。** tidy 设置多出一个
  owner 字段，成为被同步的状态，在其它每台机器上跑一次 tidy 都是空操作。tidy
  本来就默认关闭且是安装级的，所以这只多花一个字段，而不是多一个概念。如果
  owner 机器关着，就不会有 tidy——对一个后台锦上添花的功能来说，这是正确的
  取舍。
- **一次 tidy 与一轮收敛绝不重叠。** 二者都写 vault，而在改写途中取到的导出是
  一份撕裂的快照。它们抢同一把锁。此外，当有冲突或待确认项悬而未决时也会跳过
  tidy，这样改写就绝不会叠加在一次未解决的分歧之上。
- **删除对编辑，向编辑一侧收敛。** 当 owner 的 tidy 删掉了一份别的机器编辑过的
  文档时，保留编辑、丢弃删除。一次新鲜的编辑是某个人或某个 agent 刚刚做出的
  决定；而那次删除只是一次整理判断，下一次 tidy 自然还会再做一遍。

保留期清理 worker 不需要这一整套：它清理的是审计日志、MCP 调用记录和对话，
这些都不同步。

## 确定性与路径可移植性

resource 与 state 的序列化必须是确定性的——键排序、时间戳归一化、剥掉本机
专属字段——这样一个没变过的 vault 就会产出一棵没变过的树。确定性正是「无话
可说的一轮不产生 commit」的前提，也正是历史能被用户自己的 git 工具读懂的前提。

`$HOME` 之下的绝对路径以 `~` 哨兵存储，并按每台机器的 home 展开。`$HOME` 之外
的路径原样存储，在另一台机器上可能应用失败，表现为一次逐路径失败。

## 凭据

只有当远端被配置为携带凭据密文时，密文才会外传。主密钥永远不会被写进仓库；
它通过 `coffer sync key export` / `coffer sync key import` 以带外方式引导到另一台
机器上，而持有密文却没有密钥的机器会把那些 ref 报为已锁定，而不是悄无声息地
解密失败。

推送凭据在推送时从凭据存储解析，按引用指名、绝不按值传递。它不会进入仓库的
git config，不会出现在命令行里，并会从任何被记录的错误中脱敏。

## 恢复

远端的历史同时也是 vault 的备份。`coffer sync restore [--at <rev|date>]` 把工作树
移到某个版本，并应用它与当前 pointer 之间的差异，于是上周被删掉的一份文档能
回来，而 vault 此后新增的东西不会被丢弃。恢复永远是显式的；一轮收敛绝不会自己
回头去翻历史。

## 界面

| 界面 | 操作 |
| --- | --- |
| CLI | `coffer sync remote set <url> [--branch] [--interval] [--with-credentials] [--credential-ref]` · `coffer sync remote show` · `coffer sync remote clear` · `coffer sync adopt <url>` · `coffer sync now` · `coffer sync status` · `coffer sync restore [--at <rev\|date>]` · `coffer sync rebuild` · `coffer sync confirm` · `coffer sync rollback` |
| CLI（机器） | `coffer sync machines` · `coffer sync machine rename <name>` · `coffer sync machine remove <id>` |
| CLI（密钥） | `coffer sync key export <file>` · `coffer sync key import <file>` |
| HTTP | `GET\|PUT\|DELETE /api/v1/sync/remote` · `POST /api/v1/sync/run` · `POST /api/v1/sync/adopt` · `GET /api/v1/sync/status` · `GET /api/v1/sync/runs` · `POST /api/v1/sync/restore` · `POST /api/v1/sync/confirm` · `POST /api/v1/sync/reject` · `POST /api/v1/sync/rebuild` · `POST /api/v1/sync/rollback` |
| HTTP（机器） | `GET /api/v1/sync/machines` · `PATCH /api/v1/sync/machines/self` · `DELETE /api/v1/sync/machines/{id}` |
| HTTP（密钥） | `GET /api/v1/sync/key/fingerprint` · `POST /api/v1/sync/key/export` · `POST /api/v1/sync/key/import` |
| UI | 一个顶层 **Sync** 页面，三个 tab——**Status**（远端、下一轮、一个运行按钮、主密钥卡片）、**History**（这台机器跑过的每一轮，做成表格：时间、结果、应用到本机的、发布到远端的、落到的提交）与 **Machines**（注册表表格）。冲突与待确认项以横幅形式出现在 Status 上，而不是做成常驻 tab。Status 讲 vault 此刻在做什么，History 讲它一直在做什么——后者是一轮散文式的报告给不出的：失败一次是噪音，从周二起每小时失败一次才是答案。 |

## 验收场景

### Scenario: a changed vault converges and pushes

- **Given** 一个已配置的同步远端，以及一个多出一份新知识文档的 vault，
- **When** 跑一轮收敛，
- **Then** 该文档被提交到工作树，该 commit 被推送到配置的分支，且 pointer
  前进到它。

### Scenario: an unchanged vault makes no commit

- **Given** 一个已配置的远端，其上一轮已经推送完毕，
- **When** 跑一轮，而 vault 与远端都没有任何变化，
- **Then** 不产生 commit，且本轮被记录为成功。

### Scenario: a remote addition lands in the vault

- **Given** 远端持有一个本 vault 没有的 `mcp_server`，
- **When** 跑一轮，
- **Then** 该 server 在本机被注册、它的导入后钩子已经跑过，且 pointer 越过了
  新增它的那个 commit。

### Scenario: a remote deletion is applied

- **Given** 一个两台机器上都有的 skill，在另一台上被删除并推送，
- **When** 在本机跑一轮，
- **Then** 该 skill 的文件与它的注册表行在本机被移除，已无任何剩余 resource
  引用的凭据被释放，且该删除被审计记录。

### Scenario: a local-only document survives a round

- **Given** 一份本 vault 创建、远端从未见过的知识文档，
- **When** 跑一轮，
- **Then** 该文档在本机依然存在，并且现在已发布到远端。

### Scenario: a stale machine does not resurrect a deletion

- **Given** 一台机器，其 pointer 早于另一台机器做出并推送的某次删除，
- **When** 这台机器离线一段时间后跑它的第一轮，
- **Then** 该删除被应用而不是被还原，因为这台机器相对它自己的 base 并没有对
  那条路径做过任何改动。

### Scenario: concurrent edits to different parts of one document merge

- **Given** 两台机器各自向同一份知识文档追加了不同的段落，
- **When** 两边都收敛，
- **Then** 该文档同时包含两个段落，且没有冲突上报。

### Scenario: a real conflict stops the round without touching the vault

- **Given** 两台机器编辑了同一份文档的同一批行，且没有配置内部模型，
- **When** 跑一轮，
- **Then** 本轮中止、vault 未被改动、pointer 未前进，且状态里点名了冲突路径
  以及持有它的工作树。

### Scenario: an agent-resolved conflict is validated and reported

- **Given** 一份冲突的 resource 文档，且配置了内部模型，
- **When** 跑一轮，且 agent 给出的解决结果能解析并通过校验，
- **Then** 该解决结果作为普通的合并结果被应用，且本轮状态把该路径标为由 agent
  解决。

### Scenario: an agent resolution that fails validation is not applied

- **Given** 一份冲突的 resource 文档，其 agent 解决结果残留了冲突标记，
- **When** 跑一轮，
- **Then** 什么都不被应用、本轮以未解决冲突中止，且 vault 未被改动。

### Scenario: the fresher credential ciphertext wins

- **Given** 同一个凭据 ref 在两台机器上都被重新加密过，其中另一台机器的那次
  加密更旧，
- **When** 两者在一轮中相遇，
- **Then** 事后两台机器持有的都是更新的那份密文，与哪个 commit 更新无关。

### Scenario: a new machine takes the union and deletes nothing

- **Given** 一台 id 不在远端注册表里、且有自己 vault 的机器，以及一个持有另一个
  vault 的远端，
- **When** 用户执行 `coffer sync adopt <url>`，
- **Then** 远端持有的一切都被加到本机，机器原本持有的一切都还在，且下一轮把
  两者一并发布。

### Scenario: a returning machine does not resurrect what was deleted while it was away

- **Given** 一台此前收敛过、因重装丢了 pointer 但 vault 文件还在的机器，以及一个
  在这期间被删掉了某个 skill 的远端，
- **When** 那台机器再次加入该远端，
- **Then** 它的 id 在注册表里被认出、它的 base 从它自己的描述符找回、那次删除
  是在本机被应用而不是在远端被撤销，且本轮报告它是以回归机器的身份加入的。

### Scenario: a returning machine with an empty vault does not publish the loss

- **Given** 一台此前收敛过、vault 已被抹掉的机器，重新加入一个持有数百份文档的
  远端，
- **When** 跑一轮，
- **Then** 不会有任何东西被作为删除推送出去，本轮被记录为等待确认并写明它会从
  远端移除多少份文档，且用户可以改为从远端重建这台机器。

### Scenario: a damaged machine rebuilds from the remote instead of publishing its loss

- **Given** 一台 vault 被清空、且这一轮被发布侧熔断挡下的机器，
- **When** 用户以远端重建它，
- **Then** vault 里是远端持有的内容，只有这台机器有过的文档消失，什么都没有被
  推送，挂起的那一轮被清除。

### Scenario: a failed apply holds the path back instead of deleting it

- **Given** 某一轮中有一份 resource 文档在本机无法应用，
- **When** 下一轮导出 vault，
- **Then** 该文档在工作树里依然存在、不会被当作一次删除提交，且本轮会重试它。

### Scenario: an oversized deletion is held for confirmation

- **Given** 一份会删掉超过熔断器允许数量的文档的 diff，
- **When** 跑一轮，
- **Then** 什么都不被应用，本轮被记录为等待确认并附上它将移除的文档列表，
  `coffer sync rebuild` · `coffer sync confirm` 会把它应用掉，而拒绝则让 vault 原封不动。

### Scenario: a round can be rolled back

- **Given** 一轮已完成并应用了 diff 的收敛，
- **When** 用户把它回滚，
- **Then** vault 回到应用前快照所持有的状态，pointer 也一并回退。

### Scenario: a resource is dormant on a machine outside its scope

- **Given** 一个 scope 到某一台机器的 `mcp_server`，
- **When** 它收敛到另一台机器，
- **Then** 它在那里被注册且可见，而 gateway 不向那台机器上的任何会话暴露它的
  任何工具。

### Scenario: the machine registry shows every machine and cannot conflict

- **Given** 两台都收敛过的机器，
- **When** 在任意一台上读机器表，
- **Then** 它列出两台机器及其名字、最后收敛日与密钥指纹，标出本机，且工作树里
  每台机器各有一份描述符、彼此之间没有任何合并冲突。

### Scenario: renaming a machine costs nothing

- **Given** 一台被某个 resource 的 `scope.machines` 引用的机器，
- **When** 用户把它改名，
- **Then** 该 resource 的 scope 未变且依然匹配，因为 scope 引用的是 id，而名字
  住在描述符里。

### Scenario: a machine identity survives reinstalling Coffer

- **Given** 一台机器的 `~/.coffer` 被删除并重装了 Coffer，且其宿主机能提供稳定
  标识符，
- **When** 它再次采纳该远端，
- **Then** 它以同一个机器 id 回来、它的描述符被更新而不是被复制出一份，且
  scope 到它的 resource 重新活跃。

### Scenario: tidy runs only on its owner machine

- **Given** 两台已收敛、都开启了 tidy 的机器，其中一台被指名为 owner，
- **When** tidy 间隔在两台上都到点，
- **Then** owner 上跑了一次，另一台上是空操作，且 vault 里是一份改写后的主题
  文档而不是两份。

### Scenario: a tidy pass and a converge round do not overlap

- **Given** 一次正在进行的 tidy，
- **When** 一轮收敛开始，
- **Then** 该轮会等 tidy 结束之后才去序列化 vault，因此导出的树绝不会是一个
  改写到一半的语料。

### Scenario: an edit outlives a tidy deletion

- **Given** 一篇被 owner 的 tidy 合并掉并删除的笔记，同一篇笔记在另一台机器上
  于收敛之前被编辑过，
- **When** 两者在一轮中相遇，
- **Then** 该笔记连同它的编辑依然存在、删除被丢弃，且本轮不报冲突。

### Scenario: the push credential never reaches the repository

- **Given** 一个配置了推送凭据的远端，
- **When** 某一轮执行推送，
- **Then** 该凭据不出现在仓库的 git config 里、不出现在 git 进程的参数里，
  也不出现在任何被记录的错误文本或审计载荷里。

### Scenario: the master key never enters the repository

- **Given** 一个被配置为携带凭据密文的远端，
- **When** 某一轮执行推送，
- **Then** 树里只有 Fernet 密文、没有任何密钥材料，且一台没有密钥的机器会把
  那些 ref 报为已锁定，而不是解密失败。

### Scenario: restore brings back a document deleted last week

- **Given** 一个远端，其历史里有一个后来被删除并收敛掉的 skill，
- **When** 用户执行 `coffer sync restore --at <删除之前的某个日期>`，
- **Then** 该 skill 重新被注册，而 vault 自那个日期以来新增的一切都没有被动过。

## 不在范围内

- **本地导出与导入。** 随本 spec 一并删除。把一个 bundle 写到目录里、再把一个
  目录读回来，是一次没有 base 的整体覆盖——正是造成 2026-07-10 事故的那个
  操作——它在基于 diff 的应用旁边没有立足之地。它曾服务的需求不靠它也能满足：
  一台新机器跑 `coffer sync adopt`，离线介质就是 U 盘上的一个 `file://` 远端，
  而把副本交给别人就是 `git clone ~/.coffer/sync`。
- **不止一个同步远端。** 一个汇合点，正是「一个 vault」的含义。
- **托管式同步端点。** 那需要对章程再做一次修订。
- **同步对话、审计日志或 MCP 调用记录。** 它们描述的是某台机器上发生了什么；
  合并它们是另一个特性。
- **把两个互不相干的 vault 并成一个。** 首次接触取的是文档的并集；它不会去
  调和两段从未共享过 base 的历史。
- **机器 × agent 成对矩阵。** scope 的两个列表是 `AND` 关系；在一个 resource 上
  表达每台机器用不同 agent，是不支持的。
