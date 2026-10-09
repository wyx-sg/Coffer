---
title: 本地模型代理
description: 走 API 密钥 或本地连接的智能体如何到达它的模型——一个受监管的小进程监听在 loopback 上，逐字节转发每个请求，注入真实的 key，把上游自己的错误原样交还，并为每个请求计量而不记录任何对话内容。
---

# 本地模型代理 {#the-local-model-proxy}

用自己登录态的智能体直接和厂商通信，Coffer 不插手。被 Coffer 切换到某个**连接**上的智能体——网关的 API 密钥、厂商账号，或本机上的模型运行时——则改为和**本地模型代理**通信。代理是 `127.0.0.1` 上的一个小进程。它把每个请求带上真实的 key 转发到连接的接入地址，并记下这个请求的花费。

相关决策和权衡过的方案见两份决策记录（ADR）：[API 密钥 提供商通过一个逐字节转发的独立本地模型代理访问](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/api-key-providers-are-reached-through-a-separate-local-model-proxy.md) 和 [用量在代理处计量；订阅制智能体不计量](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota.md)。本页讲它的工作原理。

## 为什么需要代理 {#why-a-proxy-at-all}

在有代理之前，Coffer 把连接的接入地址直接写进每个智能体的配置。Claude Code 还会拿到一个打印真实 key 的辅助命令，Codex 则在环境变量里拿到真实 key。这种做法有两件事做不到：

- **计量。** Coffer 运行的东西看不到请求，所以说不出智能体花了多少。
- **不让智能体接触 key。** 被提示词注入的智能体可以运行那个辅助命令，或者 `env`，读到 key。

有了代理在路径上，智能体手里只有一个**本地令牌**，它只能解锁 loopback 上的代理，别无他用。真实 key 留在 Coffer 手里。

## 整体形状 {#the-shape}

```
Claude Code ──► http://127.0.0.1:38471/anthropic/v1/messages ──┐
                 (apiKeyHelper: coffer proxy token …)          │   same wire,
                                                               ├─► same bytes ──► the connection's endpoint
Codex ──► http://127.0.0.1:38471/openai/v1/responses ───────────┘   + the real key
           (auth: coffer proxy token …)
```

