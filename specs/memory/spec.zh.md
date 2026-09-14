# 功能规格：记忆层

> English: [spec.md](./spec.md)

**Created**: 2026-09-12
**Status**: Draft
**目录名**: 本 spec 位于 `specs/memory/`，这个目录名就是所有入链和 `scripts/audit_acceptance.py` 所依据的 spec id。

**Input**: 开发者跑的每个 agent 都各自留着自己的记忆，谁也看不见谁的。Claude Code 按项目一条条积累事实笔记；Codex 把自己的 rollout 蒸馏成 task group 和一份 profile。两边都做得不错，也都不出自己的目录，于是开发者只能把一边已经知道的东西再教给另一边一遍。Coffer **读这些原生记忆，且从不往里写**，把它们归一成一套按项目划分的事实，整理这套事实，再把每个 agent 还不知道的那部分交回给它——会话开始时几百个 token，其余的按需索取。

## 这一层服从的原则

**Coffer 聚合记忆，但不拥有记忆。** 下面每一条规则都由它推出。Coffer 从不写 agent 的原生记忆文件，所以没有哪个 agent 自己的循环会被打扰，也没有任何东西需要对账。`~/.coffer/memory/` 下的一切都是**派生的**，任何时候都可以删掉重建——正因如此，才敢放手去整理它。唯一的例外——本层持有的唯一一份非派生状态——是开发者自己对记忆做的决定，它们被单独存放，正是为了让一次重建抹不掉它们。

## 记忆不是知识

spec [knowledge](../knowledge/spec.md) 存的是用户或 agent **写下的关于世界的东西**：某个平台的 API 契约、某个服务的归属人、一篇上传进来的文档。本层存的是 agent **干活时学到的东西**：用户的偏好、某个项目的决定、已经踩过的坑。它们是两层，因为在所有塑造设计的维度上它们都不同。

| | 记忆 | 知识 |
| --- | --- | --- |
| 从哪来 | agent 的原生记忆，只读 | 人上传，或人和 agent 一起写 |
| 按什么划分 | 项目（外加 `global`） | collection |
| 怎么投递 | **推送**——会话开始时一份有预算的摘要 | **拉取**——agent 自己去够 |
| 一条条目能不能被取代 | 能，而且必须能 | 不能；它是被更新的 |
| store 丢了会怎样 | 从 agent 自己那份重建 | 没了 |
| 怎么整理 | 放手改写一份派生视图 | 保守地改写唯一真相，旧版进 `.history/` |

## 这一层不重蹈的覆辙

Coffer 之前建过记忆闭环的两半，又都删掉了。**Transcript 蒸馏**（2026-09-09 移除）读会话 transcript 写一份 journal；本层根本不读 transcript——Claude Code 和 Codex 各自都在蒸馏自己的，而且比 Coffer 当时做得好得多，本层就从它们的产出起步。**会话上下文注入**（2026-09-10 移除）是一个能用的 hook，但它在维护者自己的机器上一次都没被装上过；投递这次回来，是正面处理了那次失败：安装是一次显式的动作，有看得见的结果，而且这一层会记录注入到底有没有发生（FR-055）。

## 用户场景与测试

### 用户故事 1 — 一个 agent 学到的，其它 agent 都知道（优先级 P1）

上午 Claude Code 学到这个仓库必须在 worktree 里开发。下午开发者在同一个仓库上打开 Codex，它已经知道了——不是因为 Coffer 往 Codex 的记忆里写了什么，而是因为 Coffer 在会话开始时把这条事实交给了它。

**独立测试**：让两个 agent 都注册到 fixture 配置目录上，跑一次同步；确认从 Claude Code 记忆里提取出的那条事实出现在 Coffer 为 Codex 组装的上下文里，且 Codex 自己的记忆文件与之前逐字节相同。

### 用户故事 2 — 记忆按项目归档，外加一个 `global`（优先级 P1）

关于某个仓库的事实属于那个仓库；关于开发者本人的事实——他喜欢别人怎么回答他、他这台机器的 pip 镜像是怎么回事——则到哪都算数。Coffer 把每条事实归进它来自的那个项目，或者当它讲的是人而不是项目时，归进 `global`。

**独立测试**：聚合一份含有一条项目范围事实和一条偏好的 fixture；确认前者落进该项目的 partition、后者落进 `global`，且在一个无关目录里开的会话收到后者而不是前者。

### 用户故事 3 — 会话开场给的是要紧的东西，不是全部（优先级 P1）

