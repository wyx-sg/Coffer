# 竞品调研 —— Agent 与 MCP 的凭证与密钥管理

> 中文版：本文件 · English: [credentials-secrets.md](./credentials-secrets.md)
>
> 面向 Coffer 凭证库（constitution 原则；ADR-015）的内部竞品调研报告。**日期：** 2026-06-16。
> **方法：** deep-research harness。**来源说明：** 本轮在核验时撞到 API 会话上限，故 claim 未能
> 经投票复核——但它们取自一手厂商文档（1Password、ToolHive、Infisical、Vault），反映有充分记录
> 的行为。对外引用前请做轻量复核。

## 1. 全景速览

agent/MCP 的密钥管理跨四种姿态：

| 姿态               | 密钥在哪              | 配置如何引用           | 例子                              |
| ------------------ | --------------------- | ---------------------- | --------------------------------- |
| **本地加密库**     | 加密文件 + OS keyring | spawn 时注入           | ToolHive（Encrypted）、**Coffer** |
| **托管密钥管理器** | 厂商保险库            | `op://` / `${ref}` URI | 1Password、Infisical、Doppler     |
| **企业保险库**     | 服务端（动态）        | API / agent 注入       | HashiCorp Vault                   |
| **配置内加密**     | git repo 本身         | 内联密文               | SOPS+age、git-crypt               |

### 各玩家

- **1Password** —— "访问而不暴露"的参考设计。密钥经 **`op://<vault>/<item>/[section/]<field>`**
  URI 引用，从不内联。**`op run`** 扫描 env 中的 `op://` 引用、解析、在子进程中以 env 变量运行
  命令，进程退出即消失（spawn 时物化）。`.mcp.json` 用 `${VAR}` 占位符，使配置可安全版本控制。
  1Password 的明确政策是**不经 MCP 暴露原始凭证**；在 1Password + Runlayer 集成中密钥留在保险库
  而 MCP 控制面**只存引用**，注入经 **HTTP header 注入**（在传输 header 中解析 `op://`，明文仅在
  请求期间在内存）。[1password.com/blog；developer.1password.com]
- **ToolHive** —— 三个密钥提供者（**Encrypted** 本地默认、**1Password** 只读、**Environment**
  只读），同时只一个生效。Encrypted 提供者本地存密文，并**从存在 OS keyring 的密码派生其密钥**
  （Keychain / Credential Manager / dbus）。注入是 `thv run --secret <name>,target=<ENV_VAR>`。
  [docs.stacklok.com/toolhive]
- **Infisical** —— 开源（MIT）可自托管密钥管理器；密钥引用经插值（`${KEY}`、`${dev.KEY}`、
  `${prod.frontend.KEY}`）；自带 MCP server。[infisical.com/docs]
- **HashiCorp Vault** —— BSL 源可见；**动态、短时凭证**（如临时数据库凭证）——轮换的黄金标准。
- **SOPS + age / git-crypt** —— 加密 repo 中*配置文件内的密钥值*（键明文、值密文）；加密密钥带外引导。
- **mcp-auth-proxy** —— 置于 MCP server 前的 drop-in OAuth 2.1/OIDC 网关；把身份委托给
  Google/GitHub/Okta/Auth0/Azure AD/Keycloak 而非自存凭证，带可选共享密码回退。[github.com/sigbit/mcp-auth-proxy]

## 2. 能力对比

| 能力                | 1Password           | ToolHive        | Infisical   | Vault       | **Coffer**                      |
| ------------------- | ------------------- | --------------- | ----------- | ----------- | ------------------------------- |
| 静态密钥            | 保险库（云/自托管） | 加密本地        | 保险库      | 服务端      | **Fernet 密文、本地表**         |
| 配置存引用（非值）  | ✅ `op://`          | ✅ 名称         | ✅ `${}`    | ✅ 路径     | **✅ 凭证引用**                 |
| 拒绝内联密钥        | （惯例）            | —               | —           | —           | **✅ 模式拒绝内联**             |
| spawn 时物化        | ✅ `op run`         | ✅ `--secret`   | ✅          | ✅          | **✅ 上游 spawn 时**            |
| Header 注入（HTTP） | ✅ Runlayer         | —               | —           | —           | **✅ 用于 http 传输**           |
| 主解锁模型          | 账号                | OS keyring 密码 | 账号        | unseal      | **0600 文件 / OS keyring 可选** |
| 轮换 / 动态密钥     | 轮换                | —               | **✅ 动态** | **✅ 动态** | **❌ 静态**                     |
| 外部提供者引用      | n/a（本身即是）     | ✅ 1Password    | n/a         | n/a         | **❌ 仅自有库**                 |
| 共享 / 团队         | ✅                  | 部分            | ✅          | ✅          | **❌ 单用户**                   |
| 本地优先 / 自托管   | 部分                | ✅              | ✅          | ✅          | **✅ 严格**                     |
| 单一拥有者隔离      | —                   | —               | —           | —           | **✅ 仅 daemon 访问**           |

## 3. Coffer 对比

**Coffer 与最佳实践齐平——或更强之处。**

1. **Coffer 已实现 1Password 的"访问而不暴露"理想。** 配置存引用（从不存值）、仅 spawn 时物化、
   HTTP 传输的 header 注入、审计/日志/同步里仅密文——_正是_ 1Password 倡导（且 ToolHive 实现）的
   模型。Coffer 站在业界安全论点的正确一侧。
