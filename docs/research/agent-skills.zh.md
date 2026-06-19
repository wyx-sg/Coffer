# 竞品调研 —— Agent 技能管理与分发

> 中文版：本文件 · English: [agent-skills.md](./agent-skills.md)
>
> 面向 Coffer 技能管理器（spec 005）的内部竞品调研报告。**日期：** 2026-06-16。
> **方法：** deep-research harness（扇出网络搜索 → 抓取来源 → 对抗式 claim 核验）。
> **来源说明：** 本轮抓取 21 个来源、提取 104 条 claim，但核验/综合阶段遭遇 API
> 限流，三票核验未跑完——2 条经 3 票确认，其余为单一一手来源（行内标注）。下文事实
> 视为一手来源，但对外引用前请做一次轻量复核。

## 1. 全景速览

"agent 技能"这个品类在 **Anthropic Agent Skills** 推出（约 2025-10）之前几乎不存在，
而在该格式作为开放的 **agentskills.io** 标准发布后迅速爆发（仓库 `agentskills/agentskills`
建于 2025-12-16；标准于 2025-12-18 公布；代码 Apache-2.0 + 文档 CC-BY-4.0）。市场分为四层：

| 层                | 是什么                     | 例子                                                                                                                      |
| ----------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **格式 / 标准**   | SKILL.md 契约 + 渐进式披露 | Anthropic Agent Skills、agentskills.io 开放标准                                                                           |
| **第一方托管**    | 厂商存储并运行技能的界面   | Claude.ai 上传、Claude Developer Platform、Claude Code（文件系统）                                                        |
| **跨 agent 框架** | 一套技能装进多个 agent     | obra/superpowers、ClaudeKit                                                                                               |
| **注册表 / 市场** | 发现 + 批量分发            | tonsofskills.com（约 2800 个技能）、awesome-claude-skills、anthropics/skills、vercel-labs/skills、Smithery skill-packager |

### 什么是"技能"

一个 Agent Skill 是围绕必备的 `SKILL.md` 文件构建的文件系统目录，frontmatter 为 YAML
（`name`、`description`），采用**三级渐进式披露**：元数据始终加载（启动时每技能约 100
tokens）、`SKILL.md` 正文仅在技能被触发时加载（建议 <5k tokens、<500 行）、捆绑的
`scripts/`/`references/`/`assets/` 仅按需加载（实质无上限，经 bash 执行而不进上下文）。
[3-0 确认 —— platform.claude.com/docs agent-skills/overview；
anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills]

开放标准固定了 frontmatter 契约：`name`（≤64 字符、小写字母数字+连字符、**必须与父目录名
一致**）和 `description`（≤1024 字符）为必填；`license`、`compatibility`、`metadata`
和实验性的空格分隔 `allowed-tools` 为可选。**没有内建的 `version` 字段**——version 只是
metadata 的一个示例键。[github.com/agentskills/agentskills]

### 分发与可移植性

- **原则上可移植，实践中孤岛。** 技能在 Anthropic 四个界面间可移植（Claude.ai、Claude
  Code、Agent SDK、Developer Platform），但**自定义技能不跨界面同步**——上传到 Claude.ai
  的技能在 API 上不可用，反之亦然；Claude Code 技能基于文件系统，与二者都分离。[3-0 确认]
- **跨厂商采用是真的。** agentskills.io 的 client showcase 列出约 41 个客户端，包括
  Anthropic 的竞争对手：Gemini CLI、Cursor、GitHub Copilot、OpenAI Codex、Goose、
  Mistral Vibe、Databricks、Snowflake、Letta、OpenHands、Spring AI。
- **主导分发轨道是 Claude Code 插件市场。** Superpowers 通过
  `/plugin install superpowers@claude-plugins-official` 安装（也有 Codex、Cursor、
  Gemini CLI、Copilot CLI、OpenCode、Factory Droid 的对应方式）。ClaudeKit 于 2025-12
  转向插件市场模式（`/plugin marketplace add mrgoonie/claudekit-skills`），获得自动更新
  并**弃用手动 git-clone 安装**；它以分类捆绑形式提供 13 个分类下的 70+ 个技能。