一个会话以几百个 token 开场：开发者是谁、这个项目的记忆里有些什么、以及怎么要更多。它不会以两百条事实开场。当 agent 需要某个它叫不出名字的东西时，它用自己的话去问，拿回与之相关的那几条。

**独立测试**：为一个事实数量超出预算的 partition 组装上下文；确认载荷停留在规定的上界之内，并说明有多少条被略去；然后调用 recall，确认被略去的那条够得到。

### 用户故事 4 — 矛盾被摆出来，而不是攒下来（优先级 P2）

两条事实互相打架——较早的一条记着某个机制上线了，较新的一条记着它被删了。Coffer 把它们并排摆出来，把较早的标记为已取代，而不是当两条都成立那样一起投递。

**独立测试**：聚合同一主题上结论相反、时间戳不同的两条事实；确认这一对被报告为一处冲突，且投递的摘要里带的是较新的那条。

### 用户故事 5 — 开发者的判断活得比重建久（优先级 P1）

开发者隐藏了一条从来就不对的事实，把一条一直要紧的置顶，又亲手裁定了一处冲突。然后源变了，一切被重新算过——而他的这三个决定依然有效。

**独立测试**：三种覆盖项各记录一条，删掉整棵记忆树，重跑聚合，确认三条对重新生成出来的事实依然生效。

### 用户故事 6 — 投递是有意装上的，而且看得见（优先级 P1）

会话开始时的投递要动 agent 自己的设置，所以 Coffer 绝不偷偷做。开发者从 Coffer 里把它装上，看得到它已装上，并且——这正是上次栽跟头的地方——看得到它上一次真正跑起来是什么时候。

**独立测试**：装进一份 fixture agent 配置，确认这条写入带 marker 范围且可移除；确认该 surface 报告安装状态与最近一次注入的时间戳，并在还没发生过时报告「从未触发」。

## 验收场景

### Scenario: a Claude Code memory file becomes a normalised fact

### Scenario: a Codex task group becomes normalised facts partitioned by its cwd

### Scenario: the Codex profile becomes global facts

### Scenario: aggregation never modifies an agent's native memory files

### Scenario: an unchanged source file is skipped on the next sync

### Scenario: a fact keeps the agent, path and time it came from

### Scenario: a preference lands in global regardless of which project it came from

### Scenario: a project partition is named from its root, never from an opaque id

### Scenario: a partition is registered as a resource scoped to the agents it came from

### Scenario: the same fact learned by two agents is reported as one with two origins

### Scenario: two facts with opposite conclusions are reported as a conflict

### Scenario: organize regenerates the summary without an internal connection

### Scenario: deleting the memory tree and re-syncing reproduces the facts

### Scenario: a hidden fact stays hidden across a rebuild

### Scenario: a pinned fact stays pinned across a rebuild

### Scenario: a hand-settled conflict stays settled across a rebuild

### Scenario: the composed context stays within its token budget

### Scenario: the composed context says how many facts it left out

### Scenario: recall returns facts the digest omitted

### Scenario: recall falls back to literal matching with no internal connection

### Scenario: recall spans only the partitions the calling agent may see

### Scenario: a channel turn carries the memory context without a hook

### Scenario: hook installation is marker-scoped and removable

### Scenario: hook status reports never-fired until an injection happens

### Scenario: an agent whose native memory shape is unreadable degrades loudly

## 需求

### 聚合

- **FR-001**: Coffer MUST 读取每个**已注册且已启用**的 agent 的原生记忆，路径由该 agent 自己的 `config_dir` 推出（spec [agent-registry](../agent-registry/spec.md)）。未注册的 agent MUST NOT 被读取。
- **FR-002**: 聚合 MUST 是**只读**的。Coffer MUST NOT 创建、修改、移动、删除或重排 agent 自己记忆里的任何文件，也 MUST NOT 停用或重新配置 agent 的原生记忆。这就是 [Aggregate Agent Memory](../../docs/decisions/aggregate-agent-memory-never-write-it.md) 立下的那条禁令，原样保留，如今成了另一套设计的承重约束。
- **FR-003**: Coffer MUST NOT 读取会话 transcript、rollout 或原始捕获文件。两个受支持的 agent 都已经在蒸馏自己的；本层从那份产出起步，自己不再加一层蒸馏。
- **FR-004**: v1 MUST 支持两个 reader。**Claude Code**：它按项目划分的记忆目录下、每条事实一个的 Markdown 文件，frontmatter 里带着这条事实的名称、描述和类型。**Codex**：它 `MEMORY.md` 里的 task group——每组的适用范围、偏好、可复用知识与失败——以及它蒸馏出的 profile 摘要。每个 reader MUST 忽略 agent 自己的索引或汇总文件，因为那个角色由 Coffer 自己重新生成。
- **FR-005**: 解析不了自己来源的 reader——agent 改了格式——MUST **大声地、就地地**失败：那个 agent 什么也不贡献，surface 上写明路径和原因，另一个 agent 的聚合照常完成，先前聚合出的事实原样留着而不是被删掉。
- **FR-006**: 聚合 MUST 跳过内容哈希自上一趟以来没有变化的源文件，且 MUST 为每个源记下足够的信息，使这个判断不需要重新解析就能做出。
- **FR-007**: 聚合 MUST 由后台 worker 按间隔运行，且 MUST 可以手动触发。与知识层的 tidy 不同，它 MAY 默认开启，因为它只读 agent 的文件、只写派生的文件。

