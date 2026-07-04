# ADR-006: Daemon 探测或拉起模式

> English: [ADR-006-daemon-detect-or-spawn.md](./ADR-006-daemon-detect-or-spawn.md)

**Status**: 已采纳 (Accepted)
**Date**: 2026-05-20（2026-05-30 修订，见「修订历史」）
**Deciders**: Yuxing Wu
**Related**: spec `001-mcp-gateway` (FR-017, FR-018), [ADR-005](ADR-005-session-subprocess-model.md)

## 背景

Coffer 有多个入口都需要一个正在运行的 daemon：

- `coffer-mcp-shim` —— 每次 MCP 客户端 (Claude Code、Cursor) 启动时由其拉起。
- `coffer …` CLI —— 由用户临时调用。

daemon 必须**比任一单一入口活得更久**：用户期望某个 MCP 客户端的 shim 不会因为
另一个客户端的 shim 退出而死掉，也期望一次 `coffer` CLI 调用返回后 daemon 仍
继续运行。

问题在于：daemon 如何被启动、客户端如何发现它、其生命周期归谁所有。

## 决定

**探测或拉起 (detect-or-spawn) 模式，daemon 作为独立进程。**

- daemon 是绑定在 `127.0.0.1:<port>` 的独立进程，`<port>` 在启动时选定
  （默认 8000；被占用则在小范围内退而求其次取下一个空闲端口）。
- 启动时 daemon 写入 `~/.coffer/daemon.json` (mode `0600`)，内容为
  `{pid, port, token, started_at}`。
- shim 和 CLI 都使用同一个 `detect-or-spawn` 辅助函数：
  1. 读取 `~/.coffer/daemon.json`。
  2. 若文件存在且 PID 存活，则连接。
  3. 否则将 `coffer-daemon` 作为 detached 进程拉起（stdio 重定向到
     `~/.coffer/logs/daemon.log`），短暂等待 `daemon.json` 出现后再连接。
- daemon 不自动关闭。只有在显式执行 `coffer daemon stop` 或系统关机时才退出。
- 所有客户端在每个请求中通过 `X-Coffer-Token` header 携带 `daemon.json`
  中的 token。

## 后果

**正面**

- 任何入口都能引导 daemon —— 用户永远不会遇到「没有 daemon 在跑」的摩擦。
- daemon 在启动它的那个入口退出后仍然存活。一次无关的 `coffer` 命令返回后，
  基于 shim 的 MCP 客户端依然工作；某个客户端的 shim 退出也不会把 daemon
  连同其他客户端一起拖垮。
- 不需要任何特权安装。建立方式是「执行任意一次 `coffer` 命令」。
- 单一发现文件让客户端在端口变化时保持一致 —— 若 8000 被占而 daemon 选了 8001，
  所有客户端都读到同一个答案。

**负面**

- 「daemon 归谁所有」是隐式的（最先探测到缺失的那个）。引导者的清理责任由
  「daemon 不随引导者退出而退出」予以缓解。
- 如果两个客户端同时探测到缺失并同时 spawn，存在竞态。缓解方式：在
  `~/.coffer/daemon.lock` 上持有一把排他 `flock`，覆盖刚拉起的 daemon 的整个
  「探测 + 绑定 + 写入」临界区，**并在绑定之后继续持有，直到 daemon 真正在提供
  HTTP 服务**（`bootstrap.acquire_or_existing`）：持锁期间先探测 `live_daemon()`，
  仅当无存活 daemon 时才绑定端口并写入 `daemon.json`，随后**仍然持锁** ——
  `acquire_or_existing` 返回一个 `release` 回调，由 daemon 入口在 uvicorn 报告已开
  始服务（`Server.started`）后才调用。这正是串行化得以严丝合缝的关键：因为
  `live_daemon()` 用 HTTP `GET /api/v1/daemon/status` 探测确认存活（而非裸端口
  检查），一个已绑定但尚未服务的端口会被判定为**未**存活。倘若锁在写完
  `daemon.json` 的瞬间就释放，竞争的 spawn 可能在那不到一秒的启动窗口里醒来，探测
  到尚未服务的胜者、得到 `None`、于是绑定第二个端口 —— 把胜者变成孤儿。把锁持有到
  开始服务为止，意味着败者会一直阻塞在锁上，直到胜者能应答 `/daemon/status`，随后
  观察到它并干净退出。关闭时 daemon 的 `release()` 只在 `daemon.json` 仍记录着自己
  PID 时才删除它，因此孤儿 daemon 永远不会删掉存活 daemon 的发现文件。（Windows
  没有 `fcntl`，此锁退化为 no-op，由 `live_daemon()` 的拒绝启动与原子 `os.replace`
  充当兜底。）
