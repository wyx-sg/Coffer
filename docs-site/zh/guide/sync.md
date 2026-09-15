# 同步

同一个项目,你在笔记本上做一阵,又在台式机上做一阵,两台机器都会产出保险库状态 —— 知识笔记、技能、MCP 注册、agent 配置、凭证。**同步**让它们成为同一个保险库:把每一台都与一个**你自己拥有的** git 仓库收敛。一个后台 worker 把这个保险库当前的内容提交下来,交给 git 与远端持有的内容做三方合并,再把合并的结果应用回来 —— 删除也一并算数。

那个远端是**汇合点,不是事实来源**。每台机器的保险库都完整且权威,因此你可以删掉那个仓库,再从任意一台机器把它重建出来,什么都不会丢。加密主密钥绝不会被写进去。

## 把第一台机器指向一个你自己的仓库

在任何你喜欢的地方建一个空仓库 —— GitHub、你自己的服务器、NAS 上的裸仓库,甚至 U 盘上的一个 `file://` 路径。先把推送 token 放进凭证库,这样远端就以引用而非值来指认它:

```bash
coffer credentials set sync/github-token
coffer sync remote set https://github.com/you/coffer-vault.git \
  --credential-ref sync/github-token \
  --interval 3600 \
  --with-credentials
```

| 选项 | 含义 |
| --- | --- |
| `--branch` | 收敛所用的分支。默认 `main`。 |
| `--interval` | 自动轮次之间相隔的**秒数**。默认 `3600`。 |
| `--with-credentials` | 让凭证**密文**随行。默认关闭。 |
| `--credential-ref` | 推送凭证在凭证库里的名字。 |

远端在被接受之前会先被探测一次,所以打错的 URL、推不上去的 token 会当场失败,而不是一小时后才发作。`coffer sync remote show` 打印当前配置;`coffer sync remote clear` 忘掉这个远端,保险库原样不动。

然后手动跑一轮,不用等定时器:

```bash
coffer sync now
```

```
ok
  applied here: nothing
  published: added 214
  commit: 9f1c2ab4c0d1
```

对着一个空远端的第一轮,没什么可应用、却什么都要发布。你刚刚发布出去的东西,是一个你自己拥有的仓库里的纯文本 —— 去读它:

```bash
git -C ~/.coffer/sync log --stat -1
```

## 从第二台机器加入

在那台机器上装好 Coffer,再把它指向同一个仓库:

```bash
coffer sync adopt https://github.com/you/coffer-vault.git
```

加入会在应用任何东西之前,先报告**这是哪一种加入** —— 两种加入的处理方式正好相反:

- **新机器取并集。** 它的 id 不在远端的机器注册表里,于是这一轮的 base 是 git 的空树 —— 从"什么都没有"出发的 diff 只可能包含新增。远端持有的一切被加到这里,这台机器原本就有的一切留下,下一轮把两边都发布出去。删除在结构上不可能发生,而不只是被避开了。
- **回归机器找回自己的 base。** 它的 id **在**注册表里,说明它以前收敛过,只是丢了本地的 pointer —— 重装、`~/.coffer` 被清空、从别处恢复的磁盘。它的描述符记着它上次到达的那个提交,那个提交成为 base,这一轮就按一台普通的落后机器来跑:远端的删除被应用,这台机器的编辑被保留,什么都不会复活。

这个区分正是全部意义所在。一台被当成新机器对待的回归机器,会把它离开期间别人删掉的东西统统重新发布回去 —— 所有删除一次性被撤销,而且不会报任何冲突,因为并集根本没有可供分歧的 base。

如果一台回归机器的保险库*也*没了,那一轮会停下来发问,而不是把这份损失发布出去,见下文"当一轮在删除之前发问"。而如果它记录的 base 已经不在远端的历史里,就连一个安全的默认动作都没有,于是那一轮会拒绝执行,直到你做出选择:`coffer sync adopt --keep-local` 把这个保险库的文档当作新增发布出去,`coffer sync rebuild` 则改为采用远端的状态。

## 把主密钥带过去

只有当远端携带凭证时才需要这一步。在第一台机器上:

```bash
coffer sync key export ~/coffer-master.key
```