### partition

- **FR-010**: 一个 **partition** 是 `~/.coffer/memory/` 下的一个顶层目录，同时是一个 `memory` Resource。MUST 恰好每个项目一个 partition，外加一个叫 `global` 的；不存在别的划分轴。
- **FR-011**: 项目 partition MUST 以从它的项目根推出的**可读 slug** 命名——绝不用不透明 id。绝对根路径 MUST 记在 Resource 上，并在该 partition 自己的 `README.md` 里重述一遍，好让这个目录对着浏览它的人自我解释。重名 MUST 通过加一段有区分度的路径片段来解决，而不是退回用 id。
- **FR-012**: 一条事实 MUST 归进它被学到的那个项目的 partition，唯一的例外是**讲人而不是讲项目**的事实——用户自己的偏好和长期指令——它们 MUST 归进 `global`，不论来自哪个项目。项目根是用户 home 目录的源 MUST 解析为 `global`。
- **FR-013**: partition MUST **由聚合创建**，而不是由用户创建，且 MUST NOT 在读取时由 agent 的工作目录创建出来。
- **FR-014**: partition MUST 支持 Resource 框架的 per-agent scope。它创建时的默认 scope MUST 是它聚合自的那组 agent，使记忆不需要额外设置步骤就能流回它的来源；用户之后 MAY 收窄或放宽。scope MUST 在每一条投递与检索路径上执行。

### 事实

- **FR-020**: 每条事实 MUST 是它所属 partition 下的一个 Markdown 文件，frontmatter 里带 `title`、`description`、`type`（`user` | `feedback` | `project`）、它被看到的那些来源、`captured_at`、源自身的时间戳（如果有的话），以及 `active` 或 `superseded` 的状态。
- **FR-021**: 事实的正文 MUST 是源自己的原话，不是转述。归纳发生在派生的摘要里（FR-031）；事实本身要一直能被原样引回它的来源。
- **FR-022**: 每条事实 MUST 带一个跨重算稳定的**来源键（origin key）**——由贡献它的 agent、原生文件、以及这条事实在文件里的锚点推出——因为开发者的决定就挂在它上面（FR-040）。两个 agent 贡献同一条事实 MUST 产出一条带两个来源的事实，而不是两条事实。
- **FR-023**: `~/.coffer/memory/` 下的整棵树 MUST 是派生的：删掉它再重跑聚合 MUST 能重现它。它 MUST NOT 与同步远端收敛（spec [vault-sync](../vault-sync/spec.zh.md)）：它是从**这台**机器上装着的 agent 聚合出来的，送到另一台机器上去，送过去的事实会被那台机器自己的下一轮聚合重新算掉；而一台从未装过某个 agent 的机器，会看见那个 agent 的 partition 冒出来又消失。丢了这台机器就丢了这棵派生树，这是接受的——必须活下来的是它所派生自的那些源，以及附着在它上面的那些决定，后者由 FR-043 承载。

### organise

- **FR-030**: 聚合之后，MUST 对每个发生了变化的 partition 跑一次由内部连接驱动的 **organise** 过程：它跨 agent 合并重复，当后来的一条与先前的一条矛盾时把先前那条标记为已取代，把它拿不定的一对标为冲突，并写出该 partition 的摘要。
- **FR-031**: organise MAY 放手改写派生的摘要，且 MUST NOT 归档先前的版本——知识层的 `.history/` 之所以存在，是因为知识是唯一的一份，而记忆不是。它 MUST NOT 编辑事实的正文（FR-021），也 MUST NOT 删除事实。
- **FR-032**: 没有配置内部连接时，organise MUST 仍然**机械地**产出一份能用的摘要——事实按类型分组、新的在前、每条从它的 frontmatter 里取一行——只是不贡献任何合并、取代或冲突提议。它 MUST NOT 是一次空操作：一台没有内部模型的安装照样要拿到投递。
- **FR-033**: organise 提出的取代或冲突 MUST 作为模型的判断记在事实上，在每一个 surface 上都与开发者裁定的（FR-041）区分得开。

