# Platform-Level Direct Competitors — the blind-spot re-sweep

> English: this file · 中文版: [platform-competitors.zh.md](./platform-competitors.zh.md)
>
> Produced **2026-06-20** by two parallel sweeps (a stars-first sweep that
> explicitly included the Chinese ecosystem, and a capability-matrix sweep),
> each verified against the live GitHub API. This report exists because the
> original twelve reports (2026-06-16/17) were organized **per Coffer area** and
> structurally missed two things: (a) tools that span **many categories at once**
> (platform-level competitors), and (b) the **Chinese desktop-switcher / relay /
> IM-bridge ecosystem**. The single largest competitor in the whole space —
> `cc-switch`, ~105k stars — was absent from every prior report.

## 1. Why the original sweep missed the market leader

`cc-switch` had been an all-in-one for 7–8 months by the time of the original
research (MCP since 2025-10, Skills + the explicit "from switcher to platform"
pivot since 2025-11, sessions since 2026-02), and was already ~105k stars
gaining 1,000+/day. It was not missed because it was new. It was missed because:

1. **Category framing.** The config report anchored on the "rules/config
   generator" cluster (ruler / rulesync / ai-rulez). `cc-switch` is filed under
   "provider switcher" — a different keyword cluster — so a category-scoped
   search never surfaced it.
2. **Geographic / language bias.** It is a Chinese-ecosystem tool (Chinese-first
   README, domestic relay presets, domestic sponsors). English competitive
   search under-surfaces Chinese-dominant projects even at 105k stars.

**Method correction adopted here:** sort GitHub by stars across the
Claude-Code / MCP / agent-config keyword space, run a parallel capability-matrix
pass, and explicitly include Chinese-ecosystem tools — never anchor on a curated
Western set.

## 2. The capability × tool matrix (platform-level players)

Capabilities: **MCPgw** = MCP gateway/aggregation · **Reg** = MCP registry ·
**Mem** = memory/KB/RAG · **Rules** = rules/instructions unify · **Model** =
provider/model switch · **Skill** = skills manager · **Cred** = encrypted
credentials · **Audit** = audit trail · **Sync** = multi-machine sync · **IM** =
IM channels · **LF** = local-first. (✅ first-class · ◐ partial / via overlap ·
— none.) Stars verified via the GitHub API on 2026-06-20.

| Tool                       | ~Stars | Eco    | MCPgw | Reg | Mem | Rules | Model | Skill | Cred | Audit | Sync | IM  | LF  |  #  |
| -------------------------- | ------ | ------ | :---: | :-: | :-: | :---: | :---: | :---: | :--: | :---: | :--: | :-: | :-: | :-: |
| **Coffer** (target)        | —      | Global |  ✅   |  ◐  | ✅  |  ✅   |   ◐   |  ✅   |  ✅  |  ✅   |  ✅  | ✅  | ✅  | 10  |
| **plugged.in**             | 96     | West   |  ✅   | ✅  | ✅  |   —   |  ✅   |   —   |  ✅  |  ✅   |  ✅  |  —  |  ◐  |  7  |
| **Obot**                   | 837    | West   |  ✅   | ✅  | ✅  |   —   |  ✅   |   —   |  ✅  |  ✅   |  —   |  —  |  —  |  6  |
| **cc-switch**              | 104.7k | CN     |  ✅   |  —  |  —  |  ✅   |  ✅   |  ✅   |  ◐   |   —   |  ◐   |  —  | ✅  |  5  |
| **ruflo** (ex-claude-flow) | 60.3k  | West   |  ✅   |  —  | ✅  |   —   |   —   |  ✅   |  —   |   —   |  —   |  —  |  ◐  |  4  |
| **ToolHive**               | 1.9k   | West   |  ✅   | ✅  |  —  |   —   |   —   |   —   |  ✅  |  ✅   |  —   |  —  |  ◐  |  4  |
| **open-cowork**            | 1.7k   | Hybrid |  ✅   |  —  |  —  |   —   |  ✅   |  ✅   |  —   |   —   |  —   | ✅  | ✅  |  4  |
| **MCPJungle**              | 1.1k   | West   |  ✅   | ✅  |  —  |   —   |   —   |   —   |  ✅  |  ✅   |  —   |  —  |  —  |  4  |
| **claude-code-templates**  | 28.2k  | West   |  ✅   |  —  |  —  |   —   |   —   |  ✅   |  —   |   —   |  —   |  —  |  ◐  |  3  |
| **rulesync**               | 1.2k   | West   |  ✅   |  —  |  —  |  ✅   |   —   |   ◐   |  —   |   —   |  —   |  —  | ✅  |  3  |
| **Basic Memory**           | 3.3k   | West   |  ✅   |  —  | ✅  |   —   |   —   |   —   |  —   |   —   |  ◐   |  —  | ✅  |  3  |
| **claude-mem**             | 83.2k  | West   |   —   |  —  | ✅  |   —   |   —   |   —   |  —   |   ◐   |  —   |  —  | ✅  |  2  |
| **Mem0** / OpenMemory      | 58.9k  | West   |   ◐   |  —  | ✅  |   —   |   —   |   —   |  —   |   —   |  ◐   |  —  |  ◐  |  2  |
| **claude-code-router**     | 35.1k  | CN     |   —   |  —  |  —  |   —   |  ✅   |   —   |  —   |   —   |  —   |  —  |  ◐  |  1  |
| **ruler**                  | 2.8k   | West   |   ◐   |  —  |  —  |  ✅   |   —   |   —   |  —   |   —   |  —   |  —  | ✅  |  2  |
| **cc-connect**             | 12.7k  | CN     |   —   |  —  |  —  |   —   |   —   |   —   |  —   |   ◐   |  —   | ✅  |  —  |  1  |