- **真正的市场层已经出现。** tonsofskills.com（MIT）收录约 425–432 个插件、约
  2770–2810 个技能，发布前以 agentskills.io 标准做规范校验，并配 CLI 包管理器 `ccpi`
  （`@intentsolutionsio/ccpi`：对一份权威 `marketplace.json` 做 搜索/安装/列出/更新）。

### 安全 —— 最快变化的子主题

Anthropic 对技能捆绑的代码**不提供任何内建沙箱或签名**；安全寄托于信任模型（"只从可信
来源安装；审计不可信技能"）。这在 2026 年初催生了活跃的威胁研究：

- **OWASP "Agentic Skills Top 10"** —— 专门的风险分类。[owasp.org]
- **ToxicSkills**（Snyk）—— 通过类 ClawHub 渠道分发的恶意 AI-agent 技能。[snyk.io]
- **"Skill Issues：用恶意技能攻陷 Claude Code"**（Reversec，2026-05）。[labs.reversec.com]
- **扫描器绕过** —— 一个恶意代码测试文件据报**通过了 Anthropic 的每一个技能扫描器**。[venturebeat.com]
- safedep.io、repello.ai 的威胁模型。

这是该品类的头号未解问题，且与 Coffer 直接相关。

## 2. 能力对比

| 能力                 | Anthropic Agent Skills | Superpowers             | ClaudeKit      | tonsofskills / ccpi | **Coffer 技能管理器**                        |
| -------------------- | ---------------------- | ----------------------- | -------------- | ------------------- | -------------------------------------------- |
| 单一真相源           | 按界面孤岛（不同步）   | 插件仓库                | 插件市场       | marketplace.json    | **`~/.coffer/skills/` 母库**                 |
| 跨 agent 投递        | 各界面手动             | 按 harness 安装（N 次） | 仅 Claude Code | 仅 Claude Code      | **一个母库 → 多 agent，对账**                |
| 投递机制             | 上传 / 文件系统        | 插件安装                | 插件安装       | CLI 安装            | **按 binding symlink/junction/copy**         |
| 自动分发给所有 agent | 否                     | 否                      | 否             | 否                  | **"跟随母库" + 排除项**                      |
| 采集手放技能         | 否                     | 否                      | 否             | 否                  | **unmanaged 扫描 + adopt**                   |
| 发现 / 浏览          | showcase               | README                  | 13 个分类      | 约 2800 技能        | **无（仅 git URL / 本地路径）**              |
| 版本 / 更新          | 无 version 字段        | git pull                | 自动更新       | ccpi update         | git_ref 锁定，无更新检测 UX                  |
| 采集时供应链加固     | 仅信任模型             | 信任模型                | 规范校验       | 规范校验            | **SSRF 防护、depth-1、体积上限、hooks 关闭** |
| 签名 / 扫描          | 无（扫描器可绕过）     | 无                      | 无             | 仅规范 lint         | **无（不扫描内容）**                         |
| 标准符合             | 定义者                 | SKILL.md                | agentskills.io | agentskills.io 校验 | SKILL.md（尚未对齐标准）                     |

## 3. Coffer 对比

**Coffer 领先之处。**

1. **跨 agent 投递是一等公民、可对账的引擎。** 业界把"一套技能跨多 agent"当作 N 次独立
   安装（Superpowers）或干脆不做。Coffer 是唯一设计了单一母库 + 按 binding 的跨平台链接
   引擎（symlink/junction/copy）+ **"跟随母库"策略**（自动把整库减去 per-agent 排除项推送
   给每个 agent）的方案。这正好解决了 Anthropic 自己记录的痛点（"自定义技能不跨界面同步"）。
2. **采集安全确实领先全场。** 当业界刚因恶意技能（ToxicSkills、OWASP Top 10、扫描器绕过）
   警觉时，Coffer 的 git fetch 已经中和了明显的供应链向量：SSRF 防护、浅 depth-1、克隆体积
   上限、repo hooks 中和、terminal-prompt 关闭。
3. **"采集 unmanaged 技能"独一无二。** 把手放技能合并回受管母库，受访产品中无对应物。

