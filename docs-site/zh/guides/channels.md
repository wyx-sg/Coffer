---
title: 消息渠道
description: 把 Telegram 机器人或 SeaTalk 应用接入 Coffer，配对到你自己的账号，然后在你已经在用的 IM 应用里驱动 Claude Code 或 Codex。
---

# 消息渠道 {#channels}

一个**消息渠道**把一个 Telegram 机器人或一个 SeaTalk 应用接入 Coffer，这样你就能在手机上和智能体对话，并收到 Coffer 推送的通知。本页讲所有消息渠道共有的部分：配对、默认智能体和生效范围、消息渠道运行在哪台机器上、命令、媒体和安全。平台配置请看 [Telegram](/zh/guides/channels-telegram) 或 [SeaTalk](/zh/guides/channels-seatalk)。

## 消息渠道是什么 {#what-a-channel-is}

消息渠道是一个类型为 `channel` 的已登记资源。它包含：

- 平台类型 `telegram` 或 `seatalk`，以及该平台的设置；
- 指向 Coffer [密钥存储](/zh/guides/secret-store)中各个密钥的**引用**，而不是密钥本身；
- 一个**默认智能体**：这个消息渠道上新对话开始时用的智能体；
- `runs_on`：由哪一台机器的守护进程运行这个消息渠道的适配器。