**No incumbent covers all 10.** The closest architectural analog is **plugged.in**
(7/10) but it is a ~96-star web app missing skills, rules-unify, and IM. The
biggest stars are **single-category** giants that _could_ expand — and one of
them, cc-switch, already has.

## 3. The competitors that matter most

- **cc-switch** (farion1231) — **~105k**, Chinese, Tauri desktop. The market
  leader and the one platform-trending tool: provider-switch across 7 CLIs +
  unified MCP panel + Skills install + prompt sync + sessions + a local
  routing/failover proxy + usage tracking. **What it lacks: knowledge-base/RAG,
  a real audit trail, shared-memory governance.** Watch it most; do not fight it
  on provider-switching breadth.
- **plugged.in** (VeriTeknik/pluggedin-app) — ~96, Western, web. **The closest
  thesis-analog** ("an AI-CMS for coding agents"): MCP across Claude/Cursor +
  RAG + memory + AES-256-GCM per-profile credentials + activity history +
  multi-hub sync + multi-model. **Study it.** Coffer's wedge: skills-manager,
  rules-unify, IM channels, and true local-first desktop (it is a web app).
- **Obot** (obot-platform) — ~837, Western. Broadest _server_ platform
  (gateway + registry + RAG + project memory + OAuth + audit + model mgmt) — but
  K8s/enterprise, not a local-first personal vault.
- **cc-connect** (chenhg5) — **~12.7k**, Chinese. An **IM-bridge** rival to
  Coffer's channels, spanning Feishu / DingTalk / WeChat Work / Slack / Telegram /
  Discord / LINE / QQ / Matrix. The channels report's "Anthropic's TG plugin is
  the only analog" was the same blind spot — cc-connect is far bigger.
- **claude-mem** (~83k) and **Mem0 / OpenMemory** (~59k) — single-category
  **memory** giants. Mem0's OpenMemory MCP is the canonical shared-memory-across-
  agents pattern; **Basic Memory** (~3.3k) is the closest analog to Coffer's
  co-managed plain-Markdown KB (spec 006).
- **claude-code-templates** (~28k) and **opcode**/Claudia (~22k) — the asset
  catalog/installer and the desktop command-center, respectively.

## 4. vs Coffer — where Coffer is uncontested

Across a 30+ tool field, East and West, four capabilities stay weakly covered —
and they are exactly Coffer's bet:

1. **Knowledge base + RAG over co-managed files.** Absent from every switcher and
   command-center; only memory specialists (claude-mem, Basic Memory, Mem0) and
   server platforms (Obot, plugged.in) touch it. A files-as-truth + rebuildable-
   index KB inside a local-first vault has no incumbent.
