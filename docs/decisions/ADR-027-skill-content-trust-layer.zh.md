# ADR-027 —— Skill 内容信任层（启发式扫描，警告而非拦截）

> English: [ADR-027-skill-content-trust-layer.md](./ADR-027-skill-content-trust-layer.md)

- **状态：** Accepted
- **日期：** 2026-06-19
- **决策者：** Yuxing Wu
- **Spec：** [005-skill-manager](../../specs/005-skill-manager/spec.zh.md)（FR-028、FR-029）

> **修订（2026-06-20，简化 4.3）。** Skill Git-fetch 已移除；扫描层现在只覆盖本地导入、adopt 与就地文件编辑。

## 背景

竞品调研（[`docs/research/agent-skills.md`](../research/agent-skills.md)）判定
**信任层是 #1 最高杠杆缺口**：整个 skill 生态没有内建沙箱或签名，真正的威胁是 skill
携带的 **bundled 脚本**（OWASP "Agentic Skills Top 10"、Snyk ToxicSkills、以及一个绕过
Anthropic 全部扫描器的恶意文件）。Coffer 加固了**抓取**（SSRF guard、shallow clone、
体积上限、中和仓库 hooks——抓取功能已在简化 4.3 中移除），却从未看过**内容**。对一个以保险库（vault）自我定位的工具，
内容信任天经地义。

一个硬约束决定了可能性边界：**Coffer 只交付 skill，从不运行它们。** 宿主 agent
（Claude Code、Codex……）执行 skill 的脚本，也是唯一能尊重 skill `allowed-tools` 的一方。
因此 Coffer 无法强制运行时行为。它的杠杆在**入库与启用时**：把风险摆上台面，并对"把
skill 授予某 agent"这一动作设卡。

## 决策

加入 **L2 级内容信任层**：启发式扫描 + 警告而非拦截的确认门。

1. **启发式扫描。** 纯 domain 扫描器（`domain/skill/content_scan.py`）遍历 skill 的文本
   文件，套用一组小而有版本号的规则（远程执行管道、网络出口、密钥/凭据访问、危险删除、
   提权、混淆 blob），产出带严重等级的 findings 与一个总体 verdict。它是启发式、非权威的：
   finding 是复查提示，干净报告不是保证。ruleset 带版本号，便于判断存储的 verdict 是否过期。
2. **每次内容进入都扫描。** import、adopt 与就地文件编辑都会重新扫描；verdict、findings 数、ruleset 版本、扫描时间缓存在 skill config 上（无需迁移——`config_json` 不透明）。每次扫描都审计。
3. **警告，不拦截入库。** 有风险的 skill 始终进入主库。过度拦截是错误默认——误报常见、
   干净扫描不等于安全，拦截入库只会训练用户绕过工具，同时给出虚假安心。
4. **对启用设卡，而非入库。** 当 verdict 为 `high`/`critical` 时，为某 agent 启用该 skill
   会被拒绝（`409`），直到用户显式确认风险（审计）。follow/auto-bind 调和器跳过此类 skill
   而非投递。确认是内容范围的：skill 内容变化时即重置。收编是例外——它归并的是 agent
   workspace 中已存在的 skill，拦截会移除 agent 已有的 skill 并拒绝恢复。

## 备选方案

- **L1 —— 仅清单 + 溯源。** 呈现脚本/哈希/声明的 `allowed-tools`/来源，不做风险判断。
  作为目标被否决：把每个脚本留给用户肉眼审。L1 作为 L2 的基础保留。
- **L3 —— 对 critical findings 硬拦入库/启用的策略。** 暂否：在有据的扫描器规避与误报下，
  硬拦会拒掉合法 skill 并给出虚假安心。L3 作为本层之上未来的可选策略保留。
- **运行时强制 `allowed-tools`。** 结构上不可能——Coffer 不执行 skill。我们解析并保留
  `allowed-tools`（与 FR-027 对齐）仅为可读性与未来的不符项 findings。

## 影响

- 用户获得逐 skill 风险信号与可审计的确认轨迹；被标记的 skill 不会被静默投递给每个跟随
  的 agent。
- 扫描是 best-effort、启发式的；它会漏报也会误报。verdict 是建议性的，绝非安全声明。
- 未来工作（roadmap）：发现机制中呈现扫描 findings、`allowed-tools` 与行为不符 findings、
  以及可选的 L3 策略。
