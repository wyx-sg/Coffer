# 竞品调研 —— 多机配置 / 状态同步

> 中文版：本文件 · English: [multi-machine-sync.md](./multi-machine-sync.md)
>
> 面向 Coffer 多机同步（spec 010，ADR-016）的内部竞品调研报告。**日期：** 2026-06-16。
> **方法：** deep-research harness。**来源说明：** 本轮在核验中途撞到 API 会话上限——1 条
> claim（整文件加密支持）经 3-0 确认；其余为项目文档一手来源但未复核。请做轻量复核。

## 1. 全景速览

跨机配置同步按**传输**和**是否理解所搬运的内容**分类：

| 类别               | 传输            | 理解内容？          | 例子                                             |
| ------------------ | --------------- | ------------------- | ------------------------------------------------ |
| **Dotfile 管理器** | 用户的 git repo | 文件级（复制/模板） | chezmoi、yadm、dotbot、GNU Stow、rcm、vcsh       |
| **厂商设置同步**   | 厂商云          | 应用专属            | VS Code Settings Sync、JetBrains Backup & Sync   |
| **AI 配置同步**    | git + symlink   | 文件级              | AIS（ai-rules-sync）；rulesync（生成器，非同步） |
| **资源对账器**     | 用户的 git repo | **语义（对账）**    | **Coffer**                                       |

### 各玩家

- **chezmoi** —— 黄金标准。源状态在一个 git repo；**按机器差异经 Go `text/template`**
  （`.chezmoi.hostname`、`.chezmoi.os` 条件），机器本地数据在
  `~/.config/chezmoi/chezmoi.{toml,yaml,json}`；**整文件加密经四种后端（age、git-crypt、gpg、
  transcrypt）**——加密文件以 ASCII-armored 密文形态（`encrypted_` 属性）传输，仅本地解密；
  密码管理器集成（`onepasswordDocument`）在*应用*时取密钥而非存进源状态。[chezmoi.io]
- **yadm** —— GPG（默认）/ OpenSSL 加密 glob 匹配的文件，打包进单个提交的归档
  （`~/.local/share/yadm/archive`），经显式两步 `yadm encrypt` / `decrypt`。[yadm.io]
- **git-crypt** —— git repo 内透明的逐文件加密（公私混合）；密钥分发经 GPG 用户或一个
  **带外导出的对称密钥**——从不提交。[github.com/AGWA/git-crypt]
- **AIS（`ai-rules-sync`）** —— 最接近的 AI 专用同类：经 **git repo + 软链接进项目**同步
  agent 规则/skills/命令/子agent（git 为传输 + symlink 物化，非文件复制）。[github.com/lbb00]
- **rulesync** —— 一个配置*生成器*，不是同步工具；多机一致性依赖外围 git repo。**MCPM** ——
  全局配置，**无跨机同步**。**VS Code Settings Sync / JetBrains** —— 厂商云，非用户自有。
- 确认：chezmoi 对比的六个 dotfile 工具中，**只有 chezmoi 和 yadm 支持整文件加密**
  （dotbot、rcm、vcsh、裸 git 不支持）。[3-0 确认]

## 2. 能力对比

| 能力           | chezmoi         | yadm     | git-crypt | AIS      | VS Code Sync | **Coffer**             |
| -------------- | --------------- | -------- | --------- | -------- | ------------ | ---------------------- |
| 传输           | 用户 git        | 用户 git | 用户 git  | 用户 git | 厂商云       | **用户 git**           |
| 理解内容       | 模板            | 文件     | 文件      | symlink  | 应用         | **语义对账**           |
| 按机器模板     | ✅ 杀手锏       | 部分     | ❌        | ❌       | 部分         | **❌ 每机器=全量状态** |
| 密钥处理       | age/gpg/PM 引用 | gpg 归档 | 透明      | ❓       | 云           | **✅ Fernet 仅密文**   |
| 主密钥带外     | ✅              | ✅       | ✅        | —        | n/a          | **✅ 从不同步**        |
| 每机器全量状态 | ✅              | ✅       | ✅        | ✅       | ✅           | **✅（无中心 SoR）**   |
| 对账 vs 覆盖   | 覆盖            | 覆盖     | 覆盖      | symlink  | 覆盖         | **对账**               |
| 感知 AI agent  | 经模板          | ❌       | ❌        | ✅       | ❌           | **✅ 原生**            |

## 3. Coffer 对比

**Coffer 独特之处。**

1. **对账而非覆盖确实独一无二。** 每个 dotfile 管理器都在*文件*级应用（复制或模板渲染到目标）。
   Coffer 镜像 knowledge/memory/skills _文件_，但通过资源服务对账配置*资源*——语义合并，而非盲目
   覆盖。无受访工具对结构化配置做语义对账。
2. **仅密文 + 主密钥带外匹配最佳实践。** 这正是 chezmoi/yadm/git-crypt 模型（age/gpg，密钥从不
   进 repo）。Coffer 与黄金标准对齐——是验证，不是缺口。
3. **git 为传输、每机器全量状态**匹配 dotfile 哲学（repo 是历史/传输，不是真相系统）。

**Coffer 落后 —— 具体借鉴。**