通过你信任的渠道把这个文件搬过去 —— 密码管理器、安全拷贝、U 盘 —— **不要**走同步仓库。在第二台机器上:

```bash
coffer sync key import ~/coffer-master.key
coffer sync key fingerprint        # 想的话也可以两台机器肉眼比对一下
```

::: warning 没有密钥的凭证会保持锁定
跳过这一步,收敛照样工作,但到达这里的凭证会被报为 `credentials_locked`,依赖它们的资源不会启动。Machines tab 会替你比对密钥指纹,并用文字直接说出来,不必你自己去察觉。
:::

## 一轮到底做了什么

一轮就是:把这个保险库序列化进工作树并提交,拉取远端并把它合并进这个提交,把合并带进来的差异应用回来,推送。**先**提交本地状态、**再**合并,正是为了给 git 它需要的三个输入,于是同一个文件的不同片段能干净地合并,而应用回来的差异恰好就是远端贡献的那部分。

由此得出两条性质,也是最值得记住的两条:

- **一次删除意味着真的有人删了东西。** 只有当删除以删除的形态出现在 diff 里时才会被应用,而它之所以能出现在那里,是因为某台机器相对共同 base 真的移除了那个文档。仅仅*没有*某个文档的机器什么都没断言 —— 这正是为什么一台关了一周的笔记本回来之后是吸收期间发生的事,而不是把它们撤销。
- **没有变化的保险库根本不产生提交。** 序列化是确定性的,因此无话可说的一轮什么也不产出。仓库的历史记录的是变化,不是心跳。

看看眼下是什么状况:

```bash
coffer sync status
```

```
remote: https://github.com/you/coffer-vault.git  branch main
  every 3600s · credentials included · enabled
  push credential: sync/github-token
  working tree: /Users/you/.coffer/sync
this machine: a3f21c9e4b7d2610
ok
  applied here: added 3
  published: nothing
  commit: c04b8e1f2a33
```

`status` 回答的是这个保险库此刻在做什么;`history` 回答的是它一直以来在做什么 —— 每轮一行,最新在前:

```bash
coffer sync history --limit 20
```

```
2026-09-13T15:02:11  ok  applied: added 3  published: nothing  c04b8e1f2a33
2026-09-13T14:02:09  no_change  applied: nothing  published: nothing  —
```

什么都没改的轮次和别的轮次一样会被列出来。它们才是大多数,也正是它们让一段**空白**变得可见:没有它们,一个周二就停止收敛的保险库,看起来和一个一直无事可做的保险库毫无分别。

某条路径应用失败会被报告,并进入下一轮重试,而不会让这一轮中止。某条路径如果在这台机器上**根本**应用不了 —— 比如某个 agent 的 `config_dir` 在这里并不存在 —— 会被记为*在此机器上不适用*:它被保留下来,不重试,也不计为错误。

## 一台机器留给自己的东西

有两样东西是刻意不动地方的,而它们是同一个道理:一台机器*拿保险库做了什么*,属于那台机器自己。

**生效范围不同步。** 一个资源的开关和它的 agent scope —— 网页界面上那个生效范围按钮,按钮上写着这个资源当下触达到哪里,点开的面板里是「已禁用 / 所有 agent / 只限选中的」;以及命令行上的 `coffer resource enable|disable` / `coffer scope set` —— 是在它生效的那台机器上设定的。每台机器各设各的,而一轮收敛既不读也不写它们中的任何一个。所以"这个工作用的 MCP 服务器属于台式机,不属于笔记本",是在笔记本上说的:

```bash
coffer resource disable mcp_server:work-jira      # on the laptop
coffer scope set mcp_server:work-jira --agents claude-code
```

服务器本身仍然会收敛到两台机器 —— 它在哪里都被注册、都看得见,对它配置的修改也会抵达两边 —— 只是它不在笔记本上**激活**,gateway 不会把它的任何工具暴露给那台机器上的任何会话。台式机不受影响,而且会一直不受影响,因为生效范围的任何部分都不会被发布出去。

有一处代价值得知道:一个资源第一次抵达某台机器时,起点是那台机器的默认生效范围,而不是它在别处的生效范围。这是一个你在页面上看得见、一次点击就能改的状态,而且它是"问一声"而不是"替你假定"的那个方向。

