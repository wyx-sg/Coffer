# 竞品调研 —— AI 编码 agent 的插件 / 扩展生态

> 中文版：本文件 · English: [agent-plugins.md](./agent-plugins.md)
>
> 面向 Coffer 插件 facet（spec 004 工作区修订）的内部竞品调研报告。**日期：** 2026-06-16。
> **方法：** deep-research harness。**来源说明：** 3 条 claim 经三票/部分确认；其余为
> 官方文档/issue 一手来源，但限流导致复核未跑完。视为一手来源，对外引用前请轻量复核。

## 1. 全景速览

"插件/扩展"在不同 agent 里含义差异很大。三种模型并存：

| 模型                  | 机制                                                   | agent                                 |
| --------------------- | ------------------------------------------------------ | ------------------------------------- |
| **捆绑组件插件**      | 一个目录捆绑 skills/子agent/hooks/MCP/命令，从市场安装 | Claude Code                           |
| **复用 VS Code 扩展** | Open VSX（非 MS 市场）VSIX 扩展 + 独立的 MCP 层        | Cursor、Windsurf（现"Devin Desktop"） |
| **代码模块插件**      | 从 npm 或文件系统加载的 JS/TS 模块 / 配置块            | OpenCode、Continue.dev                |

### 各玩家

- **Claude Code 插件** —— 一个插件是自包含目录，组件包括 **skills（斜杠命令）、agents/
  子agent、hooks、MCP servers、LSP servers、monitors**。[3-0 确认 —— code.claude.com/docs/plugins-reference]
  安装是**两步市场流程**（先加市场目录，再 `/plugin install name@marketplace`），有
  `/plugin enable|disable|uninstall` 动词和 `--scope` 标志。**状态分布在两个面：**
  *面向用户的*启停存在 `settings.json` 系列文件的 `enabledPlugins`（一个 `plugin@marketplace
→ bool` 映射，按作用域：user `~/.claude/settings.json`、project `.claude/settings.json`、
  local `.claude/settings.local.json`）[3-0 确认]，而*内部*安装状态存在
  `~/.claude/plugins/cache`（版本化副本，卸载后 7 天孤儿化+自动移除）和
  `~/.claude/plugins/installed_plugins.json`（安装记录）。**这正是 Coffer 设计所尊重的
  "配置 vs 内部状态"边界。** 一个有记录的坑：local 作用域的 `enabledPlugins` 覆盖在
  `settings.json` 缺该键时会被**静默丢弃**。[github.com/anthropics/claude-code issues #15524, #25086]
- **Cursor** —— 复用 VS Code 扩展模型，但来源是 **Open VSX 注册表**而非微软市场；启停状态
  存在 Cursor 内部 SQLite（非用户可编辑配置文件）。[cursor.com/help]
- **Windsurf / Devin Desktop** —— 同样从 **Open VSX** 取编辑器扩展；MCP 是接入 Cascade
  agent 的**独立集成层**，不是市场扩展。[docs.windsurf.com]
- **OpenCode** —— 插件是 `opencode.json` 中 `plugin` 键下的 **npm 包名数组**，外加从
  `.opencode/plugins/` 和 `~/.config/opencode/plugins/` 自动加载的本地插件文件。一个插件是
  导出函数（接收 context、返回 hooks）的 JS/TS **模块**——是代码，不是声明式捆绑。MCP 独立
  （`mcp` 键，每个 server 一个 `enabled` 布尔）。**截至 2026 年初没有内建启停命令**——需改
  配置或卸载；仅有 `disabled_plugins[]` 数组的提案。[opencode.ai/docs；issue #11743]
- **Continue.dev** —— `config.yaml` 块（models、context、rules、prompts/斜杠命令、docs、
  mcpServers、data）；通过 `uses: owner/blockname` 引用 hub 块。[docs.continue.dev]

### 安全 —— 背景

共享的 VS Code 底座正遭受供应链攻击：**Wiz** 关于 VS Code 扩展市场供应链风险的报告、滥用
70+ 扩展的 **GlassWorm** 蠕虫、以及 **Open VSX** 信任缺口研究（ox.security 的"verified
symbol"利用）都在 2026 年初出现。扩展/插件安装是真实攻击面——这正是 Coffer 不碰安装的*原因*。

## 2. 能力对比

| 能力              | Claude Code                       | Cursor      | Windsurf    | OpenCode   | Continue.dev | **Coffer 插件 facet**     |
| ----------------- | --------------------------------- | ----------- | ----------- | ---------- | ------------ | ------------------------- |
| 插件可捆绑        | skills/agents/hooks/MCP/LSP       | VSIX        | VSIX + MCP  | JS/TS 模块 | 配置块       | n/a（管理而非创作）       |
| 安装 / 市场       | ✅ 两步                           | ✅ Open VSX | ✅ Open VSX | npm/fs     | hub `uses:`  | **❌ 有意排除**           |
| 启停面            | settings.json 的 `enabledPlugins` | 内部 SQLite | —           | 改配置     | config.yaml  | **✅ toggle（文档化处）** |
| 卸载              | ✅                                | ✅          | ✅          | 改配置     | 改配置       | **✅ 配置面允许处**       |
| 写内部状态文件    | cache + installed_plugins.json    | SQLite      | —           | —          | —            | **✅ 从不碰**             |
| 读时清单          | —                                 | —           | —           | —          | —            | **✅ 派生、按市场分组**   |
| 跨 agent 插件视图 | ❌                                | ❌          | ❌          | ❌         | ❌           | **可行（未建）**          |

## 3. Coffer 对比

Coffer 的插件 facet **有意做最小**：读时列出某 agent 的插件（按市场分组、不入库）；
**仅在 agent 文档化配置面支持处**做启停与卸载（由 per-agent capability 描述符分派：
插件模型判别符 + `can_toggle`/`can_uninstall` + 写哪个配置文件）；且**从不写 agent
内部状态文件**。

**研究验证了这个范围划定。**

1. **"从不碰内部状态"规则匹配文档化边界。** Claude Code 自己就把面向用户的 `enabledPlugins`
   （在 settings.json）与内部 `~/.claude/plugins/cache` + `installed_plugins.json` 分开。
   写内部文件会与 agent 自己的簿记打架；Coffer 只写 `enabledPlugins` 恰好正确。
2. **per-agent 描述符匹配真实异构。** 各 agent 确实不同——Claude Code（经 `enabledPlugins`
   toggle；无干净卸载）、Codex（toggle + 卸载）、OpenCode（无内建禁用——须改配置）、Cursor
   （Open VSX；状态在 SQLite → 只读是正确选择）。数据驱动的 `can_toggle`/`can_uninstall`
   是这种差异谱的正确抽象。
3. **不碰安装规避了活跃攻击面。** 鉴于 GlassWorm / Open VSX / VS Code 市场供应链攻击，
   *不*拥有安装意味着 Coffer 不继承那份风险。可见性 + 安全 toggle 覆盖了常见需求。

**Coffer 可扩展之处（不破坏范围）。**

1. **跨 agent 插件清单。** 一个跨所有 agent 的全部插件视图——没有 agent 提供它，且天然契合
   Coffer 注册表。
2. **插件 → 中枢桥（新颖一招）。** 一个 Claude Code 插件*捆绑*了 MCP servers 和 skills。
   Coffer 可把插件的可共享组件（它的 MCP servers、它的 skills）采集进中枢再分发给所有 agent
   ——把 采集→中枢→投递 延伸到插件层。无竞品如此。
3. **市场信任信号。** 鉴于供应链气候，展示溯源（"此插件来自未验证的 Open VSX 命名空间"）。
4. **处理 settings 合并坑**（local `enabledPlugins` 在 settings.json 缺键时被静默丢弃），
   在安全编辑路径里处理。

## 4. 给 Coffer 的关键结论

1. **"可见性 + 安全 toggle/卸载、不安装"的范围是正确的**——既被"配置 vs 内部状态"边界、也被
   插件安装面临的活跃供应链威胁所验证。保持。
2. **你的"从不写内部状态"纪律恰好正确**，匹配 Claude Code 自己的文档化分离。别偏离。
3. **最大机会：插件 → 中枢桥。** 把插件捆绑的 MCP/skills 采集进 Coffer 中枢是你 hub-and-spoke
   模型独有的，把 per-agent 插件变成共享资产。
4. **廉价高价值的补充：** 跨 agent 插件清单 + 市场信任标记，二者都因 2026 供应链攻击而有理。

## 5. 来源

一手：

- code.claude.com/docs/en/plugins-reference · code.claude.com/docs/en/discover-plugins
- github.com/anthropics/claude-code issues #15524, #25086
- cursor.com/help/customization/extensions
- docs.windsurf.com/windsurf/recommended-plugins · …/cascade/mcp
- opencode.ai/docs/plugins · opencode.ai/docs/config · github.com/anomalyco/opencode issue #11743
- docs.continue.dev/reference

安全：

- wiz.io/blog/supply-chain-risk-in-vscode-extension-marketplaces
- thehackernews.com/2026/03 —— GlassWorm 供应链攻击（72 个扩展）
- ox.security —— "Can you trust that verified symbol"（IDE 扩展利用）
- developer.microsoft.com/blog —— VS 市场的安全与信任

## 核查更新（2026-06-19）

> 对本报告核心论断做了一次一手来源核查：结论总体成立，仅两处需精修（GlassWorm 数字统一为 72，并收紧 Claude Code 的 issue 引用）。

### ✅ 已确认

- **Coffer 在插件描述符里按 agent 建模 `can_toggle`/`can_uninstall`。** `PluginCapability` 携带这两个标志（`repo:backend/coffer/domain/agent/plugin_capability.py:45-64`），并在描述符表中按 agent 设置（`repo:backend/coffer/domain/agent/descriptor.py:236-332`）。
- **"跨 agent 插件视图——可行（未建）"准确。** spec 004 只描述了 per-agent 的 Plugins 标签页（`repo:specs/004-agent-registry/spec.md:184`）；代码与 FR 中均无跨 agent 聚合。
- **Codex 的"toggle + 卸载"能力真实且有一手来源。** 由 Coffer 自身描述符背书（`PluginModel.CODEX`、`can_toggle=True`、`can_uninstall=True` —— `repo:backend/coffer/domain/agent/descriptor.py:259-264`）及 FR-033（`repo:specs/004-agent-registry/spec.md:191`、`:629`），外部则有 OpenAI 文档：在 `~/.codex/config.toml` 中以 `enabled = false` 禁用，经插件浏览器 / `codex plugin` CLI 卸载。https://developers.openai.com/codex/plugins
- **OpenCode 无内建启停命令；`disabled_plugins[]` 仅为提案。** issue #11743（"Feature Request: CLI Support for Plugin Enable/Disable"）仍是开放的功能请求、尚未实现；用户当前靠改 `opencode.json` 来禁用。https://github.com/anomalyco/opencode/issues/11743
- **Windsurf 已更名为 "Devin Desktop"。** Cognition 于 2026-06-02 宣布"Windsurf is now Devin Desktop"，以 OTA 更新发布（Cascade 由 Devin Local 取代）。截至 2026-06-19 仍现行。https://devin.ai/blog/windsurf-is-now-devin-desktop/

### ✏️ 已修正

- **GlassWorm 扩展数量："70+"（§1 安全）→ 统一为 "72"。** 报告自己引用的来源标题即为 "GlassWorm Supply-Chain Attack Abuses 72 Open VSX Extensions"（故 §2 的 "72" 正确，§1 的 "70+" 是宽泛措辞——并非量级冲突）。补充背景：一手来源给出随波次不同的数字——7（2025-10 首波，Fluid Attacks）、72（2026 年 1–2 月波次，The Hacker News）、约 73 个潜伏扩展（2026-04 波次，Socket/SecurityWeek）。https://thehackernews.com/2026/03/glassworm-supply-chain-attack-abuses-72.html
- **Claude Code 静默丢弃的引用："#15524, #25086" → #25086 是主依据；#15524 是另一个相邻 bug。** #25086（"enabledPlugins in settings.local.json silently ignored unless key also exists in settings.json"）逐字描述了静默丢弃。#15524 讲的是安装命令未更新 project 级 `settings.json`——相关但不同。两个 issue 现均已 CLOSED（另有较新的重复项 #27247），故"有记录的坑"仍成立，但"是否仍现行"在关闭后存疑。https://github.com/anthropics/claude-code/issues/25086

### ❓ 仍待核查

- Claude Code 的 `enabledPlugins` 静默丢弃是否**仍现行**：#25086 与 #15524 均已 CLOSED，且有较新的重复项 #27247——行为可能在报告快照之后已改变。

### ➕ 新增覆盖

- **OpenAI Codex** —— Codex CLI 具备含市场的完整插件系统：从市场来源 install/list/remove 插件，在 `~/.codex/config.toml` 中以 `enabled = false` 禁用（或 `features.plugins=false` / `--disable plugins`），并经插件浏览器 / `codex plugin` CLI 卸载。这印证了报告能力矩阵中的 "Codex（toggle + 卸载）"，而仓库描述符亦如此建模。注意：尽管 Codex 文档为该能力论断的依据，§5 来源中目前**缺失**它——建议补上。https://developers.openai.com/codex/plugins