**Coffer 落后 / 应借鉴之处。**

1. **没有发现。** 市场（tonsofskills 约 2800 技能、ClaudeKit 分类、agentskills.io
   showcase）设定了"浏览即装"的标准，Coffer 达不到——它要求用户已经知道一个 git URL。
   一个精选目录或"从 agentskills.io / marketplace.json 导入"可补上。
2. **没有更新检测 / 锁定 UX。** Coffer 存了 `git_ref` 但没有"有更新"信号；ClaudeKit/ccpi
   提供自动更新。借鉴：有更新检测 + 显式 pin/unpin。
3. **采集之外没有信任层。** Coffer 加固*抓取*但不*扫描内容*——研究显示威胁正是捆绑脚本本身，
   而非传输。一个技能扫描器（对捆绑代码做静态检查、强制 `allowed-tools`、展示溯源）能把
   Coffer 的先发优势延伸到该品类头号缺口，也契合其金库定位。
4. **未显式对齐 agentskills.io 标准。** Coffer 已用 SKILL.md；采用标准精确的 frontmatter
   约束（name/description 限制、`allowed-tools`）即可获得对约 41 个客户端的即时可移植性，
   并能原样采集/再分发标准技能。

## 4. 给 Coffer 的关键结论

1. **显式对齐 agentskills.io 开放标准。** 你已说 SKILL.md；采用其 frontmatter 契约 +
   `allowed-tools`，让每个 Coffer 技能可移植到约 41 个客户端，并让采集/再分发无损。
2. **强化差异化卖点。** "一个库、每个 agent、无需按界面重传、自动跟随+排除"是无人提供的，
   把它作为头条。
3. **构建信任层（杠杆最高的缺口）。** 技能供应链攻击（ToxicSkills、OWASP Top 10、扫描器
   绕过）是该品类的公开伤口。你 SSRF 加固的采集是先发优势；延伸到内容扫描 + `allowed-tools`
   强制 + 溯源——这对"金库"是本职工作。
4. **加入发现 + 更新检测。** 一个精选目录 / 市场导入 + "有更新"信号，在不改母库模型的前提下
   补上相对 tonsofskills/ClaudeKit 的两处 UX 差距。

## 5. 来源

一手：

- platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- github.com/agentskills/agentskills · agentskills.io/home
- github.com/anthropics/skills
- github.com/obra/superpowers
- github.com/mrgoonie/claudekit-skills
- github.com/jeremylongshore/claude-code-plugins-plus-skills
- github.com/vercel-labs/skills · github.com/travisvn/awesome-claude-skills
- smithery.ai/skills/shawn-sandy/skill-packager

安全：

- owasp.org/www-project-agentic-skills-top-10/
- labs.reversec.com/posts/2026/05/skill-issues-compromising-claude-code-with-malicious-skills-agents-part-1
- snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/
- venturebeat.com/security/anthropic-skill-scanners-passed-every-check-malicious-code-test-file
- safedep.io/agent-skills-threat-model/ · repello.ai/blog/claude-code-skill-security

评论：

- simonwillison.net/2025/Dec/19/agent-skills/
- unite.ai —— "Anthropic Opens Agent Skills Standard"

## 核查更新（2026-06-19）

> 对一手来源做了一轮轻量复核：核验 1 条本地 claim 与 3 条网络 claim。结论均成立；
> 其中一条网络 claim 的表述需要修正（那些扫描器是第三方工具，并非 Anthropic 自建）。
> **2026-06-19 在 PR #105（frontmatter 对齐）、PR #111（技能内容信任层）与
> PR #115（技能更新检测 + 锁定）合入 `main` 后重新复核：** §2/§3/§4 中"没有技能
> 扫描器 / 内容未被扫描"这一头号缺口现已**补齐**（#111），§4"没有更新检测 / 锁定
> UX"这一缺口也已**补齐**（#115，见下方 ✏️）；frontmatter 对齐状态在下文做了细化
> （#105 为 `description` 设了上限并识别了 `allowed-tools`，但保留下划线作为有意为之的
> 向后兼容超集）。

