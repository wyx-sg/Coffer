# 快速上手——仓库同步

> English: [quickstart.md](./quickstart.md)

让一个 vault 横跨你的多台机器。你把每一台都指向一个你自己拥有的 git 仓库；一个后台
worker 负责让它们收敛。主密钥永不进入那个仓库——你只需带外把它带过去一次。

## 1. 把机器一指向一个你自己的仓库

在任何你喜欢的地方建一个空仓库（GitHub、你自己的服务器、NAS 上的一个裸仓库）。先把
推送 token 放进凭据库，这样远端就能以引用而非值来指认它：

```bash
coffer credentials set sync/github-token ghp_...
coffer sync remote set https://github.com/you/coffer-vault.git \
  --credential-ref sync/github-token \
  --interval 1h \
  --with-credentials
```

`--with-credentials` 才会让 Fernet **密文**随行。不给它，就没有任何凭据材料会到达那个
仓库；无论给不给，主密钥都不会被写进去。

然后手动跑一轮，不用等定时器：

```bash
coffer sync now
```

```
round ok — 214 documents published, nothing to apply
  knowledge 186 · skills 14 · resources 11 · state 3
pointer 9f1c2ab
```

在一个空远端上的第一轮没什么可应用、却什么都要发布。去看看你刚刚发布了什么——全是
文本，就在一个你自己拥有的 git 仓库里：

```bash
git -C ~/.coffer/sync log --stat -1
```

## 2. 从机器二加入

在另一台机器上装好 Coffer，然后：

```bash
coffer sync adopt https://github.com/you/coffer-vault.git \
  --credential-ref sync/github-token
```

加入时会在应用任何东西之前先告诉你**这是哪一种加入**：

```
joining as a NEW machine — this machine's id is not in the registry
  remote holds   214 documents
  this vault has  37 documents, none of them published yet
  nothing will be deleted on either side

joined — 214 applied, 0 failed, 37 to publish next round
```

一台新机器取**并集**：远端持有的一切都被加到这里，这台机器本来就有的一切留下，下一轮
把两边都发布出去。像这样的加入在结构上不可能删除任何东西，因为 base 是 git 的空树，
而从「什么都没有」出发的 diff 只可能包含新增。

如果反过来，这台机器以前收敛过、只是丢了 pointer——重装、`~/.coffer` 被清空、从别处恢复
的磁盘——它会如实说明，并从注册表里它自己的描述符恢复 base：

```
joining as a RETURNING machine — last converged 2026-09-02 at 4a71e0c
  8 documents changed on the remote since
  3 documents changed in this vault since
```

这个区分正是全部意义所在：一台被当成新机器对待的回归机器，会把它离开期间别人删掉的
东西全部重新发布回去。如果它的 vault *也*没了，那一轮会停下来发问，而不是把这份损失
发布出去——见第 7 步。

## 3. 把主密钥带过去（仅当远端携带凭据时）

在机器一上：

```bash
coffer sync key export ~/coffer-master.key
```

通过你信任的渠道把这个文件移过去（密码管理器、安全拷贝、U 盘）——**不要**走同步仓库。
在机器二上：

```bash
coffer sync key import ~/coffer-master.key
```

> 跳过这一步收敛照样工作，但到达这里的凭据会保持**锁定**：它们被报为
> `credentials_locked`，依赖它们的资源不会启动。Machines tab 会直接说明这一点——它替你
> 比对密钥指纹。

## 4. 看着它们收敛

不需要别的了——两台机器上的 worker 都会每隔一个间隔跑一轮。想看现在是什么状况：

```bash
coffer sync status
```

```
remote   https://github.com/you/coffer-vault.git (main), every 1h
machine  Laptop — a3f21c9e4b7d2610 (this machine)
pointer  c04b8e1
last     ok, 2026-09-13 14:02 — 3 applied, 0 failed
next     15:02
pending  none
```

在一台机器上写条知识笔记，等一轮，在另一台上读它。在一台上删掉它，等一轮，另一台上它
也没了——因为这条删除是作为删除进入 diff 的。一台仅仅*没有*某个文档的机器不会删除任何
东西，这正是为什么一台关了一周的笔记本回来之后是吸收期间发生的事，而不是把它们撤销。

未发生变化的 vault 根本不产生提交。序列化是确定性的，因此无话可说的一轮什么也不产出，
仓库的历史记录的是变化而不是心跳。

## 5. 把某样东西 scope 到一台机器上

有些东西只属于一台机器——一个工作用的 MCP 服务器、一个需要笔记本上没有的二进制的
skill。先列出你的机器拿到 id：

```bash
coffer sync machines
```

```
ID                NAME      OS      LAST CONVERGED  KEY
a3f21c9e4b7d2610  Laptop    darwin  2026-09-13      4f2a91c0b8de  (this machine)
b7c40d29e1f58a33  Desktop   darwin  2026-09-13      4f2a91c0b8de
```

