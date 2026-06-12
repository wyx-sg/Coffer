# ADR-014：信封加密的凭据存储

**状态**：Accepted
**日期**：2026-06-12
**决策者**：Yuxing Wu
**相关**：`.specify/memory/constitution.md`（凭据不变量——已修订至 v0.2.0）、spec `001-mcp-gateway`（data-model：`credentials` 表、审计事件）、[ADR-008](ADR-008-distribution-pyinstaller-tauri-sidecar.md)（未签名的 macOS 分发）

## 背景

Coffer 最初把每个注册的密钥直接存入操作系统钥匙串（macOS Keychain、Windows
Credential Manager、Linux Secret Service），daemon 是唯一的钥匙串所有者，
`keyring` 被限制在单个适配器内。

在 macOS 上，这一方案在日常使用中崩溃了。钥匙串把每个条目的访问控制列表（ACL）
绑定到创建它的二进制的 **cdhash**。Coffer 的 daemon 以**未签名**方式分发
（[ADR-008](ADR-008-distribution-pyinstaller-tauri-sidecar.md) 推迟了需要付费 Apple
Developer 账户的 Apple 公证）。每次重新构建 daemon 都会产生新的 cdhash，于是
macOS 把新二进制视为不同的应用，并**重新弹窗请求钥匙串访问——每个密钥一次，每次
重新构建都如此**。对于迭代 Coffer 的开发者，甚至只是收到一个更新版本的用户，这就
是一整面模态密码弹窗墙。

弹窗本身唯一真正的修复是一个**稳定的代码签名身份**：付费的 Apple Team ID 签名能让
cdhash 绑定的 ACL 在多次重新构建间保持有效。对一个免费、开源、自分发的工具来说，
这是一条死路——我们不会把凭据体验卡在一个付费 Apple 账户上。

因此，把钥匙串作为主要密钥存储是错误的默认。我们需要一个在未签名二进制下零弹窗即可
工作的密钥存储，同时仍为想要更强防护的用户提供钥匙串级别的加固。

## 决策

**改用信封加密：把密钥以 Fernet 密文形式存于 SQLite，并默认将单个 Fernet 主密钥保存在
数据库旁的 `0600` 文件中（操作系统钥匙串 opt-in）。**

- **静态密文。** 密钥只以 Fernet 密文形式存于 `~/.coffer/coffer.db` 的 `credentials`
  表中。明文仅在解密与拉起子进程/注入 header（消费密钥处）之间存在于内存——永不进入
  日志、审计或结构化事件（原有不变量保持不变）。
- **主密钥，两个位置，恰好一个生效。** Fernet 主密钥存在于
  `~/.coffer/master.key`（`0600` 文件——**默认**，零钥匙串弹窗）**或**操作系统钥匙串
  （service `coffer`，ref `master-key`——通过 设置 → 安全 或
  `coffer credentials storage --set keychain` opt-in；macOS 每次 daemon 启动至多弹窗
  一次）。
- **file-first、崩溃安全的解析。** daemon 先解析密钥文件，再找钥匙串。迁移**只移动主
  密钥**，并**最后**删除旧副本，因此被中断的迁移总能解析回一个可用状态。我们**搬移密钥，
  从不重新加密数据**：切换存储模式时密文列原封不动——代码少得多、没有批量重新加密窗口、
  切换中途也没有东西会损坏。
- **fail-closed 启动。** 只有当 `credentials` 表为**空**时才生成新主密钥。存在密文但无
  可解析密钥是一个致命且可操作的启动错误（`MasterKeyMissing`）—— Coffer 宁可拒绝启动，
  也不会悄然丢失对现有密钥的访问。
- **一次性 legacy 迁移。** 启动时 daemon 运行尽力而为的迁移：把被已注册资源引用的 legacy
  钥匙串密钥加密写入存储，按 ref 以 `credential_migrated` 审计。钥匙串被锁定则跳过，下次
  启动重试。
- **接口与审计变化。** `/api/v1/keychain` → `/api/v1/credentials`（POST、GET/{ref}、
  GET/{ref}/exists、DELETE/{ref}）；新增 `GET/PUT /api/v1/settings/credentials` 切换
  `master_key_storage`（`"file"` | `"keychain"`，PUT 触发迁移并审计
  `master_key_relocated`）。CLI `coffer keychain …` → `coffer credentials …`，并新增
  `coffer credentials storage [--set file|keychain]`。审计事件 `credential_set` /
  `_read` / `_deleted` / `_migrated` 与 `master_key_relocated`（legacy `keychain_*`
  仍可渲染）。`keyring` 仍被限制在 `coffer.infrastructure.credentials`（importlinter
  Contract 4 不变），现在只服务于主密钥与 legacy 迁移。daemon 仍是密钥材料的唯一所有者；
  CLI 与 web 都走 HTTP API。

这需要修订章程的凭据不变量（v0.1.0 → v0.2.0）：从「仅凭据模块访问操作系统钥匙串；DB
中无明文」改为「密钥只以 Fernet 密文形式存于 `credentials` 表；主密钥由
`coffer.infrastructure.credentials` 独占管理，文件默认 / 钥匙串 opt-in」。

## 影响

**正面**

- **默认零钥匙串弹窗**，即便在未签名、频繁重新构建的 daemon 下也是如此——原始问题消失了。
- 钥匙串模式下**每次 daemon 启动至多弹窗一次**，且只为单个主密钥——而非每个密钥一次。
- **诚实且可改进的威胁模型。** 默认模式把主密钥放在数据库旁，即与此前同样的 `~/.coffer/`
  边界，本就把能读取该目录的人排除在外——没有退化。钥匙串模式是实打实的提升：它防范对
  `~/.coffer/` 内容的离线窃取。
- **崩溃安全的存储切换**，没有重新加密窗口。

**负面 / 新增义务**

- **备份注意。** `coffer.db` 现在装的是密文；恢复它需要配套的 `master.key`（钥匙串模式下
  则是钥匙串条目）。用户必须把主密钥与数据库一起备份，文档必须写明这一点。
- 需要携带**章程修订**（v0.2.0）与一次性 legacy 迁移路径，二者随本次变更一起发布。
- **默认模式不防范能读取 `~/.coffer/` 的人**——密钥就在数据旁。这与此前的边界相同，明白
  写出来，免得有人对默认模式过度信任。

## 备选方案

**继续按密钥逐个存钥匙串，并加上代码签名。** 否决。cdhash 重新弹窗唯一的修复是稳定的签名
身份，而这需要付费 Apple Team ID。对一个免费自分发的工具，我们不会把凭据体验卡在付费
Apple 账户上。信封加密无需任何签名依赖即可消除弹窗。

**切换存储模式时重新加密所有密文。** 否决。只搬移主密钥（文件 ↔ 钥匙串）是一个极小、崩溃
安全的操作；重新加密每一行会引入一个带半迁移失败模式的批量重写窗口，代码多得多，却没有任何
安全收益——两边的数据密钥本就是同一个。

**从用户口令派生密钥（不存储密钥）。** 在默认模式下否决。它会在每次 daemon 启动时重新引入
一个弹窗（口令），违背零弹窗目标，而且口令一旦遗忘就无法恢复。钥匙串 opt-in 已覆盖那些希望
密钥不落在磁盘上的用户。

**保持钥匙串为默认，文件为 opt-in。** 否决。那会让最常见的开发者平台上的开箱体验仍是那面
重新弹窗墙。在未签名二进制下能无痛工作的模式必须是默认；加固才是 opt-in。
