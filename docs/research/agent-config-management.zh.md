# 竞品调研 —— 统一的多 agent 配置与规则管理

> 中文版：本文件 · English: [agent-config-management.md](./agent-config-management.md)
>
> 面向 Coffer agent 注册表 + 配置文件管理（spec 004）的内部竞品调研报告。
> **日期：** 2026-06-16。**方法：** deep-research harness。**来源说明：** 1 条 claim
> （Ruler 的 MCP 传播）通过完整三票对抗式核验；其余为项目 README 一手来源，但限流导致
> 复核未跑完——视为一手来源，对外引用前请做轻量复核。

## 1. 全景速览

"在一台机器上统一多个 AI 编码 agent 配置"的工具分为三种结构不同的类别：

| 类别             | 做什么                                        | 例子                                                          |
| ---------------- | --------------------------------------------- | ------------------------------------------------------------- |
| **真相源分发器** | 一个中央目录 → 生成各 agent 的原生配置文件    | ruler、rulesync、ai-rulez、airul、vibe-rules、ai-agent-config |
| **共享指令标准** | 一种每个 agent 都读的*输出格式*（不是管理器） | **AGENTS.md**（25–60k+ 项目、28+ agent）                      |
| **托管发现目录** | 索引/浏览规则与配置；不做同步                 | cursor.directory                                              |

主导模式是**单向生成**：一个声明式源（`.ruler/`、`.rulesync/`、`.ai-rulez/`）被编译进
各 agent 的原生文件。MCP 服务器配置管理出现在进阶工具里（ruler、rulesync、ai-rulez、
ai-agent-config），在纯规则工具（airul、vibe-rules）和 AGENTS.md 标准里缺席。

### 各玩家

- **Ruler**（`intellectronica/ruler`，MIT CLI）—— 把指令集中在 `.ruler/` 目录，分发到
  **28+ 个 agent** 的原生文件（CLAUDE.md、AGENTS.md、.clinerules…）。它把 MCP 服务器从
  中央 `ruler.toml`（`[mcp_servers.<name>]`）以 **merge**（默认）或 **overwrite** 策略
  传播到各 agent，支持 per-agent 覆盖（`[agents.<agent>.mcp_servers.<name>]`）；旧的
  `.ruler/mcp.json` 仍可用但带弃用警告，TOML 优先。**无漂移检测、无密钥处理、仅 CLI；
  新增一个 agent 需要 TypeScript handler 代码。** [2-0 确认 —— github.com/intellectronica/ruler]
- **rulesync**（`dyoshikawa/rulesync`，Node CLI）—— 受访中功能最全：规则、MCP 配置、
  ignore 文件、子 agent、斜杠命令、skills、hooks、permissions，从一个 `.rulesync/` 目录
  生成。覆盖 Cursor、Claude Code、Copilot、Codex、Gemini CLI、Cline、OpenCode、Zed、
  Goose、Roo、Kilo、Junie——**不含 Windsurf 或 Aider**。仅 CLI、单向。
- **ai-rulez**（`Goldziher/ai-rulez`）—— 为 **19+ 个工具**生成配置；管理
  规则/上下文/skills/agents/斜杠命令/MCP，并**自带一个内建 MCP server 注入到 agent**——
  概念上接近 Coffer 的"中枢给每个 agent 一个 MCP 入口"。
- **airul / vibe-rules** —— 更轻的 CLI，从一个源把**仅规则/指令**分发到多 agent；无 MCP、
  无密钥、无漂移/备份。
- **ai-agent-config** —— 跨工具同步包含 MCP 的配置的 CLI。
- **AGENTS.md** —— 开放、厂商中立、**按项目**的指令文件（不是中央管理器），被 25–60k+ 项目
  采用、被 28+ agent 读取（Codex 行动前会读）。它是*通用输出语*，不是工具。
- **cursor.directory** —— 托管 web 注册表，索引规则/MCP 供浏览，无本地同步。

## 2. 能力对比