然后按 id 设置 scope：

```bash
coffer scope set mcp_server:work-jira --machines b7c40d29e1f58a33
```

这个资源仍然会收敛到两台机器——它在哪里都被注册、都看得见——只是它不在笔记本上激活，
gateway 不会把它的任何工具暴露给那台机器上的任何会话。把两条轴组合起来，就能表达
「只要台式机上的 Claude Code」：

```bash
coffer scope set mcp_server:work-jira \
  --machines b7c40d29e1f58a33 --agents claude-code
```

想什么时候重命名机器都行——scope 引用的是 id，标签毫无代价：

```bash
coffer sync machine rename "Work desktop"
```

## 6. 当一次冲突让一轮停下

在两台机器各自收敛之前，改了同一个文档的同几行，git 就无法决断。配置了内部模型时，
一趟有界的处理会在工作树里尝试合并，并报告它碰过的每一条路径。否则那一轮会停下来，
完全不碰你的 vault：

```
round conflict — nothing applied, pointer unchanged
  knowledge/projects/coffer.md
resolve in ~/.coffer/sync with your own git tools, then run `coffer sync now`
```

你的 vault 纹丝不动、pointer 也没有前进，所以在你做决定期间什么都不会丢。工作树就是一个普通
的 git 仓库：

```bash
cd ~/.coffer/sync
git status
$EDITOR knowledge/projects/coffer.md   # resolve the markers
git add -A && git commit
coffer sync now
```

一次冲突会同时挡住两台机器的收敛，直到它被解决。这是刻意的：两台机器悄悄地对同一个
文档各执一词，比两台机器一起等着更糟。

## 7. 当一轮在删除之前发问

会移除异常比例文档的一轮不会继续。它记下自己打算做什么，然后等你：

```
round awaiting confirmation — PUBLISH side
  this round would delete 186 documents from the remote
  knowledge 186 of 186 · skills 14 of 14
  this vault looks empty; the remote is not
```

两个方向都有守卫。**应用**侧保护这个 vault 不被出了问题的远端伤到；**发布**侧保护其他机器
不被*这一台*伤到——否则一次重装、一次失败的恢复或者一个手滑的 `rm -rf`，会把这份损失
当成普通删除发布出去，把整队机器一起带走。

```bash
coffer sync confirm            # yes, apply it
coffer sync confirm --reject   # no, leave everything as it is
coffer sync confirm --rebuild  # rebuild this machine from the remote instead
```

当受损的正是这台机器时，`--rebuild` 就是答案：采用远端的状态、丢掉仅存在于本地的东西，
而不是把一次意外删除发布出去。

如果某一轮确实应用了你不想要的东西，它是可逆的——每一轮都会给应用发生前一刻 vault 的状态
打上 tag：

```bash
coffer sync rollback
```

## 8. 把上周删掉的东西找回来

远端的历史同时也是你的备份。恢复会把工作树移到某个修订，并应用它与你当前所在之处的
差异，因此 vault 此后新增的任何东西都不会被丢掉：

```bash
coffer sync restore --at 2026-09-05
coffer sync restore --at 4a71e0c
```

一个日期会被解析成该时间点或之前的最后一次提交。恢复永远是显式的——一轮绝不会自己
伸手回到历史里去。

## 什么永远不随行

日志、`coffer.db`、`daemon-config.json`、PID 与端口文件、聊天历史、会话、审计日志、
MCP 调用记录——以及主密钥，它在任何设置下都不会被写进那个仓库。

会话与审计日志是被刻意排除的：它们记录的是*在某台机器上*发生了什么，而把两台机器的
活动合并起来，会是一个形状完全不同的另一个特性。

## REST / Web UI

上面的一切同样是一个顶级 **Sync** 页，带三个 tab —— **Status**（远端、下次轮次、
一个运行按钮，以及主密钥卡片）、**History**（这台机器跑过的每一轮，做成表格：什么时候
跑的、怎么结束的、应用到本机什么、发布到远端什么、落到哪个提交——展开一行还能看到由
agent 合并的路径、本机应用不了的路径，以及任何失败）与 **Machines**（注册表表格，标出
本机，并用文字说明任何密钥指纹不匹配）。冲突与待确认项在 Status 上呈现为横幅。

在 HTTP 上，同样这些操作位于 `/api/v1/sync/*` —— `run`、`adopt`、`status`、`runs`、
`restore`、`confirm`、`rollback`、`machines` 家族与密钥家族。密钥相关的两条路由传的是密钥
**材料**，不是路径：`POST /sync/key/export` 收 `{}`，返回 `{"material": "…"}`；
`POST /sync/key/import` 收 `{"material": "…"}`。上面那两条 CLI 命令仍然写文件、读文件
——只是文件 I/O 由 CLI 自己做，守护进程从不打开任何由调用方指定的路径。在 Web UI 里，
导出会落成一次浏览器下载，导入则从 `<input type="file">` 读取。
