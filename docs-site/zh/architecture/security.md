# 安全

::: warning 安全不变量
以下规则不可妥协，适用于整个代码库。它们由 importlinter 契约、集成测试和架构本身强制执行，而不仅仅是约定俗成。

1. **仅监听 loopback。** HTTP API 只绑定到 `127.0.0.1`。任何面向公网的接口面必须以独立进程运行，并仅限于经过签名校验的回调路径——具体来说就是 SeaTalk 回调监听器（见 [通道与面向公网的接口面](#通道与面向公网的接口面)）。
2. **密钥明文永不落盘。** 密钥只以 Fernet 密文形式存于 `credentials` 表；配置只存储凭据的 _引用_，而不是凭据值本身。明文仅在解密与拉起子进程/注入 header（消费密钥处）之间短暂存在于内存——永不以明文进入 SQLite、日志、审计或任何结构化事件。Fernet 主密钥由 `infrastructure/credentials/` 独占管理，它是唯一被允许 import `keyring` 的位置。
3. **REST API 启用 Token + CORS 鉴权。** 每次管理 API 调用都需要 `X-Coffer-Token` header。daemon token 存储在权限位为 `0600` 的 `~/.coffer/daemon.json` 中。
4. **出站 HTTP 如今已有真实路径；SSRF 防护的缺口仅限于 HTTP 传输的 MCP 客户端。** daemon 如今已会发起出站调用——向 OpenAI 兼容的供应商请求 embeddings、为 sync 执行 `git push`、以及调用 Telegram/SeaTalk API（用裸 httpx 访问固定主机）。章程要求出站 HTTP 必须经过具备 SSRF 防护的客户端；目前仅剩的缺口是 HTTP 传输的 MCP 客户端，它仍使用 MCP SDK 的 httpx 客户端，没有 IP 范围过滤。针对该客户端的受保护 SSRF 防护封装器已列入计划。面向公网的接口面必须以独立进程运行，并仅限于经过签名校验的回调路径。
   :::

## 威胁模型与信任边界

Coffer 是一个单用户、本地优先的工具。其信任模型相应地也很简单：

**可信的**：本地用户。Coffer 假设运行 daemon 的人就是机器的拥有者。没有多租户模型，没有基于角色的访问控制，也没有共享同一台机器的不可信用户这一概念。

**防范的对象**：即使在单用户本地部署中也存在的两类攻击者：

1. **游荡的本地进程。** 同一台机器上的另一个进程——例如项目 `node_modules` 中安装的恶意包，或具有本地 HTTP 访问权限的浏览器扩展——可能尝试读取 Coffer 的数据库、调用其管理 API 或窃取已注册的密钥。loopback 绑定加上 token 鉴权提高了攻击门槛：进程必须猜测或窃取 256 位随机 token 才能调用任何变更型端点。token 不存储在任何环境变量中，只存在于 `~/.coffer/daemon.json`，其权限位为 `0600`（只有所有者可读）。

2. **恶意的上游 MCP 服务器配置。** 一个使用精心构造的 `command` 或 `url` 注册的服务器，可能尝试访问内网服务（SSRF）、通过环境变量泄露凭据，或在工作目录之外写入文件。凭据引用模型（配置中不存储明文密钥）以及静态 `env` 的正则检测（拒绝任何看起来像 token 的 `env` 值）是当前的抵御手段。SSRF 防护出站 HTTP 客户端是根据章程不变量计划中的加固措施。

Coffer（在默认配置下）**不**防范的情况：能够直接读取 `~/.coffer/` 的特权攻击者，或恶意的 Coffer 二进制文件。默认模式下，主密钥位于加密数据库旁的 `0600` 文件中——与此前同样的 `~/.coffer/` 边界，本就把能读取该目录的攻击者排除在外——因此 envelope 加密并未改变这条边界。opt-in 的**钥匙串模式**提高了门槛：主密钥存于操作系统钥匙串后，`~/.coffer/coffer.db` 中的密文对一个仅窃取目录内容、但未同时解锁钥匙串的攻击者毫无用处。已被攻陷的操作系统钥匙串（钥匙串模式下）以及恶意的 Coffer 二进制文件，仍超出本地优先开发者工具的防护范围。

## 仅监听 loopback 的 HTTP 绑定

daemon 的 FastAPI 应用将其 HTTP 服务器绑定到 `127.0.0.1`，而非 `0.0.0.0`。这是章程要求，而非配置选项。

实际效果：来自本机之外的任何请求都无法到达管理 API 或 MCP 协议端点。一个无法首先攻陷本机的远程攻击者没有任何网络路径可以访问 Coffer。这使得 daemon 无需设置防火墙规则也可以持久运行——操作系统在请求到达应用之前就会拒绝来自机器外部的连接。

唯一有意设计为无需鉴权的端点是 `GET /api/v1/daemon/status`。它仅监听 loopback，只返回生命周期阶段、版本、端口和上游健康状态摘要——不包含密钥、每个资源的详情或审计数据。其存在是为了让 CLI 和 shim 在从 `daemon.json` 读取 token 之前就能探测 daemon 是否就绪。

## 凭据：加密存储

密钥以 **Fernet 密文**形式存储在 `~/.coffer/coffer.db` 的 `credentials` 表中（envelope 加密）。明文值仅在解密与拉起子进程/注入 header（消费密钥处）之间存在于内存。其工作机制：

1. **存储**：用户调用 `POST /api/v1/credentials`，传入 ref 和密钥值。daemon 用主密钥对该值做 Fernet 加密，只把密文写入 `credentials` 表，并记录一条 `credential_set` 审计事件（详情中不含密钥值）。明文永不落盘。
2. **引用**：注册 MCP 服务器时，用户在配置中指定 `credential_refs: { "SOME_ENV_VAR": "my-secret-ref" }`。这个映射关系——从环境变量名到加密凭据存储中的一个 ref——存储在数据库的 `config_json` 中。密钥本身不被存储。
3. **物化**：在上游进程拉起时，daemon 读取每个 `credential_refs` 条目的密文，用主密钥解密，将明文注入子进程的环境变量（HTTP 传输则注入请求 header），然后拉起进程。明文只在拉起调用的持续时间内存在于内存中，永不写入日志、审计条目或数据库列。
4. **删除**：用户调用 `DELETE /api/v1/credentials/{ref}`。daemon 删除该行，并记录一条 `credential_deleted` 审计事件（详情中不含密钥值）。

### 主密钥

envelope 加密意味着数据库之外只剩唯一一份密钥材料：Fernet **主密钥**。它**恰好**存在于以下两个位置之一：

- **`~/.coffer/master.key`** —— 数据库旁的 `0600` 文件。这是**默认**：零钥匙串弹窗。（原因：macOS 把钥匙串 ACL 绑定到二进制的 cdhash，因此每次重新构建未签名 daemon 都会对每个密钥重新弹窗。文件背书的主密钥彻底消除了弹窗。见 [ADR-015](/zh/reference/adr/ADR-015-envelope-encrypted-credential-store)。）
- **操作系统钥匙串**（service `coffer`，ref `master-key`）—— 通过 **设置 → 安全** 或 `coffer credentials storage --set keychain` opt-in 的加固。macOS 每次 daemon 启动可能弹窗一次。这是防范 `~/.coffer/` 离线窃取的模式。

解析采用 **file-first**：daemon 先找文件，再找钥匙串。这让迁移**崩溃安全**——`relocate` 只移动主密钥，并**最后**删除旧副本，因此被中断的迁移总能解析回一个可用状态。迁移永不触碰 `credentials` 表中的密文（密钥搬家，数据不动）；切换存储模式不会重新加密。

只有当 `credentials` 表为**空**时，才会生成全新的主密钥。存在密文但无可解析密钥是一个致命且可操作的启动错误（`MasterKeyMissing`）—— Coffer 宁可拒绝启动，也不会悄然丢失对现有密钥的访问。

::: warning 备份注意
`coffer.db` 现在包含密文。恢复它的备份需要配套的 `master.key` 文件（钥匙串模式下则是钥匙串条目）。请把主密钥与数据库一起备份，否则恢复出的 `coffer.db` 无法读取。
:::

### legacy 钥匙串迁移

在 envelope 加密之前，密钥直接存于操作系统钥匙串。启动时 daemon 会运行一次性、尽力而为的迁移：读取那些被已注册资源引用的 legacy 钥匙串密钥，加密写入 `credentials` 表，并按 ref 以 `credential_migrated` 审计。若钥匙串被锁定，则跳过迁移，下次启动重试。

::: warning 绝对约束
`infrastructure/credentials/` 是整个代码库中**唯一**被允许 import `keyring` 的位置，且仅用于主密钥（钥匙串模式）与 legacy 迁移。这由 importlinter 契约（`backend/pyproject.toml` 中的 Contract 4）强制执行。任何在其他地方添加 `import keyring` 的 PR 都会导致 CI 失败。
:::

`StdioTransport` 配置 schema 还有第二道防线：其 `env` 字段对每个静态环境变量的值执行正则检测，并拒绝任何看起来像 token 或密钥的值（匹配 token 检测正则）。这能捕获用户不小心将明文密钥粘贴进静态 `env` map 而非使用 `credential_refs` 的情况。

## 通道与面向公网的接口面

仅监听 loopback 的不变量规定：面向公网的接口面必须以独立进程运行，并仅限于经过签名校验的回调路径。**SeaTalk 回调监听器**就是该规则的具体实现（spec 009，[ADR-014](/zh/reference/adr/ADR-014-channel-adapter-framework)）。SeaTalk 只通过公网 webhook 投递事件，因此它是 Coffer 唯一接收来自机器外部入站流量的地方——而它是通过一个 daemon 永不让网络触及的进程来完成的。

- **独立进程，永远不是 daemon。** 监听器是 daemon 拉起的子进程，仅在某个 SeaTalk 通道启用时运行。它只服务一条路由 `POST /seatalk/{channel}`，监听一个 loopback 端口（默认 `8787`，可通过 `COFFER_CALLBACK_PORT` 覆盖）。它不持有任何其他状态，除了 daemon 之外什么都触及不到。daemon 自身始终仅监听 loopback——永不暴露。
- **签名校验。** 每个回调 POST 都携带一个 `Signature` header，由 SeaTalk 按 `sha256(raw_body + signing_secret)`（小写十六进制）计算。监听器用原始 body 和该通道的签名密钥重新计算同样的摘要，并以常量时间（`hmac.compare_digest`）比较。空密钥或空签名永不通过校验——空密钥会让 MAC 退化为 `sha256(body)`，任何人都能算出。平台的 `event_verification` 挑战在原地应答；其他每个有效事件都携带 daemon token 经 loopback 转发给 daemon。
- **隧道是用户的，暴露面是监听器的。** 用户把隧道（cloudflared/ngrok）指向监听器的 loopback 端口。从公网只能触及这一条经过签名校验的回调路径；管理 API 和 MCP 端点根本不在隧道上。
- **通过配对码实现单一所有者绑定。** 一个通道通过一个 8 字符一次性配对码（无歧义字母表、1 小时 TTL、有限猜测次数、仅存于内存）绑定到恰好一个所有者，该码由 UI/CLI 签发，并由所有者的账号发送给机器人。其他任何人都被静默忽略；重新配对会替换绑定。不存在直接输入 user-id 的路径——配对同时也证明了传输层的往返通路。

密钥到达监听器的方式与上游 MCP 子进程获取密钥的方式相同：签名密钥、daemon URL 和 daemon token 在拉起时注入子进程的环境，永不落盘。拉起记录在 upstream-pids 目录中，因此 daemon 崩溃不会遗留任何东西——启动时的孤儿清扫会将其回收。daemon token 轮换会重新拉起监听器（token 在拉起时已烘焙进子进程的环境）。

## Sync 安全

多机 sync（[ADR-016](/zh/reference/adr/ADR-016-multi-machine-sync)）通过**一个用户自己拥有的 git 仓库**在机器之间搬运 vault 状态。其安全性建立在把密钥材料完全排除在该介质之外：

- **介质上只有密文。** 凭据以 Fernet 密文 blob 形式导出，并以密文形式通过 git 流转——git 仓库始终只持有无法解密的数据。即使远端是托管的 GitHub 仓库，供应商也始终只持有密文。
- **主密钥永不进入介质。** Fernet 主密钥通过 `coffer sync key export/import` **带外**引导到每台机器——永不提交、永不推送。这正是让宪章论证保持干净的原因：sync 介质不是任何可解密密钥的系统记录。
- **密钥就位前处于 `credentials_locked`。** 一台已拉取密文但尚未拿到配套主密钥的机器会报告 `credentials_locked`，并拒绝拉起受影响的资源。它永不静默地解密失败。
- **git 以子进程运行，使用环境中的凭据。** 出站 git 是真实的网络出口，但它遵循仅监听 loopback 的姿态：git 以子进程运行，使用用户自己环境中的 git 凭据，而非 Coffer 的 HTTP 客户端。Coffer 永不注入或存储 git 远端的凭据。

## Token 鉴权

daemon 启动时通过 `secrets.token_urlsafe(32)` 生成一个 256 位 URL 安全随机 token，将 `{"pid": ..., "port": ..., "token": "<token>"}` 以 `0600` 权限写入 `~/.coffer/daemon.json`，并通过 FastAPI 依赖项（`require_token`）按路由器强制执行 `X-Coffer-Token` header。

`/api/v1/*` 下的每个路由——包括 `/mcp` 处的 MCP 协议端点——都需要这个 header。`require_token` 依赖项对缺少或不正确 token 的请求返回 HTTP 401。没有备用鉴权方式：没有 session cookie，没有 Basic auth，没有使用其他 header 名称的 API key。

token 可通过 `POST /api/v1/daemon/rotate-token` 进行轮换。轮换后，旧 token 立即失效，新 token 写入 `daemon.json`。轮换事件以 `token_rotated` 记录在审计日志中。

客户端（CLI、shim、桌面 shell）都会在首次鉴权调用前从 `daemon.json` 读取 token。由于 `daemon.json` 的权限为 `0600`，只有进程所有者才能读取它——这构成了针对远程进程威胁的完整访问控制机制。

## CORS 配置

daemon 配置 CORS 以拒绝浏览器上下文中的跨域请求。由于 HTTP API 绑定到 loopback，主要风险是在同一台机器上打开的恶意网页通过浏览器的 `fetch()` API 向 `http://127.0.0.1:<port>/api/v1/…` 发起请求。CORS header 阻断了这种攻击：只有与配置允许列表匹配的来源才被允许携带凭据或读取响应体。

生产环境中，允许的来源是 Tauri 桌面 shell 的 `tauri://localhost` 和 `http://tauri.localhost`。仅当 `COFFER_DEV_CORS=1` 时才会添加 Vite 开发服务器来源（`http://localhost:5173` 和 `http://127.0.0.1:5173`）。整个列表可通过 `COFFER_CORS_ORIGINS` 覆盖。凭据始终不被允许（`allow_credentials=False`）——鉴权仅依赖 `X-Coffer-Token` header。不在允许列表中的来源在浏览器层面就会收到 CORS 拒绝，甚至在 token 检测运行之前——对浏览器端攻击向量的纵深防御。

## 出站 HTTP：真实路径与计划中的加固

daemon 如今已会发起出站 HTTP 调用。真实的出站路径包括：

- 构建知识索引时，向 OpenAI 兼容的供应商请求 **embeddings**（一个 `AsyncOpenAI` 客户端，按供应商切换 `base_url`）。
- 为 sync 执行 **`git push`**——但这是以 git 子进程运行，使用用户环境中的 git 凭据，而非 Coffer 的 HTTP 客户端（见 [Sync 安全](#sync-安全)）。
- 为通道调用 **Telegram 与 SeaTalk API**——用裸 httpx 访问固定的、众所周知的主机。
- **HTTP 传输的 MCP 服务器**，经由 MCP SDK 的 `create_mcp_http_client`（基于 `httpx`）。

章程要求出站 HTTP 必须经过具备 SSRF 防护的客户端。通道与供应商客户端访问的是固定的、众所周知的主机；尚未弥合的缺口是 **HTTP 传输的 MCP 客户端**——其目标主机来自用户注册的配置，而 MCP SDK 的 httpx 客户端没有 IP 范围过滤。为该 MCP 客户端实现该防护——在 DNS 解析后拒绝连接到 loopback、RFC 1918 私有范围和链路本地地址——是计划中的加固措施，尚未实装。

对于 stdio 传输的 MCP 服务器，根本不存在出站 HTTP——daemon 直接拉起一个子进程并通过进程的 stdin/stdout 通信。子进程的环境受到控制（不含明文密钥），其工作目录由配置中的 `cwd` 字段固定。

## 另请参阅

- [章程参考](/zh/reference/project/constitution) — 本地优先、凭据和网络默认值不变量
- [架构参考](/zh/reference/project/architecture) — 跨层关注点表和凭据模块位置