| 能力                      | Ruler              | rulesync | ai-rulez         | airul / vibe-rules | AGENTS.md    | **Coffer**                           |
| ------------------------- | ------------------ | -------- | ---------------- | ------------------ | ------------ | ------------------------------------ |
| 规则/指令分发             | ✅ 28+ agent       | ✅ 12+   | ✅ 19+           | ✅ 仅规则          | （即该格式） | **❌ 不是中枢资产**                  |
| MCP 配置管理              | ✅ merge/overwrite | ✅       | ✅ + 自带 server | ❌                 | ❌           | ✅ 网关 + adopt                      |
| 子 agent / 命令           | 部分               | ✅       | ✅               | ❌                 | ❌           | per-agent 读写                       |
| 方向                      | 单向（源→文件）    | 单向     | 单向             | 单向               | n/a          | **双向（adopt）**                    |
| 读取 agent 真实状态       | ❌                 | ❌       | ❌               | ❌                 | ❌           | **✅ 读时派生、不入库**              |
| 安全编辑（备份/并发）     | ❌                 | ❌       | ❌               | ❌                 | ❌           | **✅ 原子 + .bak + fingerprint 409** |
| 密钥处理                  | ❌                 | ❌       | ❌               | ❌                 | ❌           | **✅ 加密库 + 引用**                 |
| 新增 agent = 数据 vs 代码 | 代码（TS handler） | 代码     | 代码             | 代码               | n/a          | **✅ manifest 数据记录**             |
| 接口                      | CLI                | CLI      | CLI              | CLI                | 文件         | **CLI + REST + 桌面 GUI**            |
| 按项目作用域              | ✅                 | ✅       | ✅               | ✅                 | ✅           | **❌ 仅用户全局 config_dir**         |
| 当前覆盖 agent 数         | 28+                | 12+      | 19+              | 数个               | 28+          | **2 个启用（4 个接好但隐藏）**       |

## 3. Coffer 对比

**Coffer 结构性领先之处。**

1. **双向，而非单向。** 每个竞品都是单向*生成*配置（源 → agent 文件）。唯有 Coffer 还能
   _采集_——"adopt"把某 agent 的 MCP server（或技能）拉进共享中枢再分发。这些工具都没有
   采集这一半。
2. **读取 agent 真实状态。** 这些工具只写、从不回读 agent 实际有什么，故**无漂移检测**。
   Coffer 读时派生 agent 实际 MCP 条目/插件/目录，*本身*就是持续的漂移感知。
3. **安全编辑独一无二。** 原子写 + `.bak` + 内容 fingerprint 乐观并发（陈旧写 409）无对应物
   ——竞品直接覆盖文件，无备份无并发保护。
4. **密钥 + GUI + manifest 入驻。** Coffer 有加密凭证库（竞品不处理密钥）、桌面应用
   （它们仅 CLI），且通过单条 capability-manifest 记录而非 Ruler 式 per-agent handler
   代码来接入新 agent。

**Coffer 落后 / 有真实缺口之处。**

1. **它不把规则/指令从一个源分发到多个 agent——这正是整个品类的定义性功能。** Coffer 把
   CLAUDE.md / AGENTS.md 当作 per-agent 可编辑文件；它对 MCP 和技能有中枢分发，但**没有
   "母指令 → 所有 agent"的投递。** 这是研究暴露的最重要缺口。
2. **广度。** Ruler 覆盖 28+、ai-rulez 19+、rulesync 12+。Coffer 启用 **2** 个（4 个接好但
   隐藏）。对一个"管理你所有 agent"的工具，这个广度差距是实质的。
3. **无按项目作用域。** 这些工具按仓库运作（`.ruler/`、项目 AGENTS.md）。Coffer 只管用户
   全局 `config_dir`。大量真实配置存在于 per-project 层，Coffer 不触及。
4. **无声明式、可版本控制的源。** 竞品的单一声明式文件是优点（可 diff、可提交）。Coffer 的
   就地管理模型没有可导出的声明式形态——这与多机同步 spec 相关。

## 4. 给 Coffer 的关键结论

1. **把"指令/规则"加为一种中枢投递的资产 kind。** 你已对 MCP 和技能做 采集→中枢→投递；
   一个母 CLAUDE.md/AGENTS.md 投递给每个 agent（仿 ruler/rulesync）即可补上整个品类的核心
   功能——而你的双向 adopt 会让它做到同类最佳。
2. **对齐 AGENTS.md 标准**作为共享指令格式，使投递的母指令可原样移植到 28+ agent。
3. **就按项目作用域做决断。** 仓库级配置是竞品占据、Coffer 忽视的一整个维度；要么纳入，
   要么有意识地宣布为范围外。
4. **点亮隐藏的 agent。** 竞品支持 12–28；交付 4 个接好但隐藏的 agent（Cursor/OpenCode/
   OpenClaw/Hermes）能廉价缩小广度差距，因为 manifest 机制已存在。
5. **加入声明式导出**（ruler.toml 风格）以喂给版本控制和多机同步 spec。

## 5. 来源

一手（项目仓库/文档）：

- github.com/intellectronica/ruler _(确认：MCP 传播)_
- github.com/dyoshikawa/rulesync
- github.com/Goldziher/ai-rulez
- airul、vibe-rules、ai-agent-config（项目 README）
- agents.md / AGENTS.md 标准；OpenAI Codex 文档（AGENTS.md 发现）
- cursor.directory

## 核查更新（2026-06-19）

> 对上文标记的五条关键论断做了一次轻量事实核查。五条全部成立；其中两个数字下界
> 已低估当前现实，一处本地表述需修正，并且——最关键的是——本报告的**头号结论被推翻**：
> "Coffer 不分发指令"这一缺口（§3 / §4）已由 PR #112 补上，不再成立。