- 由子入口（shim）自动拉起一个长生存周期进程并不常见 —— 尤其在 Windows
  上用户可能短暂看到命令窗口。缓解方式：Windows 上以
  `subprocess.CREATE_NO_WINDOW` 分离；POSIX 上使用 `os.setsid()`。
- 由于 daemon 的生存周期长于 app，刚安装的新版 app 可能复用一个仍在监听的
  **旧** daemon —— 形成静默的版本偏差。缓解方式是**检测而非自动更新**：daemon 在
  `GET /api/v1/daemon/status` 上上报其包版本（`coffer.__version__`），桌面 app
  将其与本次构建期望的版本（Tauri `daemon_version_matches` 命令，取自
  `CARGO_PKG_VERSION`）比对。不一致时，沿用现有的 daemon 离线横幅展示一个
  「daemon 版本过旧 —— 请重启」的入口，复用手动重启路径；Coffer 绝不自动杀掉
  正在运行的 daemon。

**运维后续**

- 上游 MCP 子进程在其连接关闭或被驱逐 (evict) 时被权威回收：每个记录在案的
  PID（及其后代——上游通常是 `uv`/`npx` 包装层套着一个解释器孙进程）若在 SDK
  拆除后仍存活，会被 SIGTERM/SIGKILL。这是防止泄漏在长生命周期 daemon 上累积的
  首要保障。启动时对 `~/.coffer/upstream-pids/` 的扫描仅作为兜底，处理 daemon
  *崩溃*（无优雅关闭）后残留的 PID。
- **同类残留 daemon** 在新 daemon 抢到绑定时被回收。一个常驻 daemon 若不再应答
  `GET /api/v1/daemon/status`（卡死、崩溃中、或 spawn 竞争的失败者），既不会被
  `release()`（只守护 `daemon.json`）终止，也不在上游扫描范围内，于是被顶替的旧
  daemon 会跨 App 启动不断累积。当新 daemon 进入 serving——即 `live_daemon()` 判定
  无人存活、我们绑定了端口之后——它会回收其它运行同一可执行文件的进程
  （`orphan_sweep.reap_stale_daemons`，排除自身、其 PyInstaller bootloader 父进程及
  所有祖先）。**仅限冻结构建**：源码运行的可执行文件是 Python 解释器，绝不能匹配。
  这与上面的版本偏移情形不同——*仍在应答*的旧版 daemon 留给用户手动重启，而
  *不再应答*的被顶替 daemon 则自动清理。

## 备选方案

**手动 daemon（用户在做任何事之前先 `coffer daemon start`）**。被否决。
体验糟糕：强制用户在每次与 MCP 客户端交互前记住一个准备步骤。

**由某个入口拥有 daemon（该入口退出则 daemon 死亡）**。被否决。这样只要那个
碰巧启动了 daemon 的入口退出，shim 就会损坏。detect-or-spawn 的意义正在于：
每个入口都是同一份长生存周期状态之上互相独立的入口。

**不用发现文件 —— 固定端口 + 环境共享 token**。被否决。开发机上的端口冲突
（8000 被大量使用）以及共享密钥轮换都需要某种配置或发现文件。
将所有信息放进一个文件比把状态拆分到多处更简洁。

## 修订历史

- **2026-05-20** —— 初版决定：detect-or-spawn 模式，daemon 作为独立进程；shim
  和 CLI 共用同一个辅助函数；daemon 启动时写出 `~/.coffer/daemon.json`。
- **2026-05-30** —— 实现更新：`coffer` CLI 现已全面实现 detect-or-spawn。此前
  CLI 会报错并提示用户手动执行 `coffer daemon start` —— 这是对本 ADR 所述设计
  意图的一个偏差，现已纠正。此外，spawn 现在具备 **frozen 感知**：当以
  PyInstaller 二进制方式运行时（即 `sys.frozen is True`），shim 和 CLI 会通过
  `coffer.infrastructure.daemon.spawn.daemon_spawn_command()` 拉起同目录下的
  `coffer-daemon` 二进制，而不是退回到 `python -m coffer_daemon`。这确保了无论
  Coffer 是从预构建的发布归档还是从源码检出安装的，都能使用正确的二进制。
