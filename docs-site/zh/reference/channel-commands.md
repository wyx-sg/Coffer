---
title: 渠道命令
description: 十个渠道命令、各命令在直接聊天、线程和群组中的行为、设置如何跟着聊天走、/stop 后暂停的消息，以及命令菜单和选择卡片。
---

# 渠道命令 {#channel-commands}

有十个词是 Coffer 的命令。你输入的其他所有内容，包括别的以 `/` 开头的文字，都是发给智能体的消息。

下表列出十个词。每个命令的读法、可用位置和卡片见下文。如何配对并开始聊天，请看[消息渠道](/zh/guides/channels)。

| 命令 | 作用 |
| --- | --- |
| `/new [agent]` | 用这个聊天的设置开始一个新对话。带上智能体名则切换到那个智能体。 |
| `/stop` | 中断正在运行的轮次，并暂停队列。回复会写明停的是哪个对话——「⏹ Stopping “Fix login”…」；在能编辑消息的平台上它会被原地改成「⏹ Stopped “Fix login” after 12s · 3 tools.」，不能编辑的平台则另发这一行；排在它后面的消息会被暂停，并带 **Continue** 和 **Discard** 两个按钮（见[/stop 后暂停的消息](#messages-on-hold-after-stop)）。没有在运行的轮次时回复「Nothing is running.」。正在等你回答的问题会被取消，它的卡片显示「⏹ Stopped」。 |
| `/status` | 这个聊天正在运行什么，以卡片显示，只带对它有用的按钮。 |
| `/model [name]` | 查看或设置模型。 |
| `/dir [path\|name]` | 查看或切换工作目录，切换会开一个新对话。 |
| `/resume [n]` | 重新打开这个聊天之前的一个对话。 |
| `/thread [title]` | 在私聊中，在单独的话题里打开一个并行对话。 |
| `/close` | 在并行对话里发，关闭它（见[关闭并行对话](#closing-a-parallel-thread)）。 |
| `/del` | 仅所有者可用。撤回机器人的回复：引用机器人的某条消息并发送 `/del`，撤回那条消息所属的整个回复；不引用直接发送，则撤回机器人在这个聊天（或话题）里最近的一条回复。 |
| `/help` | 列出命令，一行一个并写明作用（群组里只有四个群命令），不带按钮。 |

在群组里只有 `/new`、`/stop`、`/help` 和 `/del` 可用；其余六个只能在私聊里用（见[各命令在哪里可用](#where-each-command-works)）。Telegram 的 start 链接会发送 `/start`，它的回答和 `/help` 一样。`/new` 和 `/stop` 即使在轮次运行时也会立即生效。命令会先放行所有还在停顿等待中的消息，让它们在命令之前运行；`/stop` 则会丢弃它们。

## 命令的读法 {#how-the-commands-read}

所有带设置的命令都遵循同一套语法：

- **不带参数**：显示当前生效的值；在支持按钮的平台上还会给出一张卡片来修改：`/model`、`/dir`、`/resume`。
- **带参数就是设置**：`/model opus`、`/dir coffer`、`/resume 2`。
- **`default` 表示重置**：`/model default`、`/dir default`。

名字都是你看得到的名字，从不是内部 id。智能体可以用它的显示名，或小写加连字符的名字（`claude-code`、`codex`）；大小写、`-`、`_` 和空格都不影响。模型可以用它的 id，或它按钮上显示的名字。

## 各命令在哪里可用 {#where-each-command-works}

`/new`、`/stop`、`/help` 和 `/del` 控制的是群自己的对话和它的回复，所以在群里可用。`/model`、`/dir`、`/status`、`/resume`、`/thread` 和 `/close` 配置或查看的是你和机器人自己的聊天，所以只能在私聊里用。

| 命令 | 私聊 | 并行话题 | 群组话题 | 群主聊天 |
| --- | --- | --- | --- | --- |
| `/new [agent]` | ✓ | ✓ | ✓ | SeaTalk：设置群组的默认智能体；不带参数则显示它 |
| `/stop` | ✓ | ✓ | ✓ | SeaTalk：停止群组里正在运行的所有轮次 |
| `/status` | ✓，并列出并行话题 | ✓ | 仅限私聊 | 仅限私聊 |
| `/model` | ✓ | ✓ | 仅限私聊 | 仅限私聊 |
| `/dir` | ✓ | ✓ | 仅限私聊 | 仅限私聊 |
| `/resume` | ✓ | ✓ | 仅限私聊 | 仅限私聊 |
| `/thread` | ✓ | ✓ | 仅限私聊 | 仅限私聊 |
| `/close` | 拒绝：不是并行对话 | ✓ | 仅限私聊 | 仅限私聊 |
| `/del` | ✓ | ✓ | ✓ | ✓ |
| `/help` | ✓，列出全部十个 | ✓ | ✓，列出四个群命令 | ✓，列出四个群命令 |

所有者在群里发了仅限私聊的命令时，在平台支持私下发送的情况下，只会私下回给发送者一行「This command works in a private chat with me.」，什么都不做：不交给智能体，也不设置任何东西。`/help`、`/del`、这行提示和任何「Did you mean」纠正是群里仅有的私密回答；`/new` 和 `/stop` 会改变全群共享的东西，所以保持公开可见。

## 用 /del 撤回回复 {#withdrawing-a-reply-with-del}

`/del` 只有所有者能用；其他人发的 `/del` 什么都不会发生。引用机器人的某条消息并发送 `/del`，那条消息所属的整个回复都会被撤回，包括长回复被拆成的每一段。不引用直接发送，`/del` 撤回机器人在该聊天里最近的一条回复；在话题里发送时则是该话题里最近的一条。私聊和群组里都能用。

`/del` 这条消息本身会在平台允许的地方被删掉：在 Telegram 上要求机器人在该聊天里有删除消息的权限，否则它会留着。回复怎么被撤回、能撤回多久，各平台不同，见[撤回回复](/zh/guides/channels#withdrawing-a-reply)。在群组里，每条回复还带一个 🗑 按钮，对所有者的效果相同。

## 其他斜杠文字交给智能体 {#other-slash-text-goes-to-the-agent}

只有上面十个词会被从对话里拿出来。`/compact`、`/review` 这样的技能，或者以路径开头的消息，比如 `/Users/me/app crashes on start`，都和其他消息一样送到智能体那里，所以智能体自己的斜杠命令在手机上照样能用。

和某个命令只差一点的词，比如 `/stpo`、`/stat`、`/threads`，会得到一行 `Unknown command /stpo. Did you mean /stop? Send /help for all commands.` 这样的回答，什么都不运行。短命令（四个字母及以下）容许错一个字母，长命令容许错两个；相邻两个字母对调算错一个。

## 设置跟着聊天走 {#settings-stick-to-the-chat}

每个聊天，以及其中的每个话题，都记住三项设置：智能体、模型和工作目录。在那里打开的每个新对话，无论是通过 `/new`、`/dir`，还是因为旧对话被删了，都从这些设置开始。

所以 `/new` 可以放心常用：它清掉的是上下文，不是你的选择。聊天里没设置的项会依次回退到所在群组的默认值（在群组话题里），再到消息渠道的默认智能体和配置。

- `/new <agent>` 切换智能体并记住它。为上一个智能体选的模型不会跟过去，因为一个智能体的模型对另一个毫无意义；目录则会跟过去。
- 已有的对话不能更换智能体或目录，因为智能体会话和这两者绑定，所以切换任意一个都会开新对话。旧对话随时可以用 `/resume` 找回。
- 模型每个轮次都会重新读取，所以 `/model` 对同一对话的下一个轮次就生效。

## 模型 {#model}

- `/model <name>` 设置模型。智能体目录里没有的名字会原样传给智能体的 CLI，所以你可以用选择器里没显示的模型；智能体跑不了的名字，会在下一个轮次以 CLI 自己的报错返回。
- `/model` 后面的任何词都是模型名，`high`、`max` 也不例外；唯一保留的词是 `default`。`/model default` 清除模型，回到智能体自己的默认值。Coffer 没有推理强度设置。
- 不带参数的 `/model` 显示当前生效的模型。在支持按钮的平台上，它是一张卡片：点一个模型即可；卡片第一项是 **Default**（没设模型时打勾），点它等于 `/model default`。回答只有一行：「Model: Claude Sonnet 5.5 — from your next message」。

## 工作目录 {#working-directory}

对话通常在 Coffer 管理的工作目录 `~/.coffer/content/workspace` 里运行。`/dir` 可以把聊天移到另一个目录，但只能是消息渠道允许的目录。之所以有这份允许列表，是因为任何拿到你手机的人，或者一次手滑，都不应该能让一个拥有完整权限的智能体指向你机器上任意一个文件夹；这些地方由你事先在电脑前决定。

两者都在消息渠道的**设置**标签页**工作目录**下。一个**目录**列表列出 `/dir` 可以切换进去的文件夹：用**添加目录…**添加，用每行的 ✕ 移除。每行都有**设为默认**；默认的那行标着「默认」并带**取消默认**，新对话从它开始。没有默认时新对话从 Coffer 工作区开始，它显示在列表顶部，标着「默认 · Coffer 工作区」。一个都不允许时，`/dir` 关闭。

路径必须是绝对路径；相对路径会被拒绝，什么都不保存。每个允许的目录也允许它下面的子目录。

- `/dir <path>` 接受一个允许的路径或它下面的路径；`/dir <name>` 接受某个允许路径的最后一级目录名（`/dir coffer`）。目录必须存在。
- 切换会在那里开一个新对话，并为这个聊天记住该目录。
- `/dir default` 回到消息渠道的默认目录。
- 不带参数的 `/dir` 显示当前生效的目录，并以一张 **Working directory** 卡片列出允许的目录，每个显示路径（家目录下的写成 `~/…`）；默认目录不在其中时还有一个 **Default**。卡片上写着「A new directory starts a new conversation.」。切换成功会回复「📁 Now in `<path>` — started a fresh conversation.」。
- 列表外的目录会被拒绝，并列出允许的目录。没有任何允许目录的消息渠道会回复如何添加。

## 恢复之前的对话 {#resume-an-earlier-conversation}

一个聊天打开过的每个对话都会为这个聊天记住。`/resume` 按从新到旧列出最多 100 个，每页四个，用 **← Prev** 和 **Next →** 翻页，编号跨页连续，每个写成「1 · title — Agent · 2h ago」，配编号按钮，当前生效的那个打勾。`/resume 2` 或点一下卡片，会让那个对话重新成为这个聊天的活动对话（「↩️ Resumed “title” with Codex.」），你的下一条消息就接着它。

只提供这个聊天自己打开过的对话，从不包括来自网页或其他聊天的对话，之后被删掉的对话也不会列出。

## 关闭并行对话 {#closing-a-parallel-thread}

[并行对话](/zh/guides/channels#parallel-conversations)会一直开着，直到被关闭。在它里面发 `/close`，会回答「🔒 Closed 🧵#2 Task. Send /thread in the chat to open a new one.」。这个话题的对话仍留在对话页面上，历史都在，它的编号也不会再分给别的话题。`/close` 不会替你停掉任何东西：那里有轮次在运行时，它回答「A turn is running here — send /stop first, then /close.」；有消息在排队或暂停时，它请你先让它们运行或丢弃。在私聊本身，或在一个不是 `/thread` 打开的话题回复里发，它回答「Use /close inside a parallel thread.」。

24 小时没人用的并行对话会自动关闭：这一整天里没有轮次在运行、没有排队或暂停的消息，也没有轮次开始或结束。关闭时不会发任何消息。

私聊里的 `/status` 只列出并计数还开着的话题。在已关闭的话题里发消息，什么都不运行，也绝不会并入私聊自己的对话；那个话题里会回答「🔒 This thread is closed. Send /resume here to reopen it, or /thread in the chat to open a new one.」。`/status`、`/help`、`/stop`、`/del`、`/close`、`/thread` 和 `/resume` 在那里照常可用，`/status` 的状态显示 **Closed**；`/new`、`/model` 和 `/dir` 得到同样的提示。在已关闭的话题里发 `/resume`，会列出它的对话且都不打勾；恢复其中一个就会重新打开这个话题：回答里多一句「🔓 This thread is open again.」，你在那里的下一条消息接着那个对话。

## 状态、帮助和 /new 卡片 {#status-and-help-cards}

`/status` 用文字而不是 id 回答，标题是 **Status**：对话的标题（或它的 `🧵#N` 标记）；一行写着智能体、模型和目录；然后是 **Running**、**Running · 2 waiting**、**⏸ 2 on hold** 或 **Idle**。在私聊里，它还在一行里列出还开着的并行话题，每个标明是在运行、有消息在等、有消息暂停，还是空闲。在支持按钮的平台上它是一张卡片，只带对卡片内容有用的按钮：轮次运行时有 **Stop**，有暂停的消息时有 **Continue** 和 **Discard**，然后是 **Model** 和 **Dir**。

`/help` 是一份用来看的清单，不带按钮。私聊里是：

```
Commands
/new [agent] — Start a fresh conversation, optionally on another agent
/stop — Stop what’s running
/status — What’s running, and the agent, model and directory in use
/model [name] — Switch the model
/dir [path|name] — Switch the working directory
/resume [n] — Go back to an earlier conversation
/thread [title] — Open a parallel conversation beside this chat
/close — Close this parallel thread
/del — Withdraw my latest reply (reply to one of mine to pick it)
/help — This list of commands

Anything else goes to the agent as a message.
```

群组里只列 `/new`、`/stop`、`/del` 和 `/help`，并加一句「The other commands work in a private chat with me.」。对没有命令菜单的平台（SeaTalk），发 `/help` 就能看到机器人接受什么；在 Telegram 上清单里的命令也可以直接点。

`/new` 回复一行「🆕 New conversation · Codex · Default model · ~/src/coffer」，在支持按钮的平台上还带 **Agent**、**Model** 和 **Dir** 按钮（群组里只有 **Agent** 按钮）。**Agent** 列出这个消息渠道可以驱动的智能体；点一个就在它上面开始新对话，和 `/new <agent>` 一样。

点命令按钮的效果和在那个聊天里输入对应命令完全一样。

## /stop 后暂停的消息 {#messages-on-hold-after-stop}

轮次运行时你发的消息会排队等着。`/stop` 停下轮次的同时会暂停这个队列，免得你排着的消息马上冲进刚停下的对话。停止那一行会写明暂停了几条——「⏸ 2 queued messages are on hold.」——并带两个按钮：

- **Continue** 按你发送的顺序把它们跑完（「▶ Continuing 2 queued messages.」）。
- **Discard** 把它们丢掉（「🗑 Discarded 2 queued messages.」），之后你发的消息照常单独运行。

再发任何一条消息也会继续它们，排在新消息前面。能编辑「Stopping…」那条消息的平台（Telegram）上，按钮就在那条消息上；其他平台（SeaTalk）上，暂停的那一行作为单独的卡片跟在回复后面。暂停期间 `/status` 也显示 **⏸ 2 on hold** 和同样两个按钮。已经继续或丢掉之后再点，会回复「Nothing is on hold any more.」。

## SeaTalk 上的群组默认值 {#group-defaults-on-seatalk}

在 SeaTalk 上，群主聊天里的每次 @ 提及都会开一个新话题，所以在那里发的设置只会配置一个没人再继续的话题。因此，群在主聊天里能发的两个命令配置的是整个群组：

- `@bot /new <agent>` 设置群组的默认智能体，回答里会写「default for new threads in this group」。群里每个新话题都从它开始；在话题内部，话题自己的设置仍然优先。
- `@bot /stop` 中断群里正在运行的所有轮次，并列出停掉了什么。

`/model`、`/dir`、`/status` 和 `/resume` 在那里不再设置群组默认值；它们是私聊命令，会得到那条私下的提示。Telegram 群组的主聊天本身就是一个对话，所以在那里发的 `/new` 和 `/stop` 照常作用于这个对话。

## 命令菜单 {#command-menus}

Telegram 会显示命令菜单；Coffer 用帮助和错拼检查所用的同一份列表来注册它，所以三者永远一致。私聊里有全部十个命令；群组里只有 `/new`、`/stop`、`/del` 和 `/help`，这些是控制群自己对话的命令。每个菜单都用英文和中文各注册一遍。在群组里，从菜单点的命令会以 `/status@your_bot` 的形式到达，Coffer 把它当作 `/status`。SeaTalk 没有命令菜单，只有一个入口：发 `/help` 即可，仅限私聊的命令会得到那一行私下的提示。

它们就是 `/help` 里显示的那几行。英文描述如下（中文菜单含义相同）：

| 命令 | 菜单描述 |
| --- | --- |
| `/new` | Start a fresh conversation, optionally on another agent |
| `/stop` | Stop what’s running |
| `/status` | What’s running, and the agent, model and directory in use |
| `/model` | Switch the model |
| `/dir` | Switch the working directory |
| `/resume` | Go back to an earlier conversation |
| `/thread` | Open a parallel conversation beside this chat |
| `/close` | Close this parallel thread |
| `/del` | Withdraw my latest reply (reply to one of mine to pick it) |
| `/help` | This list of commands |

## 选择卡片 {#selection-cards}

在支持按钮的平台上，私聊里不带参数的 `/model`、`/dir` 和 `/resume` 会回复一张选择卡片。一张卡片最多六个按钮；更长的列表会分页，每页四个选项，加上 **← Prev** 和 **Next →**，在首页或末页时对应按钮显示为不可点。翻页不改变任何东西，只有点选项才会。当前生效的选项前面带 ✓。点过之后，卡片会原地重写，勾移到你的新选择上。

按钮点击和消息一样接受检查：只有所有者的点击才算数。如果平台拒绝了卡片，命令会改用纯文本回答。