### ✅ 已确认

- **Coffer 的隐藏 agent 集合。** manifest 中 4 个被禁用的 agent 恰好是
  Cursor / OpenCode / OpenClaw / Hermes（`enabled=False`），启用的恰好是 2 个
  （Claude Code、Codex）。`repo:backend/coffer/domain/agent/descriptor.py`
- **Coffer 双向采集配置（即"采集那一半"）。** spec 004 把工作区修订表述为
  采集→中枢→投递；US10 / FR-028 将"把直连 MCP server 采纳进 Coffer"定义为
  "Coffer 中枢-辐射模型的采集那一半"。`adopt()` 会注册一个 `mcp_server` 资源、
  通过 `self._rs.get(...)` 验证可回读，然后移除直连条目——而漂移感知由"派生而从不
  存储"的 Agent MCP Entry 视图（`cache_present=false` 示例）支撑。技能侧也存在一条
  平行的 `adopt_unmanaged` 路径。`repo:specs/004-agent-registry/spec.md`、
  `repo:backend/coffer/application/agent/mcp_entry_service.py`
- **ai-rulez 自带内置 MCP server。** README 称："ai-rulez 包含一个带 35+ 工具的内置
  MCP server，让 AI 助手自行管理其治理"，通过 `[[mcp_servers]]` 名为 `ai-rulez`
  接入各 agent。"19+ 平台"数目与报告一致。https://github.com/Goldziher/ai-rulez
- **Ruler 从中心配置传播 MCP server**（合并或覆盖，推荐 `.ruler/` TOML，兼容旧版
  JSON）。https://github.com/intellectronica/ruler
- **rulesync 的功能集与目标清单。** 逐字吻合："rules、ignore、mcp、commands、
  subagents、skills、hooks、permissions"；点名的目标均在列，且 Windsurf / Aider
  确实缺席。https://github.com/dyoshikawa/rulesync

### ✏️ 已修正

- **头号结论被推翻 —— Coffer 现已分发指令（§3 缺口 #1、§4 结论 #1、§2"规则/指令分发"行）。**
  本报告最重要的那条结论——"Coffer 不把规则/指令从一个源分发到多个 agent，而这正是整个
  品类的定义性功能"——**自 PR #112 起已不再成立**（"master-instructions 中枢 + per-agent
  投递"，spec 004 US13 / FR-041–FR-046）。Coffer 现在在中枢里保存一份规范的**母指令**文档
  （`~/.coffer/instructions/AGENTS.md`），并将其**投递**进每个 agent 的原生指令文件
  （`CLAUDE.md` / `AGENTS.md` / `SOUL.md`），形式为一个由专属标记包围的 Coffer 托管块
  （`<!-- coffer:instructions:start (managed, do not edit) -->` … `<!-- coffer:instructions:end -->`）。
  投递是**合并、而非覆盖**——只就地（幂等地）upsert 该托管块，标记之外的每个字节都原样保留，
  且该块的标记刻意与 spec-007 的记忆标记区分，使两者在同一文件中共存。Coffer 按 agent 在读时
  派生 `delivered` / `in_sync` 状态（具漂移感知），并且——以 Coffer 标志性的双向操作——可把某
  agent 已有的指令**采纳（adopt）**回母指令。这使 §2"规则/指令分发"行从"❌ 不是中枢资产"翻转为
  一种具合并语义的中枢投递资产，并补上了报告其余部分视为 Coffer 核心差异化缺口的 §3 缺口 #1 /
  §4 结论 #1（加上 adopt，这条轴线上 Coffer 现已堪称同类最佳，而非缺席）。
  `repo:backend/coffer/application/agent/instructions_service.py`、
  `repo:backend/coffer/domain/agent/instructions.py`、
  `repo:backend/coffer/domain/agent/managed_block.py`、
  `repo:backend/coffer/surfaces/http/agent_instructions_routes.py`、
  `repo:specs/004-agent-registry/spec.md`（US13、FR-041–FR-046）
- **Coffer 的 agent 数（§4 结论 #4 / 概览表格）。** 旧："4 个接好、2 个启用"
  → 修正为：**共接入 6 个，2 个启用，4 个隐藏。** manifest 定义了 6 条
  `AgentDescriptor` 记录，而非 4 条；点名的隐藏集合与"2 个启用"原本就正确。
  （结论 #4 的措辞"4 个接好但隐藏的 agent"本身是准确的。）
  `repo:backend/coffer/domain/agent/descriptor.py`
- **Ruler"28+ agent"** → 仍是有效下界，但 README 现已列出 **31** 个点名 agent。
  https://github.com/intellectronica/ruler
- **rulesync"12+ agent"** → 仍是有效下界，但 README 现已列出 **约 25+** 个目标
  （含 Antigravity、AugmentCode、Warp、Qwen Code 等）。https://github.com/dyoshikawa/rulesync