你发的一条消息会成为一个普通 Coffer 对话里的一个轮次，智能体的回复再发回 IM 聊天。这个对话就是 Web 界面[对话](/zh/guides/chat)页面列出的那一个，带一个写着消息渠道名的 **via** 标记，所以你可以在手机上开始一个任务，再到浏览器里查看或继续。你在浏览器里输入的回复也会发到它来自的那个聊天，智能体的回答随后跟上（见[回复消息渠道的对话](/zh/guides/chat#replying-to-a-channel-s-conversation)）。

一个机器人可以驱动所有托管的智能体。你在聊天里用 `/new <agent>` 在 Claude Code 和 Codex 之间切换，同一个群的不同话题可以同时运行不同的智能体。

::: info 只管 Coffer 托管的消息渠道
Coffer 只管理它自己托管的消息渠道。智能体自己的官方集成（Claude Code 的 Telegram 插件、厂商的 Slack 应用、智能体原生的网关）独立运行，Coffer 既不管理也不代理。
:::

## 登记消息渠道 {#register-a-channel}

两种方式都是先保存密钥，再用一个指向它的引用登记消息渠道。

::: code-group

```sh [CLI]
# Store the secret (read from stdin, so it stays out of your shell history)
coffer secret set channel/tg/bot-token

# Register the channel; --agent is the agent's type (claude-code or codex)
coffer channel add my-telegram --type telegram \
  --bot-token-ref channel/tg/bot-token --agent claude-code
```

```text [Web UI]
Channels → Add channel
  1 Platform:  SeaTalk | Telegram
  2 Connect:   Name, Default agent, Bot token (or App ID + App secret)
  3 Pair:      the code to send the bot, then "Paired with …"
```

:::

在 Web 界面里，**添加消息渠道**分三步。**平台**一步列出每个平台支持什么、连接需要什么。**连接**一步把密钥写进密钥存储并登记消息渠道，一步完成；对 SeaTalk，它会提醒你在连接*之后*去 SeaTalk Developer Portal 把事件推送方式设为 WebSocket，因为门户会检查是否已有连接。**配对**一步立刻签发一个配对码，等你给机器人发消息（见[配对你的账号](#pair-your-account)）；**稍后配对**会关掉对话框，消息渠道保持未配对。名称由字母、数字、短横线和下划线组成，最长 64 个字符。

如果密钥引用无法解析，登记会被拒绝，什么也不保存。默认智能体没有在这个保险库里登记的，同样会被拒绝。

新消息渠道会绑定到你登记它的那台机器，并且可以驱动所有已登记的智能体。保存后它的适配器立即启动。

## 配对你的账号 {#pair-your-account}

配对让你成为消息渠道的所有者。在配对之前，消息渠道不回复任何人。

1. 生成一个配对码：在消息渠道的**总览**里点**生成配对码**（已配对的消息渠道则在**谁可以使用**下点**重新配对…**，它会先让你确认允许新的所有者接管），或者：

   ```sh
   coffer channel pair my-telegram
   ```

   ```text
   pairing code: K7QM3XPA
   expires at:   2026-09-24T15:04:05Z
   pair link:    https://t.me/my_coffer_bot?start=K7QM3XPA
   Send this code to the bot from the account that should own the channel.
   ```

2. 用你自己的账号把这八个字符作为一条消息发给机器人。在 Telegram 上也可以选**在 Telegram 中打开**，它会打开聊天并填好配对码。页面会显示剩余时间和**等待你的消息…**，直到配对完成，然后显示新的所有者。
3. 机器人确认配对，并接着发一次[帮助](#status-and-help-cards)。现在你是这个消息渠道唯一的所有者。

配对码是八个字符，字母表里没有 `0`、`O`、`1` 和 `I`。它只能用一次，一小时后过期，猜错 10 次后作废。配对码只保存在守护进程的内存里，所以重启守护进程会丢掉还没用的配对码，重新生成一个即可。

用另一个账号再次配对会替换所有者。原所有者的私聊和群组配对都会被移除。

## 和智能体对话 {#talk-to-an-agent}

给机器人发一条消息。第一条消息会在消息渠道的默认智能体上打开一个对话，工作目录是 Coffer 管理的 `~/.coffer/content/workspace`，之后的每条消息都接着这个对话。你可以用[命令](#commands)把聊天切换到另一个智能体、模型或目录。

- 一个表情回应（Telegram）或输入中提示（SeaTalk）表示消息已收到。
- 智能体工作时，实时回复的顶部有一行状态，即使某个工具长时间没有输出，它的计时也一直在走：

  ```
  ⏳ Working · 2m 14s · 7 steps
  💬 Checking the deploy logs
  +4 earlier
  ✅ Read · checkout.spec.ts
  ✅ Bash · rerun the 3DS test
  ⏳ Grep · retry in e2e/
  ─
  The failure is the 3DS step: the sandbox answered after 30 s and…
  ```

  `💬` 那一行是智能体在调用工具前最后说的话；回答在分隔线下面逐渐变长。最终回复保留智能体写下的全部内容，每段连续文字一段。
- 失败、被停止或达到工具迭代上限的轮次，最后会有一行总结：结果、工具调用次数、耗时和 token 数。成功的轮次不发总结，回复本身就是信号。

### 回复的样子 {#what-the-reply-looks-like}

Coffer 会告诉智能体它在哪个平台、哪种聊天里，以及那里能渲染什么，并要求它给出适合手机阅读的回复：第一句就是结论（通知里显示的就是它），不要一步步叙述过程，长内容放在 `## Details` 标题下，图表用图片。然后 Coffer 再把回复调整成适合这个聊天的样子：

- **详情**：在 Telegram 上，`## Details` 小节会折叠显示。在 SeaTalk 上，回复只带这一节之前的部分，随后是一张卡片，标题是结论，带 **Details** 和 **As file** 两个按钮：**Details** 把这一节作为回复发在卡片的话题里，**As file** 把它作为 `.md` 文件发送。
- **表格和日志**：SeaTalk 无法显示表格，所以每一行变成一个列表项（`- **checkout** · failed · 3DS timeout`）；超过 12 行或 4 列的表格只保留前五行，完整内容以 `.csv` 文件发送。超过 30 行的代码块只保留前三行，完整内容以文件发送。
- **长回复**：从不在代码块中间截断，第一条之后的每条消息开头都标明它的位置，比如 `(2/3)`。在 Telegram 上这些后续消息静默送达，只有第一条会发通知。

### 需要你回答的问题 {#questions-for-you}

当智能体需要你点头或做个选择才能继续时（比如它要做某个改动），它会以一个问题结尾，Coffer 把问题单独发成一条消息，每个选项一个按钮：**Yes** / **No**，或最多四个选项。点一个按钮就等于输入那个回答：它作为你的回复进入对话。在群组里只有消息渠道的所有者能回答，其他人点了会被拒绝。点过之后，卡片显示你的回答，不再提供选项。在不支持按钮的平台上，问题留在回复末尾。

### 长轮次结束时 {#when-a-long-turn-finishes}

一个轮次运行超过消息渠道设定的阈值（默认 90 秒）时，如果它的回答本身不会通知你，结束时会补一行短消息：`✅ Done · 4m 12s — <the answer's first line>`，或者 `⚠️ Failed · …`、`⏹ Stopped · …`、`❓ Needs you · …`。在 SeaTalk 上，回答就是轮次开始时打开的那条消息，所以它写完不会提醒任何人，提醒你的是这行完成消息：发在同一个话题里，在群组中还会 @ 你。在 Telegram 上回答总是一条新消息，所以不需要额外这一行。

有两个按消息渠道设置的选项影响这一点，在消息渠道的**设置**标签页**回复**下（**长任务完成提醒**，默认 90 秒；以及**显示步骤行**），或者用 CLI：

- `coffer channel edit <name> --hide-steps`（或 `--show-steps`）：只保留状态头和 💬 那一行，不显示步骤列表。在热闹的群里很有用。
- `coffer channel edit <name> --notify-after <seconds>`：长轮次阈值，0 到 3600；0 表示关闭完成提醒。

快速连发的几条消息算作一个问题。消息渠道在每条消息之后等一小段停顿再开始轮次：文字之后 1.5 秒，转发的聊天记录或不带文字的文件之后 5 秒。停顿期间发来的任何内容都并入同一个轮次。所以你可以先转发一段聊天记录，再输入「看看这个」，智能体看过两者后只回答一次。每条消息到达时仍会立即得到确认。

两个停顿时长都按消息渠道设置：在消息渠道的**设置**标签页**消息合并**下，或者用 `coffer channel edit <name> --wait-after-text <seconds> --wait-after-forward <seconds>`。取值 0 到 60 秒；设为 0 表示每条这类消息都单独回答。

轮次运行期间你发的消息会在对话的队列里等待，按顺序运行，和对话页面显示的是同一个队列。轮次期间连发的一串消息作为一项进入队列。每条等待的消息都会收到「⏳ Queued (n)」的回复，n 是当前等待的数量。最多可以有 10 条在等；已有 10 条等待时再发的消息会被丢弃，机器人会说明这一点和原因。

### 并行对话 {#parallel-conversations}

一个私聊就是一个对话。要在旁边再跑一个任务又不混淆上下文，发送 `/thread [title]`。机器人会打开一个标记为 `🧵#N title` 的话题，你在这个话题里发的内容都在它自己的对话里运行。这个标记就是话题在聊天里的名字、对话在对话页面上的标题，也是在话题里发 `/status` 时的标题。在私聊里发 `/status` 会在一行里列出各个并行话题，并标明每个是在运行、有消息在等，还是空闲。

话题的样子取决于平台。在 SeaTalk 上，它是机器人发的一条消息，你在它下面回复。在 Telegram 上，它是一个私聊话题，需要在 BotFather 里为机器人打开 Threaded Mode。在群组里，每个话题本来就是独立的对话，所以不需要 `/thread`。

每个轮次都会告诉智能体它在一个聊天渠道上：回复要简洁，但支撑结论的关键日志行、错误和 ID 要原样引用，而且它无法点击你电脑上的对话框。每个轮次开头还有一个 `[Message origin]` 块，写明平台、聊天、话题和发送者，这样智能体能回答「这是哪个群？」，也能把平台工具调用对准正确的聊天。轮次的系统提示里还带着[记忆](/zh/guides/memory#in-channel-turns)索引，你消息里点名的笔记会追加在它后面：这两者都由 Coffer 自己投递；在已连接的智能体上，Coffer 的 Hook 在轮次内会为它们让路，但它的触发器仍然守护轮次里的命令。

## 命令 {#commands}

有九个词是 Coffer 的命令。你输入的其他所有内容，包括别的以 `/` 开头的文字，都是发给智能体的消息。

| 命令 | 作用 |
| --- | --- |
| `/new [agent]` | 用这个聊天的设置开始一个新对话。带上智能体名则切换到那个智能体。 |
| `/stop` | 中断正在运行的轮次，并暂停队列。 |
| `/model [name] [level]` | 查看或设置模型和推理强度。 |
| `/dir [path\|name]` | 查看或切换工作目录，切换会开一个新对话。 |
| `/status` | 这个聊天正在运行什么，以带快捷操作的卡片显示。 |
| `/resume [n]` | 重新打开这个聊天之前的一个对话。 |
| `/thread [title]` | 在私聊中，在单独的话题里打开一个并行对话。 |
| `/kb [collection]` | 把你刚发的文档存进一个[知识](/zh/guides/knowledge)知识集。 |
| `/help` | 列出命令，带 New、Stop、Model、Status 和 Resume 按钮。 |

Telegram 的 start 链接会发送 `/start`，它的回答和 `/help` 一样。`/new` 和 `/stop` 即使在轮次运行时也会立即生效。命令会先放行所有还在停顿等待中的消息，让它们在命令之前运行；`/stop` 则会丢弃它们。

### 命令的读法 {#how-the-commands-read}

所有带设置的命令都遵循同一套语法：

- **不带参数**：显示当前生效的值；在支持按钮的平台上还会给出一张卡片来修改：`/model`、`/dir`、`/resume`、`/kb`。
- **带参数就是设置**：`/model opus`、`/dir coffer`、`/resume 2`。
- **`default` 表示重置**：`/model default`、`/dir default`。

名字都是你看得到的名字，从不是内部 id。智能体可以用它的显示名，或小写加连字符的名字（`claude-code`、`codex`）；大小写、`-`、`_` 和空格都不影响。模型可以用它的 id，或它按钮上显示的名字。

### 各命令在哪里可用 {#where-each-command-works}

| 命令 | 私聊 | 并行话题 | 群组话题 | SeaTalk 群主聊天 |
| --- | --- | --- | --- | --- |
| `/new [agent]` | ✓ | ✓ | ✓ | 设置群组的默认智能体；不带参数则显示群组的默认值 |
| `/stop` | ✓ | ✓ | ✓ | 停止群组里正在运行的所有轮次 |
| `/model` | ✓ | ✓ | ✓ | 设置群组的默认值 |
| `/dir` | ✓ | ✓ | ✓ | 设置群组的默认值 |
| `/status` | ✓，并列出并行话题 | ✓ | ✓ | 群组的默认值和正在运行的话题 |
| `/resume` | ✓ | ✓ | ✓ | 请你在话题里回复 |
| `/thread` | ✓ | ✓ | 回答说群组里每个话题本来就是独立的对话 | 同样的回答 |
| `/kb` | ✓ | ✓ | ✓ | ✓ |
| `/help` | ✓ | ✓ | ✓ | ✓ |

在群组中，`/model`、`/dir`、`/status`、`/resume` 和 `/help` 的回答，以及任何「Did you mean」纠正，在平台支持时都只私下发给你。`/new`、`/stop`、`/thread` 和 `/kb` 会改变或指向全群共享的东西，所以保持公开可见。

### 其他斜杠文字交给智能体 {#other-slash-text-goes-to-the-agent}

只有上面九个词会被从对话里拿出来。`/compact`、`/review` 这样的技能，或者以路径开头的消息，比如 `/Users/me/app crashes on start`，都和其他消息一样送到智能体那里，所以智能体自己的斜杠命令在手机上照样能用。

和某个命令只差一点的词，比如 `/stpo`、`/stat`、`/threads`，会得到一行 `Did you mean /stop?` 这样的回答，什么都不运行。短命令（四个字母及以下）容许错一个字母，长命令容许错两个；相邻两个字母对调算错一个。

### 设置跟着聊天走 {#settings-stick-to-the-chat}

每个聊天，以及其中的每个话题，都记住四项设置：智能体、模型、推理强度和工作目录。在那里打开的每个新对话，无论是通过 `/new`、`/dir`，还是因为旧对话被删了，都从这些设置开始。

所以 `/new` 可以放心常用：它清掉的是上下文，不是你的选择。聊天里没设置的项会依次回退到所在群组的默认值（在群组话题里），再到消息渠道的默认智能体和配置。

- `/new <agent>` 切换智能体并记住它。为上一个智能体选的模型和推理强度不会跟过去，因为一个智能体的模型对另一个毫无意义；目录则会跟过去。
- 已有的对话不能更换智能体或目录，因为智能体会话和这两者绑定，所以切换任意一个都会开新对话。旧对话随时可以用 `/resume` 找回。
- 模型和推理强度每个轮次都会重新读取，所以 `/model` 对同一对话的下一个轮次就生效。

### 模型和推理强度 {#model-and-effort}

- `/model <name>` 设置模型。智能体目录里没有的名字会原样传给智能体的 CLI，所以你可以用选择器里没显示的模型；智能体跑不了的名字，会在下一个轮次以 CLI 自己的报错返回。
- `/model <level>` 只设置推理强度。级别有 `minimal`、`low`、`medium`、`high`、`xhigh` 和 `max`；没有模型以这些词命名。
- `/model <name> <level>` 同时设置两者，`/model default` 清除两者，回到智能体自己的默认值。
- 不带参数的 `/model` 显示当前生效的模型和推理强度。在支持按钮的平台上，它是一张两步卡片：先点一个模型，如果该模型有推理级别，同一张卡片会变成级别选择，并带一个保留当前推理强度的按钮。

### 工作目录 {#working-directory}

对话通常在 Coffer 管理的工作目录 `~/.coffer/content/workspace` 里运行。`/dir` 可以把聊天移到另一个目录，但只能是消息渠道允许的目录。之所以有这份允许列表，是因为任何拿到你手机的人，或者一次手滑，都不应该能让一个拥有完整权限的智能体指向你机器上任意一个文件夹；这些地方由你事先在电脑前决定。

两者都在消息渠道的**设置**标签页**工作目录**下。**默认**是新对话开始的位置（不设则用智能体自己的）；**/dir 可用的目录**列出 `/dir` 可以切换进去的文件夹：用**添加目录…**添加，用**移除**删掉，默认目录那一行标着 *default*。一个都不允许时，`/dir` 关闭。也可以用 CLI：

```sh
coffer channel edit my-telegram --default-dir ~/src/coffer              # where new conversations start
coffer channel edit my-telegram --dir ~/src/coffer --dir ~/src/notes   # replaces the list
coffer channel edit my-telegram --no-dirs                              # allows none
```

`--dir` 可以重复，相对路径会被转成绝对路径。每个允许的目录也允许它下面的子目录。

- `/dir <path>` 接受一个允许的路径或它下面的路径；`/dir <name>` 接受某个允许路径的最后一级目录名（`/dir coffer`）。目录必须存在。
- 切换会在那里开一个新对话，并为这个聊天记住该目录。
- `/dir default` 回到消息渠道的默认目录。
- 不带参数的 `/dir` 显示当前生效的目录，并以一张 **Working directory** 卡片列出允许的目录，每个显示路径（家目录下的写成 `~/…`）；默认目录不在其中时还有一个 **Default**。切换成功会回复「📁 Now in `<path>` — started a fresh conversation」。
- 列表外的目录会被拒绝，并列出允许的目录。没有任何允许目录的消息渠道会回复如何添加。

### 恢复之前的对话 {#resume-an-earlier-conversation}

一个聊天打开过的每个对话都会为这个聊天记住。`/resume` 按从新到旧列出最近 20 个，每个带标题、智能体和时间，当前生效的那个打勾。`/resume 2` 或点一下卡片，会让那个对话重新成为这个聊天的活动对话，你的下一条消息就接着它。

只提供这个聊天自己打开过的对话，从不包括来自网页或其他聊天的对话，之后被删掉的对话也不会列出。

### 状态和帮助卡片 {#status-and-help-cards}

`/status` 用文字而不是 id 回答，标题是 **Status**：对话的标题（或它的 `🧵#N` 标记）；一行写着智能体、模型、推理强度和目录；然后是 **Running**、**Running · 2 waiting** 或 **Idle**。在私聊里，它还在一行里列出并行话题，每个标明是在运行、等待还是空闲。

`/help` 在一行里列出所有命令，并说明其他任何内容都是发给智能体的消息。

`/new` 回复一行「🆕 New conversation · Codex · Default model · ~/src/coffer」，在支持按钮的平台上还带 **Agent**、**Model** 和 **Dir** 按钮。**Agent** 列出这个消息渠道可以驱动的智能体；点一个就在它上面开始新对话，和 `/new <agent>` 一样。

在支持按钮的平台上，`/status` 是一张带 **New**、**Model**、**Resume** 和 **Dir** 按钮的卡片，轮次运行时还有 **Stop**；`/help` 是一张带 **New**、**Stop**、**Model**、**Status** 和 **Resume** 的卡片。点按钮的效果和在那个聊天里输入对应命令完全一样，所以记住 `/status` 就能到达所有操作。帮助还会在你配对后立刻发一次，对没有命令菜单的平台（SeaTalk）来说，这就是它告诉你机器人接受什么的方式。

### SeaTalk 上的群组默认值 {#group-defaults-on-seatalk}

在 SeaTalk 上，群主聊天里的每次 @ 提及都会开一个新话题，所以在那里发的设置只会配置一个没人再继续的话题。因此，在主聊天里发的命令配置的是整个群组：

- `@bot /new <agent>`、`@bot /model …` 和 `@bot /dir …` 设置群组的默认值，回答里会写「default for new threads in this group」。群里每个新话题都从这些默认值开始；在话题内部，话题自己的设置仍然优先。
- `@bot /status` 显示群组的默认值和各话题正在运行什么。
- `@bot /stop` 中断群里正在运行的所有轮次，并列出停掉了什么。

Telegram 群组的主聊天本身就是一个对话，所以在那里发的命令照常作用于这个对话。

### 命令菜单 {#command-menus}

Telegram 会显示命令菜单；Coffer 用帮助和错拼检查所用的同一份列表来注册它，所以三者永远一致。私聊里有全部九个命令；群组里有 `/new`、`/stop`、`/model`、`/status`、`/resume` 和 `/help`，这些是适合当着别人面点的。每个菜单都用英文和中文各注册一遍。在群组里，从菜单点的命令会以 `/status@your_bot` 的形式到达，Coffer 把它当作 `/status`。SeaTalk 没有命令菜单，配对后的帮助卡片起到同样的作用。

### 选择卡片 {#selection-cards}

在支持按钮的平台上，不带参数的 `/model`、`/dir`、`/resume`，以及不带知识集的 `/kb`，会回复一张选择卡片。一张卡片最多六个按钮；更长的列表会分页，每页四个选项，加上 **← Prev** 和 **Next →**。翻页不改变任何东西，只有点选项才会。点过之后，卡片会原地重写，勾移到你的新选择上。

按钮点击和消息一样接受检查：只有所有者的点击才算数。如果平台拒绝了卡片，命令会改用纯文本回答。

::: info 与早期版本相比的变化
`/new <agent>` 取代了 `/agent`，`/model <level>` 取代了 `/effort`，`/status` 列出原来 `/threads` 列出的并行话题，`/kb` 取代了 `/save`。旧的词不再保留：`/threads` 会被纠正为 `/thread`，其余的作为文字送到智能体。
:::

## 默认智能体和生效范围 {#default-agent-and-scope}

有两项设置决定由哪个智能体回答。

**默认智能体**是新对话开始时用的智能体。登记消息渠道时设置它；之后在消息渠道**总览**的**智能体** → **默认智能体**里修改。

**生效范围**是消息渠道的覆盖面，即它**可以驱动**的智能体列表。对其他所有资源类型，生效范围指的是资源被投递*给*哪些智能体；而消息渠道不被任何智能体使用，所以它的生效范围要反过来读。在消息渠道**总览**的**可驱动的智能体**里设置，或者：

```sh
coffer channel scope my-telegram                        # show the current scope
coffer channel scope my-telegram --agents claude-code   # may drive only Claude Code
coffer channel scope my-telegram --all                  # may drive every agent
coffer channel scope my-telegram --none                 # dormant: drives nothing
```

- 不受限的生效范围表示所有已登记的智能体。
- 受限的生效范围会在所有地方收窄 `/new <agent>`：你输入未知名字时给出的候选，以及对你输入名字的检查。
- 默认智能体必须始终在生效范围内。Coffer 会拒绝把当前默认智能体排除在外的生效范围，也会拒绝不在当前生效范围内的默认智能体，并用显示名写明两者，让你先扩大生效范围或先改默认智能体。
- 空的生效范围会让消息渠道**休眠**：它的适配器不启动。休眠的消息渠道仍然可以编辑，比如修正一个错误的令牌。
- 收窄生效范围时，话题里已不再被允许的固定智能体选择会被丢掉；下一个对话使用默认智能体。

和所有生效范围设置一样，生效范围和启用开关按机器设置，不会同步。

::: warning 无处可路由的消息渠道不会启动
没有默认智能体、默认智能体不在生效范围内，或默认智能体没有在本机登记的消息渠道都不会启动，它的状态会说明原因。Coffer 从不擅自换成别的智能体。
:::

## 消息渠道运行在哪台机器上 {#the-machine-a-channel-runs-on}

一个机器人只容得下一个消费者：两台机器轮询同一个 Telegram 机器人，或者占用同一个 SeaTalk 应用的连接，就会争抢它的消息。所以每个消息渠道都在 `runs_on` 里指定运行它的那一台机器。和生效范围不同，`runs_on` 是消息渠道配置的一部分，会随[保险库同步](/zh/guides/vault-sync)一起传播，所以每台机器读到的答案都一样。

- 从任何 Coffer 界面登记的消息渠道，都绑定到登记它的那台机器。
- 只有指定的机器会启动适配器。绑定在另一台机器上的消息渠道会显示为在别处运行，而不是已停止。
- 没有绑定，或绑定到注册表不认识的机器的消息渠道，哪里都不运行，并在它的页面上说明这一点。

要迁移消息渠道，在它的**设置**标签页修改**运行在**；对由另一台机器运行的消息渠道，也可以选**在本机运行…**（它会先询问，因为在另一台机器同步之前两台机器可能都会应答）；或者：

```sh
coffer channel bind my-telegram              # bind to this machine
coffer channel bind my-telegram <machine_id> # bind to another machine
```

重新绑定不需要重启。失去消息渠道的机器会在一个调和周期内停掉适配器；得到它的机器会在下一轮同步带来这个变化后启动适配器。要干净地交接，就在当前运行这个消息渠道的机器上重新绑定。如果在另一台机器仍在运行时把消息渠道绑定到你所在的机器，两台机器可能都会应答，直到那台机器的下一轮同步。

你的配对随消息渠道一起走，所以迁移后不需要重新配对。

## 群组和话题 {#groups-and-threads}

把机器人加进一个群组，就能在群里用它。

- 机器人只处理发给它的消息：@ 提及它，或者回复它。群里其他消息都被忽略。
- 只有所有者能驱动它。其他人发给它的消息会收到一句简短的「not authorized」回复，不会开始轮次。
- 在群主聊天里，回答会放进以你那条消息为根的话题里，从不发在主聊天。在话题里，机器人就在那个话题里回复。
- 每个话题是一个独立的对话，有自己的智能体、历史和队列，所以多个话题可以并行运行。
- 群组里的回答挂在提问的那条消息上：在 Telegram 上，它作为对那条消息的回复发送；在 SeaTalk 上，以那条消息为根的话题就是挂载点，回答会 @ 你。
- 你引用一条消息时，被引用的发送者和文字会以 `> sender: …` 行的形式并入轮次，放在你的文字上方。
- 转发的聊天记录会被展平成一个 `[Forwarded chat record]` 块。

有两项消息渠道设置调节机器人在群组里何时回答。它们只改变机器人何时回答，从不改变谁可以驱动它。

| 设置 | 默认值 | 效果 |
| --- | --- | --- |
| `require_mention` | 开 | 机器人在群里保持安静，直到有人 @ 它或回复它。关闭后，它会处理所有者在群里发的每条消息。仅限 Telegram：SeaTalk 只在群消息 @ 了机器人时才把消息推送给它。 |
| `ignore_other_mentions` | 关 | 同时 @ 了其他人的群消息会被放过，即使它也 @ 了机器人。 |

**Web 界面：**在消息渠道的**设置**标签页，使用**群聊中**下的开关：**仅在被 @ 时回复**（仅 Telegram 消息渠道）和**忽略同时 @ 了其他人的消息**。拨动即保存。

**CLI：**把开关传给 `coffer channel add`，或之后用 `coffer channel edit` 修改。没写的选项保持当前值。

```sh
coffer channel edit my-telegram --no-require-mention --ignore-other-mentions
```

```text
require_mention: off
ignore_other_mentions: on
```

如果机器人被移出群组，这个群的会话就会停止。如果一个 SeaTalk 群变成外部群，机器人会在群里发一次警告。

## 媒体 {#media}

像发给真人一样发送照片、文件、语音消息和其他媒体。每个附件都会下载到 `~/.coffer/content/channel-media`，并以智能体能用的形式交给它：

| 你发送的 | 智能体收到的 |
| --- | --- |
| 照片或贴纸 | Claude Code 能看到图片。Codex 拿到文件路径。 |
| PDF、Office 文档、epub 或 rtf | 提取出的文字，放在一个 `[Document: <name>]` 块里。无法提取时给文件路径。 |
| 语音消息或音频 | 在**设置 › 通用 → Coffer 自用模型**下打开了**语音转文字**时，是转写文本。否则是音频文件。 |
| 其他任何文件 | 文件路径。 |
| 位置、联系人名片 | 没有可下载的内容：机器人会请你发文字、照片或文件。 |

超过平台允许机器人下载大小的文件不会被拉取；轮次文字里会注明，所以回复会提到这一点。附件以引用的形式保存，所以同一对话之后的轮次仍能拿到它们。`~/.coffer/content/channel-media` 里的文件在最后修改 30 天后被清理。

::: warning 语音转写会把音频发出你的机器
转写会把音频发给你配置的转写提供商。在你同时选定转写提供商和模型之前，它是关闭的。转写失败从不会让轮次失败，智能体会改为拿到音频文件。
:::

### 回传文件 {#sending-files-back}

智能体要发给你一个文件，只需自己写一行：

```text
MEDIA:/Users/you/reports/q3-chart.png | Q3 revenue by region
```

这一行必须以 `MEDIA:` 开头，后面跟一个绝对路径，可选再加 `| caption`。消息渠道会把文件上传到轮次来自的同一个聊天和话题（图片以照片形式，其他以文档形式），并从回复里删掉这一行。路径不存在、是相对路径或文件超过 50 MB 时，这一行作为文字保留。像 `![chart](chart.png)` 这样的普通 Markdown 从不会被上传。消息渠道的说明会告诉智能体这个语法，所以你直接让它发文件就行。

## 通知 {#notifications}

Coffer 可以在没有收到消息的情况下，主动给已配对的所有者推送一条消息：

```sh
coffer channel notify my-telegram "build finished"
coffer channel notify my-telegram "deploy done" --chat -1001234567890
```

不带 `--chat` 时，消息发到所有者的私聊。`--chat` 指定另一个已配对的聊天，比如一个群组；消息渠道没有配对过的聊天会被拒绝。在消息渠道页面上，**发送测试**（或 **⋯** 菜单里的**发送测试消息**）会向所有者的私聊发一条测试消息，内容可编辑，默认是**来自 Coffer 的测试消息**；它不会开始轮次。给没有已配对所有者的消息渠道发通知会失败，什么也不发。对应的 REST 接口是 `POST /api/v1/channels/{uid}/notify`。

## 管理消息渠道 {#manage-channels}

**消息渠道**页面用来配置和照看消息渠道：它的配置、连接状态和设置。它不显示消息：消息渠道的对话在[对话](/zh/guides/chat)页面，每个消息渠道都有一个 **Conversations from this channel** 链接通往那里，打开的是按它筛选的列表（`/conversations?channel=<uid>`）。

消息渠道列表在打开的消息渠道旁边。它按需要你做什么来分组：**需要处理**（正在重连、被踢下线、无法启动、未配对、没绑定机器或绑定到 Coffer 不认识的机器）、**已连接**、**在其他机器**（由另一台机器运行），以及有的话还有**已关闭**。**筛选**按名称或平台缩小列表。消息渠道按 uid 寻址：`/channels/<uid>` 是它的**总览**，`/channels/<uid>/settings` 是它的**设置**，所以改名不会让链接失效。

页头写着消息渠道名、状态和运行位置（`SeaTalk app 8231 · WebSocket · runs on this machine`），带一个当前状态所需的操作：**发送测试**、**立即重连**、**拿回连接**、**重试**、**更换密钥**或**更换 token**、**在本机运行…**；还有一个 **⋯** 菜单：**发送测试消息**、**重新连接**、**更换机器…**、**更换密钥**（或**更换 token**）和**删除消息渠道**。只要有问题，页头下方就有一条横幅说明原因和修复办法：连接断开正在重连、另一个进程抢走了 SeaTalk 连接、缺少 SeaTalk SDK、平台拒绝了连接、适配器停止了（常见原因是令牌被吊销或密钥被重新生成）、状态读取失败、消息渠道按设计在另一台机器运行，或者没有绑定机器、绑定到未知机器。**重新连接**会重启消息渠道的适配器。

**总览**包含：

- **谁可以使用**：已配对的所有者，配对时间，以及**重新配对…**；未配对的消息渠道则提供**生成配对码**。
- **智能体**：**默认智能体**（选中即保存）和**可驱动的智能体**，即消息渠道的生效范围（见[默认智能体和生效范围](#default-agent-and-scope)）。
- **Conversations from this channel**。

**设置**每改一处就保存一处：数字或路径在你停止输入且合法时保存，开关立即保存；顶部会显示**保存中…**、**已保存**或**保存失败**。它包含消息渠道的标题、**群聊中**、**消息合并**、**回复**、**Directories for /dir**、**密钥**（SeaTalk 的 App ID，以及打码显示的密钥或令牌，带**更换**）、**运行在**和**删除…**。更换的密钥写在消息渠道已经在用的那个引用下，适配器用新密钥重启，所以轮换密钥不会影响配对和绑定。删除消息渠道会停掉机器人并移除配对；它的对话仍保留在对话页面上。

用 CLI：

```sh
coffer channel list
coffer channel show my-telegram
coffer channel disable my-telegram   # stop the adapter
coffer channel enable my-telegram    # start it again
coffer channel rm my-telegram        # stop it and remove the pairing
printf %s "$NEW_TOKEN" | coffer secret set channel/tg/bot-token   # rotate
```

```text
channel:  my-telegram (telegram)
uid:      9b2e…
agent:    claude-code
gating:   require_mention=on  ignore_other_mentions=off
secret:   bot_token_ref = channel/tg/bot-token
enabled:  True    running: True
runs on:  3f9c… (this machine)
pairing:  no pending code
peer:     Ada (chat 123456789)
conv:     01J8Z…
```

如果平台上的某项设置会让消息渠道的配置失效，比如 Telegram 的隐私模式，`coffer channel show` 还会打印一行 `warning:`。

## 安全 {#security}

所有者配对是消息渠道所能做的一切事情的安全边界。

- **只有已配对的所有者能驱动智能体。**Coffer 同时检查聊天和发送者的平台身份（Telegram 的 user id、SeaTalk 的 employee code），所以已配对群组里的其他成员无法驱动轮次。
- **陌生人得到的是沉默。**在私聊中，非所有者发来的消息既没有回复也不产生轮次，所以机器人不会暴露它在运行。在群组中，非所有者发给它的消息会收到一句简短的拒绝。
- **点击和消息一样受检查。**选择卡片上的按钮从不会为非所有者配对，也不会为其切换任何东西。
- **智能体以完整权限运行。**工具调用没有审批步骤。任何能配对这个机器人的人都能让智能体在你的机器上行动，所以要像对待密码一样对待配对码，只在马上要用时才生成。
- **密钥留在保险库里。**消息渠道配置只保存密钥引用；如果引用字段里的值看起来像原始密钥，Coffer 会拒绝。
- **不向网络暴露任何东西。**Telegram 是轮询，SeaTalk 是出站 websocket；两者都不开端口，也不需要公网 URL。

签发和认领配对码会连同消息渠道的生命周期变更一起写进审计日志。消息、通知和轮次不写；对话本身就是它们的记录。

## 工作原理 {#how-it-works}

消息渠道层只在轮次平台的接缝处与智能体接触：对话创建和轮次事件流。所以新增一种消息渠道类型只是多一个适配器，不碰任何智能体代码；新增一个智能体也不用改消息渠道就能从每个消息渠道访问。每个适配器声明自己的能力（实时文本、编辑、按钮、表情回应、媒体），核心根据这些声明决定如何渲染回复，从不根据平台名字判断。见[对话与轮次](/zh/architecture/chat)。

## 相关 {#related}

- [Telegram 配置](/zh/guides/channels-telegram)
- [SeaTalk 配置](/zh/guides/channels-seatalk)
- [对话](/zh/guides/chat)：在浏览器里看同样的对话。
- [密钥存储](/zh/guides/secret-store)：消息渠道密钥存放的地方。
- [保险库同步](/zh/guides/vault-sync)：消息渠道的绑定和配对如何在机器之间传播。
- [安全模型](/zh/architecture/security)
- [规格：channels](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/channels/spec.md)
- [Channel Adapter Framework](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-adapter-framework.md)、[Channel Attachments: Bytes on Disk, a Reference in the Message, Materialised per Agent at Send](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/channel-attachments.md)