1. **无按机器模板（最大缺口）。** chezmoi 的定义性功能是 `.chezmoi.hostname` / `.chezmoi.os`
   条件 + 机器本地数据，让每台机器可不同（工作 vs 个人路径、装的 agent 不同）。Coffer 的"每机器
   持有全量状态"对真实多机场景过于僵硬。借鉴按机器覆盖/条件。
2. **单一介质 = git。** 有意且无妨，但 chezmoi/Syncthing 提供替代；作为有意识约束记录。
3. **应用时的提供者引用。** chezmoi 的 `onepasswordDocument` 在应用时从外部管理器取密钥——与
   凭证报告的外部提供者引用借鉴相连。

## 4. 给 Coffer 的关键结论

1. **以对账而非覆盖作为头条** —— 这是没有 dotfile 管理器做到的一点，也是跨机结构化配置的正确模型。
2. **加入按机器模板/覆盖**（chezmoi `.hostname`/`.os` 模型）——最清晰的功能缺口；"每机器=相同
   全量状态"对合理地按机器不同的真实场景会失效。
3. **你的仅密文 + 带外主密钥设计是最佳实践**——保持；它匹配 chezmoi/yadm/git-crypt。
4. **AIS（`ai-rules-sync`）是最接近的 AI 专用同类**（git + symlink）；你的资源对账比 symlink
   物化更稳健。

## 5. 来源

一手：

- chezmoi.io —— comparison-table、user-guide/encryption（age）、manage-machine-to-machine-differences
- yadm.io/docs/encryption
- github.com/AGWA/git-crypt
- github.com/lbb00/ai-rules-sync（AIS）
- github.com/dyoshikawa/rulesync · github.com/pathintegral-institute/mcpm.sh
- VS Code Settings Sync 文档 · JetBrains Backup & Sync 文档

## 核查更新（2026-06-19）

> 针对 2026-06-16 来源说明所标记的四条 claim（1 条本地头条 claim + 3 条 web claim）做
> 轻量核查，并对 chezmoi 加密后端清单做了独立复核。全部成立，无需修正。

**导语：** 所有目标 claim 均经一手来源确认——而对账而非覆盖这一头条差异点是在**代码中已实现**，
并非仅停留在规格层面。

### ✅ 已确认

- **对账而非覆盖确有其事，并非空想。** 配置资源经与 kind 无关的资源服务按 `(kind, name)` 对账
  ——已存在的走 `update_config` + `set_enabled`，新增的走 `register`，上游删除的走 `delete`
  ——绝非对文件的盲目覆盖。`update_config` 会重新校验配置、探测凭证引用并运行各 kind 的跨版本
  钩子，因此这是一次经校验、感知 kind 的对账。[`backend/coffer/application/sync/importer.py:71-110`；
  `backend/coffer/application/resource_service.py:206-243`；ADR-016；spec 010]
- **chezmoi 整文件加密经四种后端**——age、git-crypt、gpg、transcrypt；加密文件以
  ASCII-armored 形态存于源目录并带 `encrypted_` 属性，仅在需要时自动解密。
  https://github.com/twpayne/chezmoi/blob/master/assets/chezmoi.io/docs/user-guide/encryption.md
- **chezmoi 按机器模板**经 Go `text/template`，以 `.chezmoi.hostname` / `.chezmoi.os`
  条件实现；机器本地 `[data]` 存于 `~/.config/chezmoi/chezmoi.{toml,yaml,json}`。
  https://www.chezmoi.io/user-guide/manage-machine-to-machine-differences/
- **chezmoi `onepasswordDocument`** 在*应用*时从 1Password 取文档（按 uuid 缓存输出）；
  密钥留在 1Password，而非进入 dotfiles。
  https://www.chezmoi.io/reference/templates/1password-functions/onepassworddocument/
- 在受访的 dotfile 工具中，**只有 chezmoi 和 yadm 支持整文件加密**；dotbot、rcm、vcsh 与裸
  git 不支持（chezmoi 对比表中分别为 `✅`/`❌`）。https://www.chezmoi.io/comparison-table/
- **AIS（`ai-rules-sync`）** 跨众多 agent（Cursor、Claude Code、Copilot、OpenCode、
  Trae AI、Codex、Gemini CLI、Warp）同步 AI 规则/skills/命令/子 agent——在 git repo 中管理
  规则，并经软链接物化进项目（默认目标 `.cursor/rules/`、`.github/instructions/`）——确认是
  git + symlink 而非文件复制。https://github.com/lbb00/ai-rules-sync

### ✏️ 已修正

- **属补充说明，并非事实修正（§3.1）：** 三方*内容*合并发生在 git/YAML 文本层（确定性序列化
  ——每个资源一份 YAML、键排序、时间戳归一化、剥离仅本地字段——使 diff 可合并）；importer 随后
  把本地 SQLite 库对账*到*已合并的工作区。报告"语义合并而非盲目覆盖"的表述成立；合并与对账是两个
  不同的层。[ADR-016；`backend/coffer/application/sync/importer.py:71-110`]
- chezmoi 的 **FAQ** 加密页只列出 age/gpg/rage，但 **user-guide/encryption** 页列出了全部
  四种后端，与报告一致——四后端 claim 应引用 user-guide 而非 FAQ。
  https://github.com/twpayne/chezmoi/blob/master/assets/chezmoi.io/docs/user-guide/encryption.md