### 开发者的决定

- **FR-040**: 开发者 MUST 能**隐藏**一条事实、**置顶**一条、把一条标记为**被另一条取代**，以及在一处冲突里**裁定**其中一方胜出。这些 MUST 与派生树分开存放，按来源键索引，放在本层新增的那唯一一张表里。
- **FR-041**: 覆盖项 MUST 在每一次聚合与 organise 之后被重新施加，且 MUST 压过模型决定的任何东西。删掉记忆树、或者某个 partition 被改名，MUST NOT 让它们丢失。
- **FR-042**: 被隐藏的事实 MUST 不出现在任何一次投递和任何一条检索结果里，同时在管理 surface 上仍然可见——也仍然可撤销。被置顶的事实 MUST 在摘要的预算里被优先（FR-051）。
- **FR-043**: 覆盖决定 MUST 与同步远端收敛（spec [vault-sync](../vault-sync/spec.zh.md)），并且它们是这一层里唯一这样做的部分。它们与 FR-023 那棵树恰好在关键处相反：隐藏或置顶是**开发者做出的决定**，不是一次计算，因此没有任何一台机器的聚合过程能把它重现出来，每一台机器都必须被告知。它们以 origin key（FR-022）为键传播——那个键跨重新计算是稳定的，因此跨「各自独立重新计算」的多台机器也是稳定的——每条覆盖一个文档。origin key 里带有路径容不下的字符，所以文档名 MUST 由该键**推导**出来，而不能就是该键本身。

### 投递

- **FR-050**: 投递 MUST 恰好有三层。**L0**，始终给：开发者是谁、这个项目的记忆里有些什么、以及怎么要更多。**L1**，在预算装得下时给：该 partition 的摘要，每条事实一行。**L2**，按需给：`coffer__recall`。
- **FR-051**: 组装出的载荷 MUST **受一个显式 token 预算约束**，当有事实被略去时它 MUST 说明略了多少条、以及怎么够到它们。置顶的事实，然后是 `global` 里讲人的事实，然后是当前项目里最新的那些，MUST 按这个顺序被优先。
- **FR-052**: `coffer__recall` MUST 接受一句自然语言查询，只覆盖调用方 agent 的 scope 允许的那些 partition，返回与之相关的事实及其来源。它 MUST 使用 spec [knowledge](../knowledge/spec.md) FR-025..FR-029 那套带排序的检索——同一个内部连接、同一条可丢弃 sidecar 规则——并且在没有配置内部连接时 MUST 回退到字面匹配，绝不报错。
- **FR-053**: **由渠道驱动的一轮** MUST 通过 turn 平台本就在组装的 system-prompt 追加段拿到 L0 和 L1（spec [channels](../channels/spec.md)）。它 MUST NOT 需要 hook，因为那段上下文本来就在 Coffer 自己手里。
- **FR-054**: 对开发者自己驱动的 agent，投递 MUST 走那个 agent 自己的 hook 机制，调用 Coffer 既有的 CLI。agent 有会话开始事件的，投递 MUST 用它；没有的——Codex，它的 hook 事件只有 `PreToolUse`、`PostToolUse`、`PreCompact`、`Stop` 和 `UserPromptSubmit`——投递 MUST 用它最早的那个每会话事件，并加一道**每会话只触发一次的守卫**，让摘要只到达一次而不是每条提示都来一遍。安装 MUST 是 Coffer surface 上的一次**显式动作**，带 marker 范围以便识别，可在不打扰 Coffer 没写过的条目的前提下移除，且是幂等的。Coffer MUST NOT 偷偷装上它，也 MUST NOT 写进任何属于 agent *记忆*的文件——hook 住在 agent 的设置里，那是另一回事，而且只在开发者明确指示时才会被写。
- **FR-055**: Coffer MUST 逐 agent 报告投递是否已装上、以及**它上一次真正触发是什么时候**，在还没触发过之前报告从未触发。这正是被移除的那层注入所缺的检查：它发了版，从没被装上，而两个月里没有任何东西说过一句。

### Surface