### ✅ 已确认

- **Coffer 将技能来源锁定到某个 `git_ref`。** `GitSource` 携带
  `git_url`/`git_ref`/`git_subpath`（`repo:backend/coffer/domain/skill/source.py`），
  fetch/clone 会精确解析并把该 ref 复制进母库（spec FR-006）。这一锁定事实在
  `main` 上仍然成立；但报告随附的"没有更新检测 / 落后上游信号"的说法现已过时——
  PR #115 已补上该能力（见下方 ✏️）。
  [`repo:backend/coffer/domain/skill/source.py`、
  `repo:specs/005-skill-manager/{spec,plan}.md`]
- **SKILL.md frontmatter 现已对齐 agentskills.io 约束（PR #105，2026-06-18）——
  部分对齐。** 自 #105 起，`SkillFrontmatter` 强制执行标准的上限（`name` ≤64、
  `description` ≤1024），并且现在会**识别并保留**可选的 `license` 与实验性的
  `allowed-tools` 字段，而不再在 `extra="allow"` 下被丢弃（`allowed-tools` 被
  规整为列表，正是信任层所消费的数据）。报告指出的两处差距属于有意保留、并非遗漏：
  它仍**不**强制 `name == 父目录名`，且 `name` 正则仍容忍下划线（见下方 ✏️）。
  [`repo:backend/coffer/domain/skill/frontmatter.py`、
  `repo:specs/005-skill-manager/{spec,data-model,plan}.md`、spec FR-004/FR-027]
- **Reversec "Skill Issues" 一文确有其事，且与描述一致。** 标题为"Skill Issues:
  Compromising Claude Code with malicious skills & agents — Part 1"，作者
  James Henderson，发布于 **2026-05-05**（报告写的"2026-05"正确）。论点吻合：技能/agent
  是带文件与命令访问权的可执行指令，相当于运行不可信的二进制 / pip 包；RCE 路径包括
  `allowed-tools` frontmatter 与 agent 权限覆盖。
  [labs.reversec.com/posts/2026/05/skill-issues-compromising-claude-code-with-malicious-skills-agents-part-1]
- **agentskills.io 的 frontmatter 约束与报告一字不差。** `name` 必填、≤64 字符、只允许
  小写 `a-z`/`0-9`/连字符（首尾不得为连字符、不得连续连字符）**且必须与父目录名一致**；
  `description` 必填、≤1024 字符、非空；**没有顶层 `version` 字段**（唯一的 `version`
  出现在可选 `metadata` 示例里）；`allowed-tools` 为可选的空格分隔字符串，明确标注
  "(Experimental)"。[agentskills.io/specification]

### ✏️ 已修正

- **§1 安全 / §5 来源中对扫描器绕过事件的表述。** 旧：一个恶意代码测试文件据报"通过了
  **Anthropic 的**每一个技能扫描器"。更正：这些扫描器是**第三方**审计 Anthropic/Claude
  技能的工具——**Snyk Agent Scan、Cisco 的 AI Agent Security Scanner 与 VirusTotal
  Code Insight**——并非 Anthropic 自建。实质不变：藏在 `*.test.ts` 文件里的载荷骗过了
  全部扫描器，因为没有一个把捆绑的测试文件当作执行面来检查（测试文件经标准测试运行器 /
  `npm test` / CI 以完整本地权限运行）。底层研究归于 Gecko Security（在 RSAC 2026 经
  CrowdStrike 披露）。
  [venturebeat.com/security/anthropic-skill-scanners-passed-every-check-malicious-code-test-file]
- **内部小瑕疵：§1 称 `name` 为"小写字母数字+连字符"，但 Coffer 的正则
  `^[a-z0-9][a-z0-9_-]{0,63}$` 还额外允许下划线**，而标准并不允许。PR #105
  （frontmatter 对齐）**并未**移除下划线——如今它在代码与 spec FR-004 中被明确记录为
  _有意为之的向后兼容超集_（以保留磁盘上已有技能的有效性），因此该差异属于设计选择、
  而非疏漏。[`repo:backend/coffer/domain/skill/frontmatter.py`、spec FR-004、
  agentskills.io/specification]
