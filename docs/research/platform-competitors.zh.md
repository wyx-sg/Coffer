# 平台级直接竞品 —— 盲区补查

> English: [platform-competitors.md](./platform-competitors.md) · 中文版：本文件
>
> **2026-06-20** 由两路并行调研合成（一路按 star 横扫、明确纳入中文生态；一路按
> 能力矩阵覆盖），结果均经 GitHub API 实时核对。本报告之所以存在，是因为最初的
> 十二份报告（2026-06-16/17）是**按 Coffer 各功能区**切分的，结构上漏掉了两类东西：
> (a) **同时横跨多个领域**的工具（平台级竞品），(b) **中文圈的桌面切换器 / 中转 /
> IM 桥接**生态。整个赛道里最大的竞品——`cc-switch`，~105k stars——在此前每一份
> 报告里都缺席。

## 1. 为什么最初的调研漏掉了市场领头羊

到最初调研时，`cc-switch` 已经做成 all-in-one 七八个月了（MCP 自 2025-10，Skills +
"从切换器到平台"的明确转向自 2025-11，会话自 2026-02），且已 ~105k stars、日涨
1000+。漏掉它不是因为它新，而是因为：

1. **类目框定。** 配置那份报告锚定在"规则/配置生成器"那一簇（ruler / rulesync /
   ai-rulez）；`cc-switch` 被归在"供应商切换器"——关键词簇不同，类目范围内的搜索
   永远捞不到它。
2. **地域 / 语言偏差。** 它是中文生态工具（README 以中文为主、国内中转预设、国内
   赞助商）。英文 competitive 搜索对中文主导项目天然欠采样——哪怕 105k stars。

**本次采用的方法修正：** 按 star 横扫 Claude-Code / MCP / agent-config 关键词空间，
并行跑一遍能力矩阵，且默认纳入中文生态工具——绝不锚定一组精选的西方工具。

## 2. 能力 × 工具 矩阵（平台级玩家）

能力：**MCPgw** = MCP 网关/聚合 · **Reg** = MCP 注册表 · **Mem** = 记忆/KB/RAG ·
**Rules** = 规则/指令统一 · **Model** = 供应商/模型切换 · **Skill** = skill 管理 ·
**Cred** = 加密凭据 · **Audit** = 审计 · **Sync** = 多机同步 · **IM** = IM 渠道 ·
**LF** = 本地优先。（✅ 一等公民 · ◐ 部分/经由重叠 · — 无。）star 数 2026-06-20 经
GitHub API 核对。

| 工具                        | ~Stars | 生态   | MCPgw | Reg | Mem | Rules | Model | Skill | Cred | Audit | Sync | IM  | LF  |  #  |
| --------------------------- | ------ | ------ | :---: | :-: | :-: | :---: | :---: | :---: | :--: | :---: | :--: | :-: | :-: | :-: |
| **Coffer**（目标）          | —      | Global |  ✅   |  ◐  | ✅  |  ✅   |   ◐   |  ✅   |  ✅  |  ✅   |  ✅  | ✅  | ✅  | 10  |
| **plugged.in**              | 96     | 西方   |  ✅   | ✅  | ✅  |   —   |  ✅   |   —   |  ✅  |  ✅   |  ✅  |  —  |  ◐  |  7  |
| **Obot**                    | 837    | 西方   |  ✅   | ✅  | ✅  |   —   |  ✅   |   —   |  ✅  |  ✅   |  —   |  —  |  —  |  6  |
| **cc-switch**               | 104.7k | 中文   |  ✅   |  —  |  —  |  ✅   |  ✅   |  ✅   |  ◐   |   —   |  ◐   |  —  | ✅  |  5  |
| **ruflo**（原 claude-flow） | 60.3k  | 西方   |  ✅   |  —  | ✅  |   —   |   —   |  ✅   |  —   |   —   |  —   |  —  |  ◐  |  4  |
| **ToolHive**                | 1.9k   | 西方   |  ✅   | ✅  |  —  |   —   |   —   |   —   |  ✅  |  ✅   |  —   |  —  |  ◐  |  4  |
| **open-cowork**             | 1.7k   | 混合   |  ✅   |  —  |  —  |   —   |  ✅   |  ✅   |  —   |   —   |  —   | ✅  | ✅  |  4  |
| **MCPJungle**               | 1.1k   | 西方   |  ✅   | ✅  |  —  |   —   |   —   |   —   |  ✅  |  ✅   |  —   |  —  |  —  |  4  |
| **claude-code-templates**   | 28.2k  | 西方   |  ✅   |  —  |  —  |   —   |   —   |  ✅   |  —   |   —   |  —   |  —  |  ◐  |  3  |
| **rulesync**                | 1.2k   | 西方   |  ✅   |  —  |  —  |  ✅   |   —   |   ◐   |  —   |   —   |  —   |  —  | ✅  |  3  |
| **Basic Memory**            | 3.3k   | 西方   |  ✅   |  —  | ✅  |   —   |   —   |   —   |  —   |   —   |  ◐   |  —  | ✅  |  3  |
| **claude-mem**              | 83.2k  | 西方   |   —   |  —  | ✅  |   —   |   —   |   —   |  —   |   ◐   |  —   |  —  | ✅  |  2  |
| **Mem0** / OpenMemory       | 58.9k  | 西方   |   ◐   |  —  | ✅  |   —   |   —   |   —   |  —   |   —   |  ◐   |  —  |  ◐  |  2  |
| **claude-code-router**      | 35.1k  | 中文   |   —   |  —  |  —  |   —   |  ✅   |   —   |  —   |   —   |  —   |  —  |  ◐  |  1  |
| **ruler**                   | 2.8k   | 西方   |   ◐   |  —  |  —  |  ✅   |   —   |   —   |  —   |   —   |  —   |  —  | ✅  |  2  |
| **cc-connect**              | 12.7k  | 中文   |   —   |  —  |  —  |   —   |   —   |   —   |  —   |   ◐   |  —   | ✅  |  —  |  1  |

