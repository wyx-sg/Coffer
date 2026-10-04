---
title: 安全策略
description: 如何私下报告 Coffer 的漏洞、报告里要写什么、会得到怎样的回应，以及每一次代码改动都必须遵守的安全不变量。
---

# 安全策略 {#security-policy}

本页有两类读者。如果你发现了漏洞，前半部分告诉你如何私下报告。如果你在修改 Coffer 的代码，后半部分列出你的改动必须保持的安全不变量。威胁模型以及各项防护如何配合，请读[安全模型](/zh/architecture/security)。

## 报告漏洞 {#reporting-a-vulnerability}

::: danger 不要开公开 issue
永远不要在公开的 GitHub issue、discussion 或 pull request 中报告安全问题。
:::

请使用以下私密渠道之一：

1. **GitHub 私密漏洞报告**（首选）。在 [github.com/wyx-sg/Coffer/security/advisories/new](https://github.com/wyx-sg/Coffer/security/advisories/new) 提交报告，或者使用仓库 Security tab 上的 **Report a vulnerability**。你需要登录 GitHub。
2. **发邮件**给维护者：[hutwyx@gmail.com](mailto:hutwyx@gmail.com)。如果你有维护者的 PGP 公钥，请用它加密。非严重问题用明文也可以。

### 报告里要写什么 {#what-to-include}

- 受影响的提交或版本。
- 复现步骤：最小化的环境和相关的日志片段。
- 你对影响的评估。
- 建议的缓解措施（如果有的话）。

### 你会得到怎样的回应 {#what-to-expect}

| 步骤 | 目标 |
| --- | --- |
| 确认收到 | 72 小时内 |
| 分类与首次回复 | 7 天内 |
| 修复与披露时间表 | 逐案商定，通常 30 到 90 天 |

Coffer 处于 1.0 之前，只有一位维护者，所以这些时间是尽力而为，不是有保证的 SLA。

### 支持的版本 {#supported-versions}

只支持 `main`。修复进入 `main`，并在下一个发布版本中交付。旧版本不会收到回移的安全修复。

## 贡献者须遵守的安全不变量 {#security-invariants-for-contributors}

这些规则来自[原则](/zh/architecture/principles)，它的优先级高于项目的其他所有文档。破坏其中一条不是风格问题：在任何代码依赖它之前，需要先对原则提出修正案，并在单独的 pull request 中提出并达成一致。

### 守护进程只监听回环地址 {#the-daemon-listens-on-loopback-only}

HTTP API 只绑定 `127.0.0.1`，别无其他。每个读取或修改保险库状态的路由器都声明了 `require_token` 依赖，所以它的请求必须在 `X-Coffer-Token` 中携带 API 令牌。只有就绪探针 `GET /api/v1/daemon/status` 不需要令牌就会响应。令牌在每次守护进程启动时生成，发布在以 `0600` 权限写入的 `~/.coffer/daemon.json` 中。每个路由前面还有一道防护，拒绝任何 `Host` 头不是守护进程端口上的 `127.0.0.1`、`localhost` 或 `[::1]` 的请求。这项检查挫败了 DNS rebinding，即网页把自己的主机名重新解析到 `127.0.0.1` 的攻击。同一道防护还拒绝任何 `Origin` 不属于 Coffer 自身的请求：守护进程的 Web 来源、桌面应用，或者显式启用的开发来源。

贡献时：

- 永远不要添加会把守护进程暴露到回环地址之外的绑定地址、参数或设置。
- 给每个新路由器加上 `dependencies=[Depends(require_token)]`，永远不要让某个路由或监听器绕过 Host 和 Origin 防护。
- CORS 不是安全边界，放宽它也不会授予任何权限。令牌才是边界。不要把来源检查当作认证。

### 密钥只以密文形式存在 {#secrets-exist-only-as-ciphertext}

密钥只以 Fernet 密文形式存在，每个密钥一个文件（`~/.coffer/vault/secret/<ref>.enc`，本机专属的则在 `local/secret/`）。明文只在解密到被进程启动或请求头注入消费之间存在于内存中。

- 在任何其他表、配置文件、资源 spec 或 API 响应中，只存**密钥引用**，永远不存密钥本身。
- 永远不要让明文进入数据库、日志行、审计日志或任何结构化事件。留意可能包含请求头或环境变量块的异常消息和 `repr`。
- Fernet 主密钥只由 `coffer.infrastructure.secret` 管理，放在由构建选择的存储端口之后：签名的发布版把它保存在只有 Coffer 签名二进制才能读取的钥匙串访问组中；开发构建把它保存在数据库旁边一个 `0600` 文件里，或者在用户选择时保存在操作系统钥匙串里。它永远不会进入保险库发布出去的任何东西，比如同步远端。它到达另一台机器的唯一途径，是桌面应用在在场验证之后写出的密钥备份，以及**设置 › 安全 › 导入主密钥**。
- 没有任何路由、命令或 MCP 工具返回密钥明文或主密钥。唯一的例外是桌面应用经过在场验证的查看和密钥备份，以及 `coffer run` 对独立 `secret/` 名称的解析。任何新的返回值路径都是缺陷，无论它如何被审计（[安全模型](/zh/architecture/security)）。
- 密钥材料只以密文形式离开本机，而且只在用户明确要求时。

`secrets-scan` CI job 会用 gitleaks 扫描完整的 git 历史。提交过的密钥即使在后来的提交中删除，也会让 pull request 失败。在测试和 fixture 中使用明显是假的值。

### `keyring` 被限制在固定范围内 {#keyring-stays-confined}

只有 `backend/coffer/infrastructure/secret/keyring_adapter.py` 导入 `keyring`。其他所有模块传递的都是密钥引用。`backend/pyproject.toml` 中的 import-linter 契约强制执行这一点（"keyring confined to infrastructure"、"CLI does not access the keychain directly"），`make lint` 会运行它们。不要为了绕过它们而添加 `ignore_imports` 豁免，把需求交给密钥模块去处理。

### 访问用户提供的 URL 的出站请求要经过 SSRF 防护 {#outbound-requests-to-user-supplied-urls-go-through-the-ssrf-guard}

`coffer.infrastructure.net.ssrf_guard.check_url` 解析 URL 的主机，并拒绝回环、私有、链路本地和运营商级 NAT 目标。提供商编辑器在保存任何东西之前运行的探测（列出模型、测试连接）都用它校验 base URL。用户自己配置的端点（HTTP MCP 上游、模型和转写调用、IM 平台、同步远端）在 Coffer 使用它们时不受此限制，因为在那里回环或局域网端点是合法目标（[原则 → 网络默认值](/zh/architecture/principles)）。当你添加让守护进程获取用户提供的 URL 的代码时，先用 `check_url` 校验它。这道防护不会把解析出的地址一直固定到 HTTP 客户端，所以一个做 DNS rebinding 的主机可能先通过校验，之后再解析到别处。对于一个单用户、只监听回环地址、URL 都来自自己用户的守护进程，这个残余风险是可以接受的。

### 用户内容留在本机 {#user-content-stays-on-the-machine}

所有保险库状态都在用户的机器上。云服务只作为模型和工具的提供方，永远不是记录系统。唯一的例外是同步到用户自己的 git 远端的保险库同步：默认关闭，密钥只以密文形式存在，远端被视为一个可以从任意一台机器重建的汇合点。任何把保险库内容发送到其他远程服务的功能，都需要修正原则。

### 来自用户和智能体的路径要经过防护 {#paths-from-users-and-agents-are-guarded}

知识路径经过同一道路径穿越防护 `infrastructure/knowledge/paths.py`，它拒绝空的、全是点的、隐藏的或其他不安全的路径段。当你添加一个把用户或智能体提供的字符串转换为文件系统路径的端点时，让它经过所属模块的防护，而不是自己拼接路径。

## 安全相关改动的检查清单 {#checklist-for-a-security-relevant-change}

- [ ] 没有新增绕过令牌和主机检查的监听器、绑定地址或路由。
- [ ] 密钥只存在于密钥存储的密文文件（`vault/secret/<ref>.enc`）中：表、日志、审计日志和 API 响应里都没有。
- [ ] 密钥模块之外没有新增 `keyring` 导入，也没有新增 import-linter 豁免。
- [ ] 用户提供的出站 URL 都经过 SSRF 防护校验。
- [ ] 用户或智能体提供的路径都经过路径穿越防护。
- [ ] 测试使用假密钥，`make verify` 为绿，包括 `lint-imports`。
- [ ] pull request 描述写明了改动涉及的原则，并解释了改动为什么遵守了它。

## 相关 {#related}

- [安全模型](/zh/architecture/security)
- [密钥存储指南](/zh/guides/secret-store)
- [设计原则](/zh/architecture/design-principles)
- [`SECURITY.md`](https://github.com/wyx-sg/Coffer/blob/main/SECURITY.md)