2. **拒绝内联密钥是真实加分。** Coffer 主动拒绝 MCP 配置里像密钥的内联值并强制走引用——多数工具
   靠惯例；Coffer 强制执行。
3. **daemon 单一拥有者是比多数更强的隔离。** 单一写者、所有界面只经 daemon API 触达密钥，胜过典型
   的"任何 CLI 进程都能读库"模型。
4. **本地优先加密库 + OS-keyring 保护的主密钥**镜像 ToolHive 的 Encrypted 提供者——与最佳本地
   设计齐平。

**Coffer 落后 —— 具体借鉴。**

1. **无外部提供者引用（最大借鉴）。** 1Password（`op://`）、ToolHive（1Password 提供者）、
   Infisical 让配置指*进*已有保险库。Coffer 只在自有表存密钥。加一个提供者引用方案，让 Coffer 凭证
   引用能从 1Password / Infisical / Vault 解析——已经在跑保险库的用户不该把密钥复制进 Coffer。
2. **无轮换 / TTL。** Vault 发动态短时凭证；Coffer 的是静态。加轮换钩子 / 过期，至少过期时重新提示。
3. **无共享 / 团队 / 动态密钥** —— 有意的单用户范围；有意识地记录。

## 4. 给 Coffer 的关键结论

1. **你已实现业界的"访问而不暴露"理想** —— 引用 + spawn 时物化 + 处处密文 + 拒绝内联密钥。作为头条；
   这是优势，不是缺口。
2. **最大借鉴：外部提供者凭证引用**（`op://` 风格），让 Coffer 引用能从 1Password / Infisical /
   Vault 解析，而非强迫把密钥复制进 Coffer 的库。
3. **加入轮换 / TTL 钩子**（受 Vault 启发）应对会过期的凭证。
4. **保留 daemon 单一拥有者 + 拒绝内联密钥** —— 二者都比业界常态更强。

## 5. 来源

一手：

- developer.1password.com/docs/cli/secret-references · /docs/cli（op run）
- 1password.com/blog —— securing-mcp-servers-with-1password、where-mcp-fits-and-where-it-doesnt、secure-mcp-credentials-1password-runlayer
- docs.stacklok.com/toolhive/guides-cli/secrets-management
- infisical.com/docs/documentation/platform/secret-reference
- developer.hashicorp.com（Vault 动态密钥）· getsops.io · github.com/AGWA/git-crypt
- github.com/sigbit/mcp-auth-proxy

## 核查更新（2026-06-19）

> 轻量复核（2026-06-16 那轮在投票核验前撞上会话上限）。四项受检 claim 均与一手来源相符，无一需要
> 实质性修正。

### ✅ 已确认

- **Coffer 仅存密文 + "访问而不暴露"。** `EncryptedCredentialStore` 仅以 Fernet 密文形式把密钥
  存进 SQLite 的 `credentials` 表——`set()` 加密、`get()` 仅解密进内存、`exists()` 是从不解密的
  存在性探测。模块 docstring："明文仅在解密与消费它的 spawn 之间存在于内存。密文列从不进入日志或
  审计行。" ADR-015（2026-06-12 已接受）重申"静态密文……从不进入日志、审计或结构化事件"，主密钥
  默认放在 0600 文件 / 可选 OS keychain（与"主解锁模型"一行相符）。
  [repo:backend/coffer/infrastructure/credentials/encrypted_store.py;
  repo:docs/decisions/ADR-015-envelope-encrypted-credential-store.md]
- **1Password `op run` 在 spawn 时物化。** 文档："载入指定的密钥，然后在子进程中运行所给命令，密钥
  仅在进程存续期间作为环境变量可用。"它解析 `op://` 引用并注入子进程；值不会持久化到 shell env 或
  磁盘。https://www.1password.dev/cli/secrets-environment-variables/
- **1Password + Runlayer 的 header 注入。** 博客（原文）："凭证仅存在于客户的 1Password 保险库。
  Runlayer 只存引用，从不存原始值。"以及："当 MCP 代理处理一次工具调用时，它会扫描传输 header 中的
  `op://` 引用。每命中一个，就调用 1Password SDK 解析出实时值并注入上游连接。"明文仅在请求期间留在
  内存；磁盘或网关数据库上无任何持久化。发布于 2026-03-17。
  https://1password.com/blog/secure-mcp-credentials-1password-runlayer
- **许可证姿态。** Infisical 核心默认为 MIT（Expat）；任何 `ee/` 目录下的内容受单独的企业许可证
  约束。HashiCorp Vault 为 BSL/BUSL 1.1（源可见），2023 年 8 月采用（由 MPL 2.0 变更而来）；在
  Change Date / 发布满 4 周年时转为开源。
  https://raw.githubusercontent.com/Infisical/infisical/main/LICENSE;
  https://www.hashicorp.com/en/blog/hashicorp-adopts-business-source-license

### ✏️ 已修正

- **出处："spec 015" → ADR-015 + spec 001-mcp-gateway。** 抬头引用了"spec 015 / ADR-015"；ADR
  确实存在，但并无 `specs/015-*` 目录。凭证功能由 ADR-015 加 spec 001-mcp-gateway 记录（credentials
  表、审计事件）。不影响该 claim 的实质。
  [repo:docs/decisions/ADR-015-envelope-encrypted-credential-store.md]
