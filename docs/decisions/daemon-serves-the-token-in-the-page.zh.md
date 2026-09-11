# 由 daemon 把 token 放进它提供的页面里，并以 Host 请求头把守

> English: [daemon-serves-the-token-in-the-page.md](./daemon-serves-the-token-in-the-page.md)

- **状态：** 已采纳
- **日期：** 2026-09-11
- **决策者：** Yuxing Wu
- **规范：** [mcp-gateway](../../specs/mcp-gateway/spec.zh.md) FR-024 / FR-025 / FR-027
- **相关：** [Detect-or-Spawn](./daemon-detect-or-spawn.zh.md)（daemon 的端口会随重启变动，这是浏览器找不回自己的另一半原因）

## 背景

daemon 每次启动都会铸造一个新的 API token —— `secrets.token_urlsafe(32)`，跨重启
绝不持久化 —— 并绑定端口区间内第一个空闲端口，因此 origin 也会漂移。浏览器取得该
token 的唯一途径，曾经是 `coffer open` 放进启动 URL 的一次性 `#code=…` fragment：
页面到 `POST /daemon/web-session` 用该 code 换回 token，再把 token 存进
`localStorage`。

这只在每次 `coffer open` 时生效一次。人抵达 UI 的其它任何方式 —— 书签、手敲地址、
刷新、睡眠后恢复的标签页 —— 都会重新读取 `localStorage` 里还留着的东西；而在任何一次
daemon 重启之后，那是一个已经作废的 token。于是每一次 API 调用都 401。UI 把它报成
`UNAUTHENTICATED`，其文案称之为连不上后台并建议刷新；可刷新只会重新读到同一个死
token，所以这条建议永远不可能奏效。真正的补救是再跑一次 `coffer open`，而这一点没有
任何地方告诉过用户。

原设计的前提就写在它所辩护的那个模块里：「URL 是一个刚打开的浏览器唯一会读的通道。」
这个前提是错的。daemon 自己提供 SPA（FR-024），因此**响应正文**本身就是通往那个浏览器
的通道 —— 一条 URL 的那些顾虑完全够不着的通道。

## 决策

**daemon 把自己的实时 API token 注入到它提供的 `index.html` 中**，以文档 head 里的
`window.__COFFER_TOKEN__` 形式 —— 这正是前端本来就优先于存储读取的那个全局变量，因为
Vite dev server 就是这么把它喂进去的。于是，一个由 daemon 提供的页面，凭「被提供」这件
事本身即已鉴权，无需任何用户动作，也不持久化任何东西。

有三条性质让它是正确的，而不只是方便：

- **唯一真相来源。** 注入的取值来自 `surfaces/http/auth.get_active_token()` ——
  与 `require_token` 所比对的是同一个进程内变量，且按请求读取。一次轮换只改这一个
  变量，因此交给页面的值不可能与 API 接受的值漂移开。
- **每一条路由，而不只是 `/`。** 只要提供的是 `index.html` 就注入，包括客户端路由的
  SPA 回退。触发这次修改的故障发生在 `/agents`。
- **绝不缓存。** 该文档现在携带了一份每个 daemon 各自的密钥，所以以
  `Cache-Control: no-store` 提供，不带 ETag、不带 Last-Modified。一份缓存或再验证得到的
  副本，会把上一个 daemon 的 token 交给重启后的浏览器 —— 也就是这个 bug 借缓存重演。
  `/assets` 下带内容哈希的文件保持正常缓存。

**同时，daemon 拒绝任何 `Host` 请求头不指向 loopback 权威的请求**（FR-027），
以 `421 HOST_NOT_LOOPBACK` 应答。这不是顺手做的独立整顿，而是让上述注入得以安全的
前提；两半绝不可以只上其一。

绑定 loopback 挡得住远程主机，却挡不住浏览器：攻击者把 `evil.com` 的域名重解析到
`127.0.0.1`，在浏览器看来该页面仍与 `evil.com` 同源 —— CORS 因此根本不介入，页面能读到
响应正文。在这次修改之前这什么也换不到，因为 daemon 的 HTML 里没有秘密。而 token 一旦
进入文档，一次 `fetch("/")` 就能把整个保险库端走。DNS rebinding 不会改变 `Host` 请求头，
所以被重绑定的请求仍然写着 `Host: evil.com`，直接被拒。

`COFFER_ALLOWED_HOSTS`（逗号分隔，或 `*`）可以追加权威。后端测试套件设为 `*`，因为它
在进程内驱动 ASGI 应用，那里既没有网络也没有浏览器；真实部署中没有任何东西需要它。

一次性 code 那条路径是**删除**而非与新路径并存：`web_session` 存储、
`POST /daemon/web-code`、`POST /daemon/web-session`、前端的兑换逻辑，以及
`coffer.token` 这个 localStorage key，全部消失。`coffer open` 保留，但不再携带任何凭据 ——
它从 `daemon.json` 读取 daemon 真实的端口（detect-or-spawn 在必要时拉起一个），并在那个
origin 上打开浏览器。

## 影响

- **UI 自己就能恢复。** 重启 daemon、刷新页面 —— 哪怕是一条深链接 —— 它就会以新端口上
  新 daemon 的身份完成鉴权。「每次重启都得再 `coffer open` 一遍」的仪式没有了。
- **会话不再有任何持久化。** token 不进存储、不进 URL、不进历史。页面的凭据与文档同寿。
- **`Host` 校验从此是承重的。** 今后任何出现在 daemon 端口上的面都继承它。独立的
  `coffer-callback` 进程 —— 隧道唯一会指向的东西 —— 是另一个端口上的另一个应用，不受
  影响；它以按频道的签名校验入站流量，再经 loopback 转发给 daemon。
- **不由 daemon 提供的浏览器页面没有 token。** 那就是 Vite dev server，而它已经从
  `daemon.json` 注入同一个全局变量。不存在第三种情况。

## 备选方案

- **保留 code 兑换，只改错误文案。** 否决：那仍然要求用户每次重启后再跑一次
  `coffer open`，只是把死胡同解释得客气一点。
- **跨重启持久化 token，不再每次新铸。** 否决：一个长期躺在磁盘上、能解锁凭据端点的
  token，比按进程铸造的划算不了；何况它也治不了端口漂移。
- **直接把 token 放进 URL fragment。** 以原设计自己的理由否决 —— URL 会进入历史、终端
  回滚、截图和粘贴出去的 bug 报告。响应正文一样都不沾，这正是它才是对的通道、而 fragment
  不是的原因。
- **只靠绑定 loopback，不做 `Host` 校验。** 否决：那恰恰是 DNS rebinding 穿过去的缺口，
  也正是这次注入会打开的缺口。