**没有任何在位者覆盖全部 10 项。** 架构上最接近的是 **plugged.in**（7/10），但它是
个 ~96 star 的 web 应用，缺 skills、规则统一、IM。star 最大的几个都是**单一类目**
的巨头，且其中之一（cc-switch）已经在向平台扩张。

## 3. 最值得关注的几个竞品

- **cc-switch**（farion1231）—— **~105k**，中文，Tauri 桌面。市场领头羊、也是唯一
  在向平台化走的：跨 7 个 CLI 切供应商 + 统一 MCP 面板 + Skills 安装 + prompt 同步 +
  会话 + 本地路由/故障转移代理 + 用量追踪。**它缺的：知识库/RAG、真审计、共管记忆
  治理。** 最该盯它；不要在供应商切换的广度上跟它拼。
- **plugged.in**（VeriTeknik/pluggedin-app）—— ~96，西方，web。**理念最像的对手**
  （"给编码 agent 的 AI-CMS"）：跨 Claude/Cursor 的 MCP + RAG + 记忆 + AES-256-GCM
  逐 profile 凭据 + 活动历史 + 多 hub 同步 + 多模型。**值得研究。** Coffer 的楔子：
  skill 管理、规则统一、IM 渠道，以及真正的本地优先桌面（它是 web 应用）。
- **Obot**（obot-platform）—— ~837，西方。最广的**服务端**平台（网关 + 注册表 +
  RAG + 项目记忆 + OAuth + 审计 + 模型管理）——但是 K8s/企业向，不是本地优先的个人
  保险库。
- **cc-connect**（chenhg5）—— **~12.7k**，中文。Coffer channels 的 **IM 桥接**对手，
  覆盖飞书 / 钉钉 / 企业微信 / Slack / Telegram / Discord / LINE / QQ / Matrix。channels
  那份报告说"只有 Anthropic 的 TG 插件能类比"，正是同一个盲区——cc-connect 体量
  大得多。
- **claude-mem**（~83k）与 **Mem0 / OpenMemory**（~59k）—— 单一类目的**记忆**巨头。
  Mem0 的 OpenMemory MCP 是"跨 agent 共享记忆"的范式；**Basic Memory**（~3.3k）是
  最接近 Coffer "共管纯 Markdown 知识库"（spec 006）的类比。
- **claude-code-templates**（~28k）与 **opcode**/Claudia（~22k）—— 分别是资产目录/
  安装器，以及桌面指挥中心。

## 4. vs Coffer —— Coffer 无人争夺的地盘

横跨 30+ 工具、东西方都算上，有四块能力始终覆盖很弱——而它们恰恰是 Coffer 的赌注：