- **FR-060**: MCP 网关 MUST 恰好新增暴露一个内置工具，`coffer__recall`。MUST NOT 存在 `remember` 工具：本层的事实派生自 agent 自己的记忆，而 agent 要记下什么，就按它本来的方式记下来。
- **FR-061**: `/api/v1/memory` 下的一族 REST API 与一个 `coffer memory` CLI 组 MUST 覆盖：列出 partition 与事实、展示某条事实连同它的来源与冲突、跑一次同步、跑一次 organise、组装会话上下文、施加与清除每一种覆盖项，以及为某个 agent 安装／查看／移除投递。
- **FR-062**: Web UI MUST 以**表格**呈现 partition，且无论有没有 partition 都保持同一形态——尚无 partition 的安装 MUST 看到这张表自己的空行以及仍可点到的同步入口，而不是换成另一个页面——并 MUST 呈现单个 partition 的事实，把冲突作为待裁定的成对项摆出来，暴露那四种覆盖项。
- **FR-064**: 逐 agent 的投递状态（含上一次触发时间，FR-055）MUST 呈现在**该 agent 自己的详情页**上，而不是 partition 列表页。投递写的是某一个 agent 的设置文件，因此它是逐 agent 的状态；已经限定到某个 agent 的页面 MUST NOT 再让读者选一次 agent。
- **FR-065**: 本层 MUST NOT 自带审计界面。它的事件在各 kind 共用的全库审计界面上阅读；kind 维度的第二份拷贝属于重复界面，因此本层记录的每一种事件类型 MUST 在那里可读，而不是显示为原始事件码。
- **FR-063**: 每一个生命周期动作——聚合、organise、每一种覆盖项、投递的安装或移除——MUST 记录一条带 actor 的审计事件。一次 recall MUST 记录照常的那行 `mcp_invocations`，且不记录任何关于它的查询或结果的东西。

### 约束

- **FR-070**: 本层 MUST 恰好新增**一张**表，用来放开发者的覆盖项。事实、摘要和 partition 元数据都是文件，或既有的 Resource 行。
- **FR-071**: 文件内容 MUST 只能通过开发者配置的那个内部连接离开这台机器，用于 organise 和 embedding，与 spec [knowledge](../knowledge/spec.md) 允许的完全一致——没有配置时则完全不外发。
- **FR-072**: 读取 MUST 限定在已注册 agent 的配置目录下的那些记忆路径里。每一条由某个源的内容拼出的路径 MUST 通过穿越防护。
- **FR-073**: 本层 MUST NOT 重新引入 transcript 蒸馏、journal lane、原生记忆投影，或逐 agent 的能力矩阵。两个 reader 就写成两个 reader；第三个 agent 出现才配得上一层抽象，在那之前不配。

## 成功标准

- **SC-001**: 一个 agent 学到的事实，出现在为另一个 agent 组装的会话上下文里，而两个 agent 自己的记忆里没有任何文件发生过变化。
- **SC-002**: 把 `~/.coffer/memory/` 整个删掉再重跑一次同步，每条事实都被重现，且开发者记录过的每一条覆盖项依然有效。
- **SC-003**: 在一个事实数量比预算所能容纳的多一个数量级的 partition 上，会话上下文仍停留在它规定的 token 预算之内，并说明它略去了什么。
- **SC-004**: 一台没有配置内部连接的安装照样拿到 partition、事实、摘要、投递和 recall——缺的是合并、取代和排序，而不是这个功能本身。
- **SC-005**: surface 能对每个 agent 回答：投递是否已装上、以及它上一次是什么时候触发的。
- **SC-006**: 某一个 agent 的原生记忆格式错乱或无法识别，不影响另一个 agent 的聚合，也不影响所有先前聚合出的事实。

## 假设

- 每个受支持 agent 的原生记忆格式，都按它今天的样子来读。格式一变，预期就会把 reader 打坏；FR-005 存在的意义，是让它坏得看得见、坏得局部，而不是悄无声息地把 store 清空。
- 两个受支持的 agent 都把自己的记忆蒸馏得足够好，足以当一个好来源。哪天其中一个不再这么做了，答案不是让 Coffer 开始读 transcript，而是重新考虑那个 reader。
- 语料规模保持在每个 partition 几百条事实，正是这一点让进程内排序和一次整份摘要的 organise 过程负担得起。
- hook 住在 agent 的设置文件里，而不是它的记忆里；在开发者明确指示下写一个 hook，与把记忆投影进 agent 是两回事，后者仍然被禁止。
- Codex 没有会话开始事件，所以它的守卫只能以 agent 进程为键，而不是以它并不公开的 session id 为键。这是一个尽力而为的代理值：守卫失灵的代价是摘要重复一次，而不是丢失一次——错误往这个方向倒是对的。