**渠道完全不同步。** 渠道是一条绑定在单台机器上的入站面 —— 它的端口、它的隧道、平台被告知要去回调的那个 webhook URL —— 所以一条渠道抵达第二台机器,往好了说什么也不做,往坏了说会把同一段对话应答两遍。需要渠道的机器,各自配置各自的。

## 保险库里都有哪些机器

```bash
coffer sync machine list
```

```
Name                   Id        System  Last converged  Key  Agents
Laptop  (this machine) a3f21c9e  darwin  2026-09-13      ✓    claude-code, codex
Desktop                b7c40d29  darwin  2026-09-13      ✓    claude-code
```

想什么时候改名都行 —— 保险库里没有任何东西引用这个标签,也没有任何东西引用那个 id。退役一台机器只是移除它的描述文件,不改写别的任何东西:

```bash
coffer sync machine rename "Work desktop"
coffer sync machine remove b7c40d29e1f58a33
```

机器 id 是从宿主推导出来的 —— macOS 上取 `IOPlatformUUID`,Linux 上取 `/etc/machine-id` —— 因此它能熬过重装 Coffer,一台机器不会变成幽灵回来。两者都读不到时,会退化成一个生成后缓存在 `~/.coffer` 下的 id;这一种**不能**熬过删除那个目录,`status` 和 Machines tab 都会把这件事说出来。

## 当一次冲突让一轮停下

在两台机器各自收敛之前,改了同一个文档的同几行,git 就无法决断。配置了内部模型时,一趟有界的处理会**只在工作树里**尝试合并,并报告它碰过的每一条路径 —— 对你自己笔记的机器合并,绝不会悄无声息。否则那一轮会停下来,完全不碰你的保险库:

```
conflict
  applied here: nothing
  published: nothing
  conflict: knowledge/projects/coffer.md
  resolve them with your own git tools, then run 'coffer sync now'
```

保险库纹丝不动,pointer 也没有前进,所以在你做决定的这段时间里什么都不会丢。那个工作树就是一个普通的 git 仓库:

```bash
cd ~/.coffer/sync
git status
$EDITOR knowledge/projects/coffer.md   # 解掉冲突标记
git add -A && git commit
coffer sync now
```

一次冲突会同时挡住两台机器的收敛,直到它被解决。这是刻意的:两台机器悄悄地对同一个文档各执一词,比两台机器一起等着更糟。

凭证密文根本不会走到文本合并那一步。Fernet token 的加密时间是明文携带的,因此同一个引用的两份密文不需要密钥也能排出先后,较新的那一份胜出。

## 当一轮在删除之前发问

一轮如果其 diff 会删掉异常比例的文档 —— 超过某个状态区的 20%,或者干脆达到 20 个 —— 就不会继续。它记下自己打算做什么,然后等你:

```
awaiting_confirmation
  held: this round would delete the following from the remote.
  If this vault was just reinstalled or restored, do NOT confirm.
    knowledge: 186 of 186
    - knowledge/global/notes/coffer.md
    …
```

两个方向都有守卫。**应用**侧保护这个保险库不被出了问题的远端伤到;**发布**侧保护其他机器不被*这一台*伤到 —— 否则一次重装、一次失败的恢复,或者一个手滑的 `rm -rf`,就会把这份损失当成普通删除发布出去,把整队机器一起带走。

```bash
coffer sync confirm    # 是,让它跑完
coffer sync reject     # 不 —— 丢掉这一轮,保险库从未被碰过
coffer sync rebuild    # 受损的正是这台机器:采用远端的状态
```

`rebuild` 是第三个答案,也是当坏掉的正是本机保险库时唯一正确的那个:确认会把损失扩散到其他每一台机器,拒绝则会让同一轮被永远拒下去。它用远端的状态替换这个保险库,丢掉仅本机持有的文档,并且什么也不推送。它执行前会先问一句,`--yes` 可以跳过这个确认。

如果某一轮确实应用了你不想要的东西,它是可逆的。每一轮都会给应用发生前一刻保险库的状态打上 tag,最近十个快照会被保留:

```bash
coffer sync rollback
```