- **2026-06-13** —— 版本偏差检测：daemon 现在会在 `GET /api/v1/daemon/status`
  上上报其包版本；当被复用的旧 detached daemon 的版本与 app 构建期望的版本不一致
  时，桌面 app 会展示一个手动的「daemon 版本过旧 —— 请重启」横幅。仅检测 + 手动
  重启；不自动更新，也不自动杀进程。
- **2026-06-13** —— spawn 竞态加固（本 ADR 一直在文档里写的那把 `flock`，现在真正
  落地了）。刚拉起的 daemon 的「探测 + 绑定 + 写入」现在在
  `~/.coffer/daemon.lock` 上的一把排他 `flock` 下运行
  （`bootstrap.acquire_or_existing`），关闭了「先检查后动作」的间隙 —— 此前两个
  几乎同时的 spawn 会各自绑定一个端口，败者的 `os.replace` 把胜者变成孤儿。
  `release()` 改为按 PID 校验 —— 仅当 `daemon.json` 仍记录着自己 PID 时才删除它，
  因此孤儿退出时不会删掉存活 daemon 的发现文件。`coffer daemon start` 现在以
  `live_daemon()`（真实状态探测）为准，因此陈旧的 `daemon.json` 会触发重新拉起，
  而不是误报「已在运行」；`coffer daemon stop` 在发送 `SIGTERM` 前会校验所记录的
  PID 的命令行确实是一个 Coffer daemon（被回收的 PID 不再被误杀）。桌面 app 的
  detect-or-spawn 存活性检查从裸 TCP 连接改为 HTTP `GET /api/v1/daemon/status`
  的 200 探测，因此占用了崩溃 daemon 所记录端口的「占座进程」不再被误判为存活
  daemon。
- **2026-06-22** —— shim 重启自愈。长驻的 `coffer-mcp-shim` 只在**启动时**解析
  一次 daemon 的端口 + token，并在其整个生命周期内固定使用。当 daemon 在不同端口
  上重启时（8000 被占用 → 选了 8001，或反之），所有已存在的 shim 仍然往那个已死
  的端口 POST，对每次工具调用都返回 `httpx.ConnectError: All connection attempts
  failed`，并让 SSE 重连循环永远空转 —— 客户端（如 Codex）会把它显示成单个工具的
  「连接错误」，看上去像上游/URL 配置错误，实则纯粹是 shim↔daemon 端点过期。
  修复：POST 连接失败时，shim 现在会重读一次 `daemon.json`（`_Bridge._recover`）；
  若在**不同**端点上发现存活的 daemon，就重绑共享 httpx 客户端的 `base_url` 与
  `X-Coffer-Token`，丢弃失效的 `Mcp-Session-Id`，重放缓存的 `initialize` 握手在新
  daemon 上建立新会话，然后重试该调用一次。同端点抖动仍按瞬时处理（正常退避）；
  完全宕机的 daemon 仍返回 JSON-RPC 错误（此时靠重新 spawn 一个新 shim 恢复）。
  共享客户端的重绑也会把 SSE 重连循环引导到新 daemon 上。
- **2026-06-13** —— 关闭启动窗口。spawn `flock` 现在会持有到写完 `daemon.json`
  之后、直到 daemon 真正在提供 HTTP 服务为止：`acquire_or_existing` 返回一个
  `release` 回调，由入口在 uvicorn 报告 `Server.started` 后才调用。此前锁在写完
  `daemon.json` 的瞬间就释放，留下一个不到一秒的窗口 —— 竞争的自动 spawn 会探测
  到已绑定但尚未服务的端口、从 `live_daemon()` 得到 `None`、于是绑定第二个端口，把
  胜者变成孤儿。并发测试也已修正为驱动一个真实的「已绑定但尚未服务」的 socket
  （并把释放锁与「正在服务」绑定），而不再把「`daemon.json` 存在」当作存活 ——
  那恰恰掩盖了这个窗口。
