# 按 agent 的资源 scope

> English: [per-agent-resource-scope.md](./per-agent-resource-scope.md)

- **状态：** 已采纳
- **Spec：** [vault-sync](../../specs/vault-sync/spec.md)（同时修订
  [mcp-gateway](../../specs/mcp-gateway/spec.md) 与
  [skill-manager](../../specs/skill-manager/spec.md)）
- **修订：** [Everything Is a Resource Kind](./everything-is-a-resource-kind.zh.md)（资源现在
  携带 scope）、[Tool Retrieval](./tool-retrieval-for-overload.zh.md) /
  [Built-in Agent Is Internal](./builtin-agent-is-internal-capability.zh.md)
  （`coffer__search_tools` 的排序感知 scope），以及自 2026-09-13 修订起的
  [Provider Switching](./provider-switching.zh.md)（连接的 `compatible_agents` 字段被本 scope
  取代）与 spec [channels](../../specs/channels/spec.zh.md)（渠道的 scope 命名它可以驱动哪些
  agent）。见[修订历史](#修订历史)。

## 背景

有些资源只对某一个 agent *可用*：某个 MCP server 的工具只对 coding CLI 有意义，
某个 skill 是照着 Claude Code 的 frontmatter 写的。而仓库没有通用的方式表达这件
事——网关把每个 server 的工具暴露给每个 agent，放错地方的 server 要么失败、要么
制造噪音。

skill 本来就有自己那套按 agent 的分发策略（消费侧的 follow 开关加排除项）。按 agent 的
MCP scoping 此前作为某个 kind 自己的特性被尝试过一次，并在 2026-06-20 的简化中
被撤销，因为把 allowlist 和会话身份塞在单个 kind 内部，其代价大于它在那里带来的
回报。两个 kind 用两种不同方式解决同一个问题，这个信号说明应该把它提到框架层去
解决——在那里身份管道只需付一次代价，此后任何需要它的 kind 声明一下即可。

本 ADR 原本还带一条 **machine** 轴。它在 2026-09-09 随着当初一同加入的持续同步
被撤销，因为赋予机器身份意义的机器注册表也随之消失，而取值指不向任何东西的轴
不成其为轴。它现在随双向同步一起回来（[Vault Sync](./vault-sync.zh.md)），理由
正是反过来的同一条：收敛后的 vault 让每台机器都持有所有机器的资源，于是「不在
这里」成了资源需要能够表达的东西。它回来时的形状与当初离开时不同——是两条互相
独立的轴，而不是一个矩阵——理由见[已考虑的备选方案](#已考虑的备选方案)。

## 决策

在资源模型上增加一个由框架拥有的 `scope` 字段——两条按 `AND` 相交的允许列表
`agents` 与 `machines`；每个 kind 声明自己是否支持 scope，并各自拥有自己的执行点。

1. **框架级 `scope`。** 唯一的 `scope` 形状位于 `Resource` 实体上，而不在 kind
   config 里：

   ```
   scope == None                              → 处处生效
   scope == {agents: ["claude-code"]}         → 只对该 agent，但在任何机器上
   scope == {machines: ["a3f2…"]}             → 只在该机器上，但对任何 agent
   scope == {agents: [...], machines: [...]}  → 只在两者都匹配处生效
   scope == {agents: []}                      → 休眠（空列表匹配不到任何东西）
   ```

   - 留作 `None` 的轴不构成限制；给了列表的轴就限制到该列表。两条轴按 `AND`
     相交，所以收紧任何一条都只会拿走生效范围，绝不会授予。
   - `is_active(scope, agent=…, machine=…)` → 每条受限的轴都匹配时为 `True`。
     无身份的会话（`agent=None`——一个手工配置、不上报 `--agent` 的 shim）只匹配
     不受限的 agent 轴，因此它看到的严格更少，绝不会更多。
   - `excluded_by(...)` 回答是**哪条**轴让资源在这里休眠，并且**先报 machine
     轴**。「在这整台机器上休眠」和「只对某个 agent 休眠」是两件需要分别解释的
     事，而前者更可能是用户正在找的答案。
   - machine 轴以推导出的 `machine_id` 为键（spec
     [vault-sync](../../specs/vault-sync/spec.zh.md)），绝不用显示名，所以给机器
     改名不产生任何代价。
   - 两条列表里出现未知的名字都是合法的，只是永远匹配不上——可以在某个 agent 或
     某台机器出现之前就把它划进 scope。
   - 不声明 scope 的 kind 在校验阶段拒绝非 null 值（422）。如今 `agent` 是唯一这样的
     kind，其余每个 kind 都声明了 scope——所以这条规则现在是例外，而不是常态。
   - kind 还可以**对被提议的 scope 做前置校验**（`Kind.validate_scope_for`），它是
     config 路径上 `on_update_config` 在 scope 路径上的对应物：它拿到的是资源的当前
     状态加上被提议的 scope，抛错即在任何东西落库之前拒掉这次写入（同一个 422 信封）。
     它之所以存在，是因为一个「读 scope 有超出过滤之外后果」的 kind，可能在自己的
     config 与 scope 之间存在不变量，而只在 config 路径上强制，会让另一条路径把该
     不变量禁止的状态存进去。它紧邻 `on_scope_changed`，并刻意在这次操作的另一端触发：
     这一个可以拒绝，所以必须看到未被修改的行；那一个做收敛，所以必须读到已写入的行。
     目前只有 `channel` 提供它（见第 7 条）。

2. **导出但不激活。** 被 scope 限定的资源照常导出与导入，并在任何地方都保持在
   注册表中可见；在 scope 之外它只是不被激活——不暴露、不分发。注册表仍是唯一
   事实来源，而 scope 就是一个普通的资源字段，原样穿过导出与导入。

3. **各 kind 的支持情况与执行接缝。** 每个 kind 在自己既有的咽喉点查询 scope，
   而不是新设一个中央门禁：

   「轴」这一列说的是某个 kind 的接缝**实际读了哪几条轴**，而这并不自动就是两条：
   字段由框架拥有，但每个 kind 回答的是自己那道接缝在问的问题。

   | Kind | 轴 | 执行接缝 |
   | --- | --- | --- |
   | `mcp_server` | agent + machine | 网关经由 evaluator 按会话身份过滤该 server 的工具，因此一个被 scope 到别的机器上的 server 在这里不呈现任何工具。 |
   | `skill` | agent + machine | 分发时取 skill 自身 `enabled` 与 scope 的交集；已分发但被禁用或不在 scope 内的副本会被回收。被 scope 到别的机器上的 skill 留在 vault 里，但不会写进这里的任何 agent。 |
   | `knowledge` | agent + machine | 内置知识工具过滤：一个会话能 list、grep、读、写哪些 collection。 |
   | `memory` | agent + machine | recall 过滤它能读哪些 partition，因此聚合出的 partition 只触达被 scope 到的那些 agent（spec memory FR-014）。 |
   | `channel` | agent——**反向**——+ machine | 渠道不被任何 agent 消费，因此它的 agent 轴命名的是渠道可以**驱动**哪些 agent：`/agent` 只列出、只提供、只接受这些，一条什么都驱动不了的渠道不会启动。machine 轴回答的是另一个问题——**这条入站面在哪里运行**——它正是那道拦住「两台已收敛的机器同时应答同一条渠道」的闸门。两者在不同接缝上被读：运行时闸门在启动适配器之前两条都读；路由接缝只读 agent 轴，因为它们只会在那道闸门已经放行的机器上执行。 |
   | `provider` | **只有** agent | 投射接缝：切换、按 agent 的密钥查找、导入后收敛、启动自检，读 agent 轴（∩ `enabled`）来决定一条连接被写进哪些 agent。machine 轴刻意不读——「这条连接覆盖哪些 agent 类型」是关于连接本身的断言，在一个已收敛 vault 的每台机器上都必须读出同一个答案。 |
   | `agent` | 无 | 它**就是** agent，因此没有什么可供 scope 收窄。非 null 的 scope 在校验阶段被拒绝。 |

   两条能够**设置**渠道 scope 的写入路径也同样只读 agent 轴，而且理由比路由接缝
   更强：一条被 scope 到别的机器上的渠道必须仍然能从这里编辑，否则一个已收敛的
   vault 里可能存在一条谁也改不了的渠道。

4. **shim 自报的 `--agent` 身份。** shim 安装时把
   `coffer-mcp-shim --agent <name>` 写入 agent 的配置；shim 在握手时连同既有的
   cwd `_meta` 注入一起上报该名字。没有身份的会话（手工配置的 shim）只能看到
   未被 scope 限定的 server。**信任边界：** 身份由 shim 进程自报，未经密码学
   验证——在单用户、仅 loopback 的姿态下这是可接受的。spec 会明确陈述这条边界，
   而不是暗示一种实际并不存在的更强隔离。

5. **skill 的分发就是 `enabled` ∩ scope，再无其他。** 本决策最初保留了 agent 侧
   的 follow 策略并与 scope 取交集，于是分发是 follow ∩ scope 再减去按 agent 的
   排除项，之上还压着一个 per-binding 的 enable 开关。同一个问题被三套机制回答，
   而 `mcp_server` 只用一套就回答了。follow 开关及其排除列表已被删除；binding 行
   如今只是记录「已分发副本」的簿记，不再是开关。一个 skill 送达某 agent 当且仅当
   该 skill 处于 `enabled` 且该 agent 在它的 scope 内；任一侧改变都会立即调谐——
   禁用一个 skill，或把某个 agent 移出它的 scope，即便副本是手工放上去的也会被回收。

   代价是：不再有 agent 侧那个「这个 agent 什么都不要」的单一开关。要排除某个
   agent，就得把它从每个 skill 的 scope 里摘掉——而把某个 agent 从一个 MCP server
   排除，一直以来就是这么做的。按 skill 排除的能力一点没少，只是表达在 skill 上，
   而不是表达在 agent 上。

6. **知识 collection 是要 scope 的——2026-09-12 修订。** 本 ADR 最初写的是
   `knowledge` kind 不声明 scope，因为当时的 collection 只是对*内容*的三种存储
   scope 之一（`global` / `project-<ULID>` / 具名集合），而不是谁刻意划出的边界。
   在这一层精简为纯文件之后，collection 是它**唯一**的边界，而授权正是它之所以
   是 Resource 的全部理由：该 kind 声明 `supports_scope`，agent 只能 list、grep、
   读、写为它激活的那些 collection
   （[Knowledge Is Plain Files](knowledge-is-plain-files.md)，spec knowledge
   FR-010…FR-012）。执行点只在 MCP 工具面，所以它防的是误召回，而不是一个同时
   握有 shell 工具的 agent 有意的文件系统访问（FR-014）。聊天历史、审计日志、
   运行时状态与仅本机的设置保持机器本地（此处是重申边界，不是新决策）。

7. **渠道是要 scope 的，且它的 scope 是反向的——2026-09-13 新增。** 本 ADR 最初写的是
   `channel` 不声明 scope，理由是 scope 命名的是资源对哪些 agent 生效，而渠道不被 agent
   消费。前提没错，结论错了：渠道是仓库里唯一的入站面，它的 scope 的自然读法恰是镜像的
   ——**这条渠道可以驱动哪些 agent**。那是一个真实的授权问题（工作群里的 SeaTalk bot 不应该
   能驱动本机上的每一个 agent），而它此前完全没有答案。

   两个执行接缝，因为少了任何一个都会留下缺口：`/agent` 把它的列表、选择卡片与校验一起收窄
   到 scope（同一个收窄集合，因此卡片绝不会提供一个紧接着被拒的 key），并且渠道的
   `default_agent` 被约束在 scope 之内。

   第二个接缝是两个字段之间的不变量——config 里的 `default_agent` 与行上的 `scope`——而有两个
   端点能破坏它，所以它在**两条**写入路径上强制：config 路径拒绝落在非空 scope 之外的
   `default_agent`（`on_update_config`），scope 路径拒绝排除了当前 `default_agent` 的非空 scope
   （`validate_scope_for`，也就是第 1 条为此长出的那个框架钩子）。只在 config 路径上强制不是
   一条更窄的规则，而是一条破了的规则：被 scope 端点接受的一次收窄，会留下一行 runtime 随后
   拒绝启动的数据，而属主的 bot 死掉了，只有一行日志说明原因。一旦 scope 不再容许某个 thread
   粘滞的 `/agent` 选择，该选择让位于渠道默认值。

   `scope = []` 即休眠；对渠道而言这意味着 runtime 不启动它的适配器——这是响亮而及早的失败，
   而不是一个活着的 bot 先收下消息再拒绝。因此它也是两条写入路径永远接受的那个 scope：休眠
   是属主在说「关掉」，而「关掉」不得同时意味着「冻结」，所以休眠渠道的配置仍然可编辑，写错的
   token 无需先重新激活渠道就能改对。scope 随活的 binding 流转，因此一次编辑在一个收敛周期内
   生效。

8. **`provider` 是要 scope 的，它自己那个「投给哪些 agent」的字段被撤回——2026-09-13 新增。**
   `provider` kind 本来就有这个轴：config 里的 `compatible_agents`，决定一条连接投射到哪些
   agent。它是最后一个还在用自己那套回答框架这个问题的 kind——正是决策第 3 条要终结的分歧
   ——所以该字段被删除，kind 改为声明 `supports_scope`。

   有意思的部分是迁移，也正是它为什么不能只是一次改名。两个轴对「未设置」的含义不一致：
   `compatible_agents = null` 意味着*该 wire 的默认值*（对无密钥的 ollama 连接而言是「一个都
   不给」），而 `scope = null` 意味着*所有 agent*。改名会因此把每一条从未被收窄过的连接都放宽。
   所以迁移 0071 把每一行都**物化**——算出有效集合并具体写出，再剥掉已死的键——而框架多出一个
   小钩子 `Kind.default_scope`，让新建的连接按其 wire 预填，而不是一上来就触达一切。该钩子只是
   config 的函数；`memory` 的起始 scope 是该 partition 从哪些 agent 聚合**而来**，无法以这种方式
   表达，因此它仍在注册之后自己设置 scope。

   这里有两个标志并存，且它们并不冗余：`enabled` 是用户对资源本身的开关（被禁用的连接不投射到
   任何地方，也解析不出 key），而 `is_active` 记录的是「这条连接当前被*写入*了它所触达的那些
   agent」。后者是关于磁盘上某个文件的断言，这也正是存在一个启动自检去抓它与现实不一致的原因。

## 已考虑的备选方案

- **machine × agent 矩阵**——本 ADR 在 2026-08 做出、又在 2026-09-09 撤回的决策。
  随着双向同步回归，它需要的注册表又存在了，当初杀死它的理由已经不成立；但它
  仍然没有被恢复。矩阵比两条独立的轴多买到的东西恰好只有一件：在同一个资源上
  为不同机器指定**不同的** agent。没有人要这个，而拥有它的代价是——每一次读
  scope 都得带上两个坐标，每一个界面都得渲染一张网格。两条按 `AND` 相交的列表
  回答的是真正被问到的那些问题——「只给这个 agent」「只在这台机器上」「只在这里
  给这个 agent」——而空列表表示休眠这一点，在两条轴上读法相同。
- **把按 agent 的 scoping 留在各 kind 内部**——不设框架字段，每个 kind 自己实现
  allowlist 与身份处理。这正是 2026-06 被尝试并撤销的那个形状。否决：两个 kind
  已经在同一个问题上分岔，第三个还会再分岔一次。
- **改用 deny-list 而非 allow-list**——「除这些之外的每个 agent」。否决：新加入的
  agent 会静默获得所有被 scope 限定资源的访问权，这对一个「授予」而言是错误的
  默认值。

## 影响

- `scope` 是 `Resource` 上的一个可空的两轴对象，按 kind 校验，并作为普通字段随
  vault 一起收敛——没有任何专用机制。
- 本机的机器 id 在组合根里一次性绑进一个 `ScopeEvaluator`，而不是穿过每一个调用点
  传下去。忘记传机器 id 会被读成「没有机器」，于是每一个按机器 scope 的资源都静默
  休眠、且什么都说不出来；一次性绑定正是让这件事无法被忘记的办法。凡是刻意只读
  一条轴的接缝，都在接缝处用文字说明理由——否则「只读 agent 轴」与「忘了 machine
  轴」在代码里长得一模一样。
- 网关的工具列表变得与身份相关：同一个 server 在同一个仓库里可以对不同 agent
  呈现不同的工具集。
- 反方向上，没有 `--agent` 的手工 shim 不构成提权路径：它看到的严格更少（只有未被
  scope 限定的资源）。
- 把某个 skill 移出 scope 会从已持有它的 agent 那里回收，因此 scope 的编辑有可见的
  文件系统效果——像其他分发变更一样被审计。
- 除 `agent` 自身之外，scope 现在是整个仓库对「这东西触达哪些 agent」的**唯一**答案。用户学会
  一次这个控件，就能把它用在 server、skill、collection、memory partition、渠道和连接上；某个
  kind 以后长出这个问题时，声明这个字段即可，不必再发明自己的字段。
- 有两个 kind 读 scope 的后果超出了「过滤」：休眠的渠道不运行，休眠的连接不投射到任何 agent。
  所以「休眠」并不总只是不可见——对这两者而言就是关掉。而关掉也仅仅是关掉：休眠的资源依然可见、
  可导出、可编辑。
- 由于一个「scope 带有这类后果」的 kind 现在可以对 scope 写入做前置校验（第 1 条），收窄可达范围
  现在可能被**拒绝**，而不只是产生一个用户并不想要的效果。这多出了一种 scope 编辑会失败的方式，
  代价值得点明：用户偶尔得按顺序做两次编辑（先改掉渠道的 default agent，再收窄它的 scope），而
  以前一次就被接受了。换来的是：停掉一条渠道的唯一途径是明说——`scope = []`，或者禁用它——绝不会
  是一次「看起来成功了」的收窄。

## 修订历史

- **2026-08-xx** — 以 machine × agent 矩阵采纳，`mcp_server` 与 `skill` 声明 scope，
  `agent` / `channel` / `knowledge` 都不声明。
- **2026-09-09** — machine 轴随持续多机同步一并撤回
  （[Vault Sync](./vault-sync.zh.md)），只剩 agent 轴。
- **2026-09-12** — `knowledge` 反转为声明 scope：知识层被削减为纯文件后，collection 是它唯一的
  边界（决策第 6 条）。
- **2026-09-13** — `channel` 与 `provider` 反转为声明 scope（决策第 7、8 条），并把 `memory`
  ——它带着 `supports_scope` 上线，却一直没有进表——补进表里。`agent` 现在是唯一不声明 scope 的
  kind，本 ADR 也不再为它过去排除的那两个 kind 做辩护。
- **2026-09-14** — machine 轴随双向同步回归（[Vault Sync](./vault-sync.zh.md)），
  形态是第二条按 `AND` 相交的允许列表，而不是 2026-08 时的那个矩阵。既有数据以
  「新增」方式迁移：`machines` 不设置就精确复现今天的行为。本 ADR 保留原名，而这
  个名字如今已经窄于它所讲的主题。
