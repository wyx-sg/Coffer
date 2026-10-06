---
title: 开发环境搭建
description: 从源码安装 Coffer，用一次性保险库运行守护进程和 Web 界面，熟悉仓库结构，并构建冻结二进制和桌面应用。
---

# 开发环境搭建 {#development-setup}

本页带你从一次全新的克隆走到一个由你的检出代码构建出来、正在运行的守护进程和 Web 界面。它还涵盖每一个 `make` 目标、契约与前端代码生成、发布构建，以及在 git worktree 中工作。本页面向 macOS 或 Linux 上的贡献者。桌面应用只能在 macOS 上构建。

## 前置条件 {#prerequisites}

| 工具 | 版本 | 用途 |
| --- | --- | --- |
| Python | 3.12（`.python-version`；`requires-python = ">=3.12"`） | 后端、CLI、MCP shim、所有仓库门禁 |
| [uv](https://docs.astral.sh/uv/) | 较新的任意版本 | 安装锁定的依赖集，`make lock` |
| Node.js + npm | 20，即每个 CI job 使用的版本 | Web 界面、OpenSpec CLI、Playwright |
| git | 2.40 或更高（`merge-tree --write-tree --merge-base`） | 保险库是一个 git 仓库：没有 git 守护进程会停在设置状态，保险库和同步测试也要运行它 |
| Rust 工具链（[rustup](https://rustup.rs)）+ Xcode 命令行工具 | stable | 只有桌面壳（`make desktop*`）需要 |

::: warning 使用 Node 20
CI 跑的是 Node 20。其他大版本在测试运行器里的表现可能不同。比如 Node 22 自带一个内置的 Web Storage，会在 jsdom 下弄坏 `localStorage`，`frontend/src/test/setup.ts` 不得不专门绕开它。如果前端测试在本地失败而在 CI 上通过，先检查 `node --version`。
:::

## 安装 {#install}

```sh
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
make install      # .venv from uv.lock + frontend, OpenSpec CLI and e2e npm deps
make hooks        # pre-commit and commit-msg git hooks
```

`make install` 需要 [uv](https://docs.astral.sh/uv/)。它会像 CI 一样，从 `backend/uv.lock` 把后端及其开发依赖同步到 `.venv`，后端本身以可编辑模式安装：

```sh
UV_PROJECT_ENVIRONMENT=.venv uv sync --frozen --extra dev --project backend --python 3.12
```

然后它会在 `frontend/`、仓库根目录（为了锁定版本的 OpenSpec CLI）和 `e2e/` 里分别运行 `npm install`。端到端测试用的浏览器是单独的、体积很大的下载：`make install-e2e-browsers`。

::: tip 本地结果和 CI 不一致时
先重新运行 `make install`，再调试别的。venv 与锁文件出现偏移（比如对 `>=` 下限做了一次 `pip install`）是测试在本地失败、在 CI 上通过的最常见原因。
:::

## 从源码运行 Coffer {#run-coffer-from-source}

### 快捷方式：`make dev` {#the-quick-way-make-dev}

```sh
make dev
```

`make dev` 通过真正的入口 `python -m coffer.infrastructure.daemon.entry` 从 `backend/` 启动守护进程，并设置 `COFFER_DEV_CORS=1`。它会等到 `~/.coffer/daemon.json` 出现、并且 `GET /api/v1/daemon/status` 有响应，然后在 `http://localhost:5173` 上启动 Vite。一个 Vite 插件会读取 `daemon.json`，把守护进程的端口和 API 令牌注入页面，所以界面无需任何设置就处于登录状态。按 Ctrl-C 同时停止两个进程。后端改动需要重启，因为守护进程没有开自动重载。

::: danger `make dev` 用的是你真实的保险库
直接运行时，`make dev` 会读写 `~/.coffer`，那里有你真实的保险库（配置、知识、技能和密钥）、历史和记忆。它还会写入你 home 目录下各智能体的配置，比如 `~/.claude`。它还会绑定 38470 端口。如果已安装的 Coffer 已经在那里运行，开发守护进程会拒绝启动，而且不会退到别的端口。请按下一节的做法使用沙盒。
:::

始终通过 `coffer.infrastructure.daemon.entry` 启动守护进程，不要直接用 `uvicorn coffer.main:app`。这个入口负责分配端口、生成 API 令牌并写入 `daemon.json`。没有它，每个需要令牌的端点都会返回 `503`。

### 用一次性保险库运行 {#run-against-a-throwaway-vault}

Coffer 用到的每一个路径都由 `HOME` 推导出来：`~/.coffer/`，以及它管理的各智能体配置目录。把 `HOME` 指向一个临时目录，再给守护进程分配一个自己的端口范围，就得到一个完全隔离、可以和你已安装的 Coffer 并排运行的实例：

```sh
export HOME="$(mktemp -d -t coffer-dev)"
export COFFER_PORT_RANGE_START=18150 COFFER_PORT_RANGE_END=18159
make dev
```

设置了端口范围后，守护进程会绑定该范围内第一个空闲端口，而不是坚持用 38470。`make dev` 和 Vite 插件都从沙盒的 `daemon.json` 读取选中的端口。在第二个终端里，导出同样的三个变量，就可以对沙盒使用 CLI：

```sh
.venv/bin/coffer daemon status
```

```text
status:  ready
version: 0.2.0
port:    18150
```

::: warning 在每个 shell 里都导出这些变量
需要守护进程的 `coffer` 命令在找不到守护进程时会启动一个。如果你用真实的 `HOME` 运行 CLI，它连的就是你真实的保险库。如果你用沙盒 `HOME` 但没设端口范围，它会试图在 38470 端口再启动一个守护进程。
:::

Vite 总是在 5173 端口提供服务（`strictPort`）。如果另一个检出目录的 `make dev` 已经占用了这个端口，前端那一半会以 `Port 5173 is already in use` 失败，守护进程那一半则继续运行。

当 `frontend/dist/index.html` 存在时，源码运行的守护进程也会在自己的地址上提供构建好的界面。运行 `npm run build --prefix frontend` 之后，打开 `http://127.0.0.1:<port>/`，看到的就和发布版提供的完全一样。

### 开发用的环境变量 {#environment-variables-for-development}

| 变量 | 作用 |
| --- | --- |
| `COFFER_PORT_RANGE_START`、`COFFER_PORT_RANGE_END` | 绑定该范围内第一个空闲端口，而不是配置的固定端口（默认 38470） |
| `COFFER_DEV_CORS=1` | 允许 Vite 的来源 `http://localhost:5173` 和 `http://127.0.0.1:5173`，以及桌面壳的来源。不设的话，守护进程会以 `403 ORIGIN_NOT_ALLOWED` 拒绝来自这些来源的请求 |
| `COFFER_CORS_ORIGINS` | 逗号分隔的列表，完全替换 CORS 允许列表（包括桌面壳的来源）。当你的界面运行在其他任何来源上时使用 |
| `HOME` | Coffer 的每一棵目录树（保险库、`local/`、`content/`、`derived/`、`runs.db`）都从它解析，没有针对单棵树的覆盖选项。沙盒 `HOME` 就是一个独立的 Coffer |
| `COFFER_DB_URL` | 历史数据库的 SQLAlchemy URL（默认 `sqlite+aiosqlite:///~/.coffer/runs.db`） |
| `COFFER_LOG_DIR` | 守护进程写日志文件的位置 |
| `COFFER_FEATURES` | 为这个守护进程固定实验功能的开关，格式为 `<key>=on,<other-key>=off`。例如 `models=on,sync=off`；键为 `knowledge`、`memory`、`sync` 和 `models`，没有被固定、也没在设置里开启的功能一律关闭 |
| `COFFER_WEBUI_DIR` | 从另一个目录提供构建好的界面 |

[配置参考](/zh/reference/configuration)列出了守护进程读取的每一个变量。

::: danger 测试绝不能碰到你真实的保险库
`backend/tests/conftest.py` 会在导入任何测试模块之前，把 `HOME` 指向一个一次性目录并清除所有继承来的 `COFFER_*` 变量；它给每个测试一个独立的 `HOME`，并固定 `COFFER_LOG_DIR`。另有一道绊线（`tests/support/real_home_guard.py`）会拒绝真实 `~/.coffer` 下的任何文件、SQLite 或进程启动事件，并让该测试失败。因为每一棵树都从 `HOME` 解析，一个全新的 `HOME` 就能把它们全部隔离。如果你在 pytest 之外写了会启动应用的脚本或 fixture，也要给它一个独立的 `HOME`。
:::

## 仓库导览 {#a-tour-of-the-repository}

| 路径 | 内容 |
| --- | --- |
| [`backend/coffer/`](https://github.com/wyx-sg/Coffer/tree/main/backend/coffer) | Python 包，分四层：`domain/`、`application/`、`infrastructure/`、`surfaces/`。见[分层与代码布局](/zh/architecture/layering) |
| `backend/tests/` | `unit/`、`integration/` 和 `contract/` 三个测试层级 |
| `backend/*.spec` | `coffer`、`coffer-daemon` 和 `coffer-mcp-shim` 的 PyInstaller spec |
| `backend/pyproject.toml`、`backend/uv.lock` | 依赖，以及 ruff、mypy、pytest 和 import-linter 的配置 |
| [`frontend/`](https://github.com/wyx-sg/Coffer/tree/main/frontend) | React Web 界面。见[前端](/zh/contributing/frontend) |
| [`desktop/`](https://github.com/wyx-sg/Coffer/tree/main/desktop) | Tauri 2 桌面壳（Rust），承载同一份 `frontend/dist` |
| [`e2e/`](https://github.com/wyx-sg/Coffer/tree/main/e2e) | Playwright 测试套件：`web/`（浏览器）、`mcp/`（MCP 客户端到 shim 再到守护进程）和 `visual/`（截图基线，`make verify-visual`） |
| [`evals/`](https://github.com/wyx-sg/Coffer/tree/main/evals) | 工具搜索和工具路由的评测框架，含数据集和基线 |
| [`openspec/`](https://github.com/wyx-sg/Coffer/tree/main/openspec) | 产品契约：`specs/`（当前）、`changes/`（进行中和已归档） |
| [`docs/`](https://github.com/wyx-sg/Coffer/tree/main/docs) | `decisions/`（决策记录）和 `research/`。原则和架构在本站的[架构](/zh/architecture/)部分 |
| `docs-site/` | 本 VitePress 站点 |
| [`scripts/`](https://github.com/wyx-sg/Coffer/tree/main/scripts) | 仓库门禁（`check_*.py`、`audit_acceptance.py`）和构建脚本 |
| `.agents/` | 给贡献者和智能体的约定文件 |
| `.claude/` | 智能体控制层：设置、Hook、OpenSpec 命令和技能 |
| `.github/workflows/` | CI、发布、文档站和桌面应用的 workflow。见[测试](/zh/contributing/testing#ci-workflows) |

## Make 目标 {#make-targets}

运行 `make help` 可以看到同样的列表。

| 目标 | 作用 |
| --- | --- |
| `make install` | 从 `backend/uv.lock` 同步 `.venv`（后端可编辑、含开发依赖），并为前端、OpenSpec CLI 和 e2e 运行 `npm install` |
| `make install-e2e-browsers` | 下载 Playwright 的 Chromium 构建 |
| `make hooks` | 安装 pre-commit 和 commit-msg 两个 git Hook（行尾空白、YAML/TOML/JSON 检查、ruff、prettier、commitlint） |
| `make dev` | 同时运行守护进程和 Vite（见上文） |
| `make verify` | 依次运行 `lint`、`docs-build`、`verify-unit`、`verify-integration`、`verify-contract` 和 `verify-acceptance`，打印每个阶段的耗时，然后记录一个新鲜度戳。这是开 PR 前的门禁 |
| `make verify-all` | `verify` 加上 `verify-e2e` |
| `make verify-unit` | 单元测试纯度检查、后端单元测试，然后是前端 Vitest 套件 |
| `make verify-integration` | 后端集成测试 |
| `make verify-contract` | 后端契约测试：每个对外提供的路由都有归属的能力，MCP 端点的行为符合协议 |
| `make verify-e2e` | 两个 Playwright 项目，`web` 和 `mcp` |
| `make verify-acceptance` | `openspec validate --all --strict`，然后是 `scripts/audit_acceptance.py` |
| `make openspec-validate` | 只做 OpenSpec 严格校验 |
| `make verify-benchmark` | 所有标记为 `benchmark` 的性能预算测试，包括慢到进不了 `verify` 的那些 |
| `make verify-secrets` | 像 CI 的 `secrets-scan` job 那样，用 gitleaks 扫描完整的 git 历史。没装 gitleaks 时跳过 |
| `make lint` | 所有静态门禁：见[测试](/zh/contributing/testing#what-make-verify-runs) |
| `make format` | 对 `backend`、`evals` 和 `e2e/installed` 运行 `ruff format` 和 `ruff check --fix`。前端由它自己的 prettier 配置格式化，不归这个目标管 |
| `make verify-visual` | 截图基线：每个路由、浅色和深色。不属于 `verify` 或 `verify-all` |
| `make visual-update` | 重新录制当前平台的截图基线 |
| `make test-durations` | 重新测量测试耗时，用于集成测试分片的均衡（串行，约 15 分钟） |
| `make coverage` | pytest 和 Vitest 覆盖率报告，不设阈值 |
| `make eval` | 确定性评测套件和基线门禁 |
| `make eval-routing` | 额外加上工具路由套件（需要本地 LLM） |
| `make eval-curate` | 把采集到的工具搜索查询变成带标注的黄金用例（`ARGS=--dry-run`） |
| `make lock` | 从 `pyproject.toml` 刷新 `backend/uv.lock` |
| `make contracts` | 从后端模型重新生成每项能力的传输契约，再从这些契约生成前端类型 |
| `make frontend-codegen` | 只从签入的契约重新生成前端的 TypeScript API 类型 |
| `make docs-reference` | 重新生成本站的 CLI 参考页面（英文和中文） |
| `make docs-build` | 按 Pages 工作流的方式构建本站；有失效的内部链接就会失败。它是 `make verify` 的第二个阶段 |
| `make refresh-prices` | 刷新内置的模型价格表（需要联网；不在 `verify` 中） |
| `make refresh-secret-rules` | 发版前刷新内置的 gitleaks 检测规则（需要联网；不在 `verify` 中） |
| `make bundle-binaries` | 用 PyInstaller 把 `coffer`、`coffer-daemon` 和 `coffer-mcp-shim` 冻结到 `dist/` |
| `make desktop` | 构建未签名的 `Coffer.app` 和 `.dmg`（很慢，见下文） |
| `make desktop-lint` | 对桌面 crate 运行 `cargo check` 和 `cargo clippy -D warnings` |
| `make desktop-test` | 对桌面 crate 运行 `cargo test` |
| `make desktop-stage-binaries` | 放置占位的 sidecar 二进制，让 cargo 不需要真实构建就能编译 |
| `make clean` | 删除 `.venv`、`node_modules`、`frontend/dist`、各种缓存和桌面构建产物 |

## 传输契约与前端代码生成 {#wire-contracts-and-frontend-codegen}

传输层只有一个方向：后端的 Pydantic 模型是 HTTP API 唯一手写的描述。每项能力的 OpenAPI 文件 `openspec/specs/<capability>/contracts/api.openapi.yaml` 由这些模型生成并签入仓库，所以对传输格式的修改会以 diff 的形式出现在引起它的那个 pull request 里。前端的类型又由这些文件生成。改了模型，就把两者都重新生成：

```sh
make contracts                 # models → contracts → frontend types
make frontend-codegen          # only the last step (= cd frontend && npm run codegen)
```

契约是从守护进程自己的 OpenAPI 文档中切出来的，构建这份文档不需要启动守护进程，并按每个路由归属的能力拆分。输出是确定性的，所以两个人从相同的模型重新生成，得到的字节完全相同。`make lint` 会在内存中重新生成契约，只要签入的文件不同，或者守护进程提供了某个不属于任何能力的路由，就会失败。`npm run lint` 以 `codegen:check` 开头，对前端生成的类型做同样的检查，然后拒绝前端 API 模块里手写的传输类型。永远不要手动编辑契约或 `generated/`。rebase 到一个改过模型的 `main` 之后，重新运行 `make contracts`。

## 构建冻结二进制 {#build-the-frozen-binaries}

```sh
npm run build --prefix frontend   # first: the daemon binary embeds frontend/dist
make bundle-binaries              # dist/coffer, dist/coffer-daemon, dist/coffer-mcp-shim
bash scripts/smoke_test_bundle.sh dist
```

只有 `frontend/dist/index.html` 存在时，`coffer-daemon.spec` 才会打包 `frontend/dist`。如果你跳过了前端构建，得到的守护进程能运行，但不提供界面。冒烟测试会在隔离的 `HOME` 下启动打包好的守护进程，检查它是否提供 Web 界面，并通过打包好的 shim 完成一次 MCP `initialize` 往返。

`scripts/check_pyinstaller_specs.py`（`make lint` 的一部分）让三个 `.spec` 文件和代码树保持一致，因为 pull request 上没有任何 CI job 会运行 PyInstaller。

## 构建桌面应用 {#build-the-desktop-app}

```sh
make desktop
```

它会构建 `frontend/dist`，运行 `make bundle-binaries`，把四个二进制以 Rust host triple 为后缀放到 `desktop/binaries/` 下，然后运行 Tauri 2 CLI。未签名的 `.app` 和 `.dmg` 会出现在 `desktop/target/release/bundle/`。在笔记本上大约需要 50 分钟，大部分时间花在 PyInstaller 上。本地构建的应用可以运行；未签名构建的下载副本会被 Gatekeeper 拦下。

日常修改 `desktop/src/*.rs` 时，不需要完整构建：

```sh
make desktop-lint    # cargo check + clippy, placeholders staged automatically
make desktop-test    # cargo test
```

桌面 crate 不在 `make verify` 里。`desktop` workflow 会在改动了 `desktop/` 的 pull request 上运行这两个目标。桌面壳的架构见[桌面应用](/zh/guides/desktop-app)和[分发与发布](/zh/architecture/distribution)。

## 在 git worktree 中工作 {#work-in-git-worktrees}

维护者，以及经常同时工作的多个 AI 智能体，都在并行的 [git worktree](https://git-scm.com/docs/git-worktree) 中工作，每个 worktree 一个分支：

```sh
git worktree add ../coffer-my-fix -b fix/my-fix main
cd ../coffer-my-fix && make install
```

注意以下几点：

- **`.git` 是共享的。** 任何一个 worktree 执行 fetch，`origin/main` 都会在你脚下移动。有意识地去 rebase，不要假设 `main` 还停在你离开时的位置。
- **stash 也是共享的。** 在一个 worktree 里 `git stash`，推入的是所有 worktree 都能看到的同一个栈，而裸的 `git stash pop` 可能会应用别人的工作。优先用一个临时的 WIP 提交。如果一定要 stash，就给条目命名（`git stash push -m "<tag>"`），并按它的 SHA 来应用。
- **每个 worktree 用自己的 `.venv`。** 后端以可编辑模式安装，所以从另一个检出目录软链过来的 `.venv` 导入的是那个检出目录的代码，你的测试就会在错误的代码树上通过。有两道门禁防范这一点：`make lint` 用 `PYTHONPATH=backend` 运行 `lint-imports`；如果 `coffer` 解析到本检出目录之外，`e2e/scripts/start_daemon.sh` 会拒绝启动。其他一切都只会测试 venv 指向的那份代码。
- **每个 worktree 只开一个会话。** 两个编辑器或智能体写同一个 worktree，会互相覆盖对方未提交的改动。
- **把守护进程放进沙盒。** 各 worktree 共享你的 `HOME`，所以两个 `make dev` 会争抢 `~/.coffer` 和 38470 端口。请使用上文的一次性保险库做法。

## 相关 {#related}

- [测试](/zh/contributing/testing)
- [前端](/zh/contributing/frontend)
- [运行守护进程](/zh/guides/daemon)
- [文件与目录](/zh/reference/filesystem)
- [`.agents/stack.md`](https://github.com/wyx-sg/Coffer/blob/main/.agents/stack.md)：后端约定、文件大小限制、分层规则