1. **基于共管文件的知识库 + RAG。** 所有切换器和指挥中心都没有；只有记忆专精
   （claude-mem、Basic Memory、Mem0）和服务端平台（Obot、plugged.in）沾边。"文件为
   真相 + 可重建索引"的知识库装在本地优先保险库里，无在位者。
2. **默认免费的审计 / 治理。** 只有企业/web 平台（plugged.in、Obot、ToolHive、
   ContextForge）带审计；没有一个是本地优先桌面工具。
3. **加密凭据作为一等功能。** 几乎所有人都把密钥甩给 1Password / Doppler / Infisical。
   一等的"只存密文"只出现在 plugged.in / Obot / ToolHive——同样，没有一个本地优先。
4. **IM 渠道 × 本地优先保险库。** 只有 open-cowork（飞书/Slack）和 Klavis（dev-infra）
   沾 IM；"IM 渠道 + 本地优先 + skills/记忆/规则"这个组合是空的。

**Coffer 瞄准的组合——本地优先保险库 + MCP 网关 + 记忆/KB + skills + 规则 + 加密
凭据 + 审计 + git 同步 + IM 渠道——是真正无人争夺的。** 护城河命题（"真 RAG + 治理，
而非配置广度"）不只对 cc-switch 成立，对整个赛道都成立。

## 5. 关键要点

- **不要拼广度。** 供应商切换 + 代理 + 用量追踪是 cc-switch 的主场（105k stars、一个
  路由代理、50+ 预设）。Coffer 定的极简供应商切换（共享 registry、不做代理）是对的
  范围；逐项对标 cc-switch 是输家游戏。
- **一个该盯、一个该学。** _盯_ cc-switch（它已在从切换器跨向平台，可能补 KB/记忆）。
  _学_ plugged.in（同样的"资产库"命题，在凭据/审计/记忆上更靠前，但是 web、且在
  skills/规则/IM 上很薄）。
- **值得借鉴的模式**（与既有报告的"借鉴"一致）：逐 client/逐 agent 作用域（每个 MCP
  网关都有）、Mem0 的 **OpenMemory MCP** 共享记忆范式、**Basic Memory** 的共管 Markdown
  知识库形态，以及为可移植性对齐 **agentskills** / **AGENTS.md** / 官方 **MCP Registry**
  标准。
- **流程修正。** 重做 competitive 调研时，按 star 横扫关键词空间 _并_ 跑能力矩阵，且
  默认纳入中文生态。按功能区切分的报告形态利于深度，但对平台级和地域竞品是盲的——
  本报告就是那个横切补充。

## 6. 方法与说明

2026-06-20 跑两路并行：按 star 的发现性横扫（关键词 + awesome-list + GitHub 星标排序，
含中文词）与能力矩阵横扫（逐能力的领头者 + 跨多类目者）。所有头部 star 数均经
GitHub API 直读核对。说明：SaaS 注册表的"stars"（Glama、mcp.so、Smithery）是 server
计数、非仓库 star，不可比；skill _框架_ 巨星仓（obra/superpowers ~233k、anthropics/skills
~153k）是标准/框架、非管理器；少数计数因来源冲突仍不确定（claude-mem ~66k–83k、
Higress org 仓 vs 镜像）；README"星标徽章"（如虚高的 `/topics/claude-code` 数字）一律
弃用、改用 API 直读；Omnara 与 Crystal 截至 2026 年初已归档/弃用。

## 来源

- cc-switch — https://github.com/farion1231/cc-switch
- plugged.in — https://github.com/VeriTeknik/pluggedin-app
- Obot — https://github.com/obot-platform/obot
- cc-connect — https://github.com/chenhg5/cc-connect
- claude-mem — https://github.com/thedotmack/claude-mem
- Mem0 / OpenMemory — https://github.com/mem0ai/mem0
- Basic Memory — https://github.com/basicmachines-co/basic-memory
- claude-code-router — https://github.com/musistudio/claude-code-router
- claude-code-templates — https://github.com/davila7/claude-code-templates
- opcode（原 Claudia）— https://github.com/winfunc/opcode
- ruler — https://github.com/intellectronica/ruler · rulesync — https://github.com/dyoshikawa/rulesync
- MCPJungle — https://github.com/mcpjungle/MCPJungle · MetaMCP — https://github.com/metatool-ai/metamcp · ToolHive — https://github.com/stacklok/toolhive · Director — https://github.com/director-run/director
- 发现性列表 — https://github.com/e2b-dev/awesome-mcp-gateways · https://github.com/hesreallyhim/awesome-claude-code