- **一个独立进程，用守护进程的二进制。** 正式构建里代理以 `coffer-daemon proxy` 运行，所以代理不需要自己的二进制去构建和签名；从源码运行时是 `python -m coffer.infrastructure.model_proxy.entry`。它是独立进程，因为守护进程每次升级都会重启，并在启动时跑迁移。如果代理在守护进程内部，每次重启都会切断所有进行中的模型流，包括用户自己终端里的会话。
- **由守护进程监管。** 守护进程启动时读取 `~/.coffer/proxy.json`（`port`、`pid`、`started_at`、`version` 和一个控制令牌，权限 `0600`）。如果那里有同版本的代理在响应，守护进程就重新挂接它。如果代理来自另一个构建，守护进程会让它排空，等它退出后替换掉。如果没有代理在运行，守护进程会在有智能体经由代理路由时启动一个；在那之前什么都不启动。重新挂接代理之前、以及每次向它推送密钥之前，守护进程都会先[验明](/zh/architecture/security#who-is-on-the-other-end)它的身份：它启动的代理会在标准输入上收到一个 attest 密钥，必须用它对一个新的 nonce 和自己的端口签名；所以只是抢占了端口或改写了 `proxy.json` 的进程什么都拿不到（日志里记为 `model_proxy.attest_failed`）。每隔几秒一次健康检查，会重启崩溃的代理；启动连续失败时，两次尝试之间的等待从 5 s 起指数退避，上限 10 分钟；连续失败 3 次后，代理被报告为失败。守护进程停止时，只是停止*监管*；代理继续运行。
- **固定端口。** 代理默认绑定 `127.0.0.1:38471`（`daemon-config.json` 里的 `proxy_port`）。固定端口让写进智能体文件里的 URL 不会自己变。没有绑定其他网卡的选项。

## 智能体拿到了什么 {#what-the-agents-are-given}

**Claude Code**（`settings.json`）：

- `env.ANTHROPIC_BASE_URL` 为 `http://127.0.0.1:<port>/anthropic`。
- `apiKeyHelper` 为 `<coffer> proxy token --agent-uid <uid>`。Claude Code 把它的输出同时作为 `x-api-key` 和 `Authorization` 发送，并缓存五分钟。
- `env.NO_PROXY` 加上 `127.0.0.1,localhost`，这样公司的 `HTTPS_PROXY` 永远不会截走 loopback 这一段。
- 模型相关的键（`model`、各档位固定、`modelPicker`）来自智能体的绑定，见[模型提供商](/zh/guides/providers#what-gets-written)。

**Codex**（`config.toml`）：

- `[model_providers.coffer]` 包含 `base_url = "http://127.0.0.1:<port>/openai/v1"`、`wire_api = "responses"`、`supports_websockets = false` 和 `requires_openai_auth = false`。
- `auth = { command = "<coffer>", args = ["proxy", "token", "--agent-uid", "<uid>"], timeout_ms = 30000 }`，所以在任何终端里启动的 Codex 都会自己取令牌，不需要导出任何东西。`timeout_ms` 是因为 Codex 默认只给这条命令 5 秒，而冷启动（CLI 自解压、daemon 还在启动）可能更久。基于命令的 `auth` 表需要 Codex 0.155.1 或更高版本。

两个文件都不写连接的名字。把智能体从一个 API 密钥 连接切换到另一个，改变的是代理的**路由**，智能体的文件不动。在连接和智能体自己的登录态之间切换，仍然是一次文件写入。

用自己订阅登录态的智能体永远不会被指向代理。代理反正也会拒绝它的凭据（见下文）。

## 令牌 {#tokens}

每个托管的智能体都有自己的随机 256 位令牌，首次使用时生成。它以 Fernet 密文的形式保存在密钥存储里，位于 `proxy-token/<智能体名>` 下（`proxy-token/claude-code`、`proxy-token/codex`；智能体的名字是固定的），这是一个本机专属的 ref，保险库同步永远不会带走。智能体已不存在的令牌，会在下一次构建代理状态时被删除。

- `coffer proxy token --agent-uid <uid>` 打印令牌。两个智能体运行的就是这条命令。

代理从不持有令牌本身，只持有它们的 SHA-256 摘要，并以常数时间比较请求出示内容的摘要。

对同一用户的进程而言，令牌不是安全边界：任何能读智能体配置的东西都能运行那条命令。它的作用是把浏览器页面和其他用户的进程挡在代理之外、标明请求来自哪个智能体，以及填上两个智能体都坚持要有的 key 字段。

## 转发 {#the-relay}

规则来自智能体自己的网关约定。Claude Code 的最严格。

- **同一种协议进，同一种协议出。** Anthropic 路由只转发到 Anthropic 形状的接入地址（`/v1/messages`、`/v1/messages/count_tokens`、`/v1/models`），Responses 路由只转发到 Responses 接入地址（`/v1/responses`）。没有协议转换。转换正是其他网关的 bug 藏身之处：工具调用的 delta 被弄乱、thinking 签名被丢掉、用量被清零。
- **请求体逐字节转发。** 代理只解析一份*副本*，用来读 `model` 和 `stream`。没有白名单过滤、没有重排、没有重新序列化，所以 `anthropic-beta` 的值和 Coffer 从没听说过的请求体字段都原封不动地到达，prompt caching 和 thinking 签名照常工作。
- **唯一的例外：连接不提供的模型。** 有些客户端会无视 Coffer 写进它配置里的模型。Codex 桌面 App 在 ChatGPT 工作区的模型策略下，每个新线程都从策略指定的模型开始，DeepSeek 这类接入地址会直接拒绝它。当连接配置了模型集合、而请求里的 `model` 不在其中时，代理只把这一个值替换为该智能体的默认模型（它绑定的模型，否则是连接里第一个文本模型），其余字节一概不动。对 Claude Code，若请求的模型名带有档位（`haiku`、`sonnet`、`opus`、`fable`），且连接提供 Coffer 为该档位写入的模型，则改用该档位的模型。属于集合的模型、没有配置模型集合的连接、以及没有 `model` 的请求体都不会被改动。每次替换写一行守护进程日志（`model_proxy.model_replaced`，记录请求的和实际使用的模型，不含请求体），用量按实际发出的模型记录。
- **请求头除一小份清单外都透传。** 除了逐跳头、`host`、`content-length`、客户端的凭据（`authorization`、`x-api-key`、cookie）和 `accept-encoding` 之外，全部转发。代理要求不压缩的流，好让它的用量读取器看到纯 SSE。然后注入连接的 key：Anthropic 协议上是 `x-api-key` 加 `Authorization: Bearer`，Responses 协议上是 `Authorization: Bearer`，不需要 key 的本地运行时则什么都不加。
- **响应按收到的样子返回。** 状态码、响应头和响应体分块都不经缓冲地转发，包括 ping 和 SSE 注释。Claude Code 会中止 300 秒没有动静的流，以转发的字节计。错误响应体原样转发，因为两个智能体的恢复逻辑都匹配上游的措辞。
- **超时。** 连接 10 秒，没有总超时，读空闲至少 300 秒，与两个智能体自己的看门狗一致。

除了模型路由，代理还回应 `/api/hello` 和 `/anthropic/api/hello`（Claude Code 的预热探测，不需要鉴权），以及守护进程的控制路由 `/_coffer/health`、`/_coffer/state` 和 `/_coffer/drain`（需要控制令牌）。代理收到的其他任何请求都返回 404。连接的接入地址是它的 `base_url` 去掉一个结尾的 `/v1`，所以 `https://api.anthropic.com`、`https://api.openai.com/v1` 和本地的 `http://127.0.0.1:11434/v1` 都会按各协议客户端期望的方式解析。

## 拒绝 {#refusals}

在转发任何东西之前，代理会拒绝：

- `Host` 不是请求到达端口上的 loopback 名字（DNS 重绑定），返回 403；
- 任何带 `Origin` 头的请求，返回 403。没有哪个浏览器页面是代理的客户端；
- 不带 Coffer 令牌的请求，按该协议自己的错误形状返回 401。这包括 claude.ai 的 OAuth 令牌（`sk-ant-oat…`）和真实的提供商 key。代理从不转发客户端的凭据。

## 一个连接，一个上游 {#one-connection-one-upstream}

智能体的请求只会去往一个连接：智能体被切换到的那一个。代理从不把请求挪到别的连接，也从不改变智能体请求的模型。

- **错误原样交给智能体。** 上游回什么——429、5xx、被拒的 key——都连同状态码、头和正文原样转发，智能体看到的就是它的厂商说的话，它自己的恢复逻辑据此行动。两个智能体本身都会自己重试暂时性错误。
- **完全没有响应时。** 如果上游根本连不上（连接、TLS 或 DNS 错误，或首字节超时），智能体收到一个按其协议错误形状构造的 502。
- **路由指向哪里。** 智能体的请求发往它所用的那个提供商。智能体的「概览 › 模型」只显示路由走 Coffer 的代理，并带一个**测试**按钮。

## 计量 {#metering}

一个用量读取器在转发旁边消费一份字节副本。读取器失败时，转发不受影响。代理为每个请求写一条记录：

- **谁：** 智能体（从它的令牌得知）、智能体发送时附带的会话和请求类别，以及连接。
- **什么：** 接入地址和所请求的模型。
- **结果如何：** 状态码、结局（`completed`、`error_event`、`truncated`、`client_cancel`、`upstream_error`、`connect_error`）、首 token 时间和持续时间。
- **Token：** 按互不重叠的类别计数：未缓存的输入、5 分钟和 1 小时的缓存写入、缓存读取，以及输出（其中包含推理）。它们按各协议自己的规则读取。在 Anthropic 协议上，`message_delta` 覆盖 `message_start`，因为服务端工具会重述并扩展总数。在 Responses 协议上，终止事件 `response.completed` / `incomplete` / `failed` 携带这些数字，缓存 token 和缓存写入（GPT-5.6 起才会上报，按 5 分钟写入计）从 `input_tokens` 里拆出来。

在终止事件之前被切断的流，用量记为**未知**。它从不被丢弃，也从不被猜测。

代理不打开任何数据库。它把记录追加到 `~/.coffer/proxy-usage/` 下的暂存文件里，文件完整后从 `.jsonl.part` 改名为 `.jsonl`。守护进程是唯一的数据库写入者，它摄取已完成的文件，只在对应的行提交之后才删除文件，并按上游的请求 id 去重，所以重复摄取不会把任何东西写两遍。同样的记录也告诉守护进程提供商的健康状态：被 401/403 拒绝、或根本没连上接入地址的请求，会在列表和总览里标出那个提供商（见[健康状态](/zh/guides/providers#health)）。这些记录如何变成用量报告，见[用量与额度](/zh/guides/usage)。

## 它记录什么，以及从不做什么 {#what-it-records-and-what-it-never-does}

代理的日志和记录只含元数据：上面的用量记录。它从不记录请求体、提示词、补全内容或密钥。

守护进程解密代理所服务连接的 key，并通过代理经过认证的 loopback 控制路由推送过去：在启动时、重新挂接时、每一轮调和之后，以及桌面应用里一项密钥批准生效时立即推送。key 还在等待批准的连接——正在使用的连接换了新 key，或者 key 要发往一个它以前没去过的 base URL——会被排除在推送的状态之外，所以在你批准之前，代理会继续发送旧 key，或者不向新 URL 发送任何东西；批准之后的下一个请求就会使用新 key 或新 URL，守护进程和代理都不用重启。代理只在内存中持有 key。它从不把 key 写到磁盘、argv、环境变量或日志里，也从不持有主密钥。

## 本地模型运行时 {#local-model-runtimes}

到本机运行时的连接和其他连接一样走代理。Ollama、LM Studio、vLLM 和 llama.cpp 的 `llama-server` 都符合条件，各自说自己的原生协议。这类连接不带 key 或只带一个可选的 key。现在所有主流运行时都自己同时提供 Anthropic Messages 和 OpenAI Responses，所以不需要转换。只说 Chat Completions 的运行时（`mlx_lm.server`）不是受支持的上游；请改用 LM Studio 的 MLX 引擎。检测和配置见[模型提供商](/zh/guides/providers#local-model-runtimes)。