2. **Audit / governance, free and by default.** Only enterprise/web platforms
   (plugged.in, Obot, ToolHive, ContextForge) carry an audit trail; none is a
   local-first desktop tool.
3. **Encrypted credentials as a first-class feature.** Almost everyone delegates
   secrets to 1Password / Doppler / Infisical. First-class ciphertext-only
   storage appears only in plugged.in / Obot / ToolHive — again, none local-first.
4. **IM channels × local-first vault.** Only open-cowork (Feishu/Slack) and
   Klavis (dev-infra) touch IM at all; the combination of IM channels +
   local-first + skills/memory/rules is empty.

**The combination Coffer targets — local-first vault + MCP gateway + memory/KB +
skills + rules + encrypted creds + audit + git-sync + IM channels — is genuinely
uncontested.** The moat thesis ("real RAG + governance, not config breadth")
holds not just against cc-switch but against the entire field.

## 5. Key takeaways

- **Don't chase breadth.** Provider-switch + proxy + usage tracking is
  cc-switch's home turf (105k stars, a routing proxy, 50+ presets). Coffer's
  decided minimal provider-switching (shared registry, no proxy) is the right
  scope; matching cc-switch feature-for-feature is a losing game.
- **One to watch, one to study.** _Watch_ cc-switch (it is already crossing from
  switcher to platform and could add KB/memory). _Study_ plugged.in (same "asset
  vault" thesis, further along on creds/audit/memory, but web and feature-thin on
  skills/rules/IM).
- **Borrow-worthy patterns** (consistent with the existing reports' "borrows"):
  per-client/per-agent scoping (every MCP gateway has it), Mem0's **OpenMemory
  MCP** shared-memory pattern, **Basic Memory**'s co-managed-Markdown KB shape,
  and conformance to the **agentskills** / **AGENTS.md** / official **MCP
  Registry** standards for portability.
- **Process fix.** Re-run competitive sweeps stars-first across the keyword space
  _and_ as a capability matrix, and include the Chinese ecosystem by default. The
  per-area report shape is good for depth but blind to platform-level and
  geographic competitors — this report is the cross-cutting complement.

## 6. Method & caveats

Two parallel sweeps on 2026-06-20: a stars-first discovery sweep (keyword +
awesome-list + GitHub star-sort, Chinese terms included) and a capability-matrix
sweep (per-capability leaders + multi-category spanners). All headline star
counts were verified via direct GitHub API reads. Caveats: SaaS-registry "stars"
(Glama, mcp.so, Smithery) are server-counts, not repo stars, and are not
comparable; skills-_framework_ mega-repos (obra/superpowers ~233k,
anthropics/skills ~153k) are standards/frameworks, not managers; some counts
remain uncertain where sources conflicted (claude-mem ~66k–83k, Higress org vs
mirror); README "star badges" (e.g. inflated `/topics/claude-code` figures) were
discarded in favour of API reads; Omnara and Crystal are archived/deprecated as
of early 2026.

## Sources

- cc-switch — https://github.com/farion1231/cc-switch
- plugged.in — https://github.com/VeriTeknik/pluggedin-app
- Obot — https://github.com/obot-platform/obot
- cc-connect — https://github.com/chenhg5/cc-connect
- claude-mem — https://github.com/thedotmack/claude-mem
- Mem0 / OpenMemory — https://github.com/mem0ai/mem0
- Basic Memory — https://github.com/basicmachines-co/basic-memory
- claude-code-router — https://github.com/musistudio/claude-code-router
- claude-code-templates — https://github.com/davila7/claude-code-templates
- opcode (ex-Claudia) — https://github.com/winfunc/opcode
- ruler — https://github.com/intellectronica/ruler · rulesync — https://github.com/dyoshikawa/rulesync
- MCPJungle — https://github.com/mcpjungle/MCPJungle · MetaMCP — https://github.com/metatool-ai/metamcp · ToolHive — https://github.com/stacklok/toolhive · Director — https://github.com/director-run/director
- Discovery lists — https://github.com/e2b-dev/awesome-mcp-gateways · https://github.com/hesreallyhim/awesome-claude-code