- **§2/§3/§4 的头号缺口"没有技能扫描器 / 内容未被扫描"现已补齐（PR #111，
  2026-06-18——技能内容信任层 L2）。** 报告的能力对照表把 Coffer 标为"无（内容未扫描）"，
  并把内容扫描器列为最高杠杆的缺失项。Coffer 现已配备启发式内容扫描器：
  `scan_skill_folder` 会遍历技能的文本文件，按单行正则规则检测远程执行管道
  （`curl|wget … | sh`）、base64/混淆载荷、密钥/凭证访问（`~/.ssh`、`~/.aws`、
  `id_rsa`、`AWS_SECRET_ACCESS_KEY`）、危险的递归 `rm`、shell `eval`、网络外联与
  提权，给出裁定（`low`/`medium`/`high`/`critical` 或无）。它在**每次 ingest**
  （导入、抓取、收编）以及每次会改动内容的操作（更新/编辑）时运行，把裁定缓存到
  `SkillConfig` 上；并且 **`high`/`critical` 裁定会拦截把技能启用给某个 agent，
  直到用户显式确认风险（409；follow/auto-bind 协调器会跳过未确认的技能）**。它被明确
  定位为咨询性、非权威——Coffer 只分发、从不执行技能，因此报告干净并不等于安全保证
  （ADR-027）。注意这是 Coffer **自有**的扫描器，与上文外部扫描器绕过事件
  （Snyk/Cisco/VirusTotal）无关，后者讲的是第三方审计工具漏掉了藏在捆绑测试文件里的
  载荷。[`repo:backend/coffer/domain/skill/content_scan.py`、
  `repo:backend/coffer/domain/skill/config.py`、
  `repo:backend/coffer/application/skill/{scan_ops,lifecycle_ops,update_ops,binding_ops}.py`、
  `repo:backend/coffer/surfaces/http/skill_routes.py`、spec FR-028/FR-029、
  `repo:docs/decisions/ADR-027-skill-content-trust-layer.md`]
- **§4 的"没有更新检测 / 锁定 UX"缺口现已补齐（PR #115，2026-06-18——技能更新
  检测 + 锁定）。** 报告把"没有'有更新'信号"列为相对 ClaudeKit/ccpi 的两处 UX 缺口
  之一，并明确建议"更新检测 + 显式 pin/unpin"。Coffer 现已两者皆备。按需的
  `check_for_updates`（spec FR-030）会在技能锁定的 `git_ref` 上重新抓取 Git 来源、
  重新校验上游 SKILL.md，并把上游内容哈希（以及 frontmatter `name`，以捕获重命名）
  与已存 `version_hash` 比较——**不应用任何改动**——再把结果
  （`update_available`、`available_version_hash`、`last_update_check_at`）缓存到
  `SkillConfig`；应用更新会清除该信号，且每次检查都会审计（`skill_update_checked`）。
  一个 `pinned` 标志（spec FR-031，`coffer skill pin`/`unpin`，审计
  `skill_pinned`/`skill_unpinned`）会抑制该信号，使有意冻结的技能不再被标为过期；
  `SkillOut` 暴露解析后的 `update_pending = update_available 且 not pinned`。
  三类界面均有呈现：`POST /skills/{name}/check-update` · `/pin` · `/unpin`（HTTP）、
  `coffer skill check-update`/`pin`/`unpin` CLI 以及 `skill show` 中的 `update:` 行、
  桌面端技能详情中的更新行。本地导入的技能无法检查（`UpdateNotSupported`——重新导入
  以刷新）；`plan.md` 的延后项现在只覆盖提交级锁定 / 多版本共存，而非更新检测。
  [`repo:backend/coffer/application/skill/update_ops.py`、
  `repo:backend/coffer/domain/skill/config.py`、
  `repo:backend/coffer/surfaces/http/skill_trust_routes.py`、
  `repo:backend/coffer/surfaces/cli/skill_cmd.py`、
  `repo:frontend/src/components/skills/SkillDetailTabs.tsx`、
  spec FR-030/FR-031]