## 把上周删掉的东西找回来

远端的历史同时也是你的备份。恢复会把工作树移到某个修订,并应用它与你当前所在之处的差异,因此保险库此后新增的任何东西都不会被丢掉:

```bash
coffer sync restore --at 2026-09-05
coffer sync restore --at 4a71e0c
```

`--at` 接受一个 sha、一个 ref,或者一个 `YYYY-MM-DD` 日期 —— 日期会被解析成该时间点或之前的最后一次提交。恢复永远是显式的 —— 一轮绝不会自己伸手回到历史里去。

## 哪些会随行

工作树是一个可读的纯文本目录,一个关注点一个状态区:

```
manifest.json  knowledge/  skills/  resources/  state/  credentials/  machines/
```

- **知识** —— `~/.coffer/knowledge/` 下的 Markdown 文件。
- **技能** —— `~/.coffer/skills/` 下的技能主库。
- **配置资源** —— `mcp_server`、`agent`、`skill`、`knowledge`、`memory` 与 `provider` 的定义,每个序列化成一份确定性 YAML。一项资源**是什么**会走:它的名字、描述与配置。它**触达到哪里**不走 —— 见[一台机器留给自己的东西](#一台机器留给自己的东西)。`channel` 根本不会被序列化。`$HOME` 之下的路径以 `~` 哨兵存储,并在每台机器上按各自的 home 展开。
- **共享状态** —— 那些属于保险库而非某一台机器的区域:MCP 能力偏好、内部引擎设置,以及 agent 插件清单。
- **凭证** —— **仅以 Fernet 密文形式**,且仅在带 `--with-credentials` 时。
- **机器描述符** —— 每台机器一份,落在 `machines/<id>.yaml`。每台机器只写自己那一份,因此它们之间永远不可能冲突;注册表就是这些文件当前的内容。

插件清单是**一份清单,不是一个安装器**。它记录每台机器上每个 agent 装了哪些插件,落在 `state/agent-plugins/<agent>.yaml`,并且不往任何 agent 的配置里写任何东西。到了新机器上,打开这个文件,用各家自己的 CLI 装上。

**机器本地,永不写入仓库:**日志、可重建的 `coffer.db`、`daemon-config.json`、PID 文件、端口分配、聊天历史、会话、审计日志、MCP 调用记录 —— 以及主密钥,在任何设置下都不写。

会话与审计日志是被刻意排除的:它们记录的是*在某台机器上*发生了什么,而把两台机器的活动合并起来,会是一个形状完全不同的另一个特性。它们在 [`/activity`](/zh/guide/web-ui) 里。

## Sync 页与 REST

上面的一切同样是应用里的一个顶级 **Sync** 页,位于 `/sync`,带三个 tab:

- **Status** —— 远端的配置、一个"立即收敛"按钮,以及主密钥卡片(导出落成一次浏览器下载,导入从文件选择器读回)。冲突或被扣下的轮次以横幅形式出现在这里、出现在最上方,因为这两者都是你必须去处理的状态,而不是供你翻阅的记录。
- **History** —— 这台机器跑过的每一轮,做成一张可搜索、可筛选的表:什么时候结束、怎么结束的、往本机应用了什么、往远端发布了什么、落在哪个提交上。"应用"与"发布"是两列而不是一列,因为这正是双向收敛的全部要义:一台每轮都在发布、从不应用的机器,是在从某处出发;一台每轮都在应用、从不发布的机器,是在往某处去。展开一行,还能看到由 agent 合并的路径、本机应用不了的路径、任何被锁住的凭证引用,以及错误。
- **Machines** —— 注册表,标出本机,把每台机器的密钥指纹以"匹配"或"不匹配"用文字讲清楚,并列出在那台机器上注册的 agent。

在 HTTP 上,同样这些操作位于 `/api/v1/sync/*` —— `remote`、`run`、`adopt`、`status`、`runs`、`restore`、`confirm`、`reject`、`rebuild`、`rollback`、`machines` 家族与密钥家族。密钥相关的两条路由传的是密钥**材料**,绝不是路径:文件 I/O 由 CLI 自己做,守护进程从不打开任何由调用方指定的路径。

[凭证 →](/zh/guide/credentials)
