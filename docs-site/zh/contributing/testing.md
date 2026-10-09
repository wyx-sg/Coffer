---
title: 测试
description: Coffer 的四个测试层级、各自放在哪里以及怎么运行，真实 home 防护与隔离 home，验收标记，mock 理念，make verify 运行的每一道门禁，以及 CI workflow。
---

# 测试 {#testing}

本页介绍 Coffer 是如何测试的：四个层级及其所在位置、怎么运行、测试套件如何让测试远离你真实的 home 目录、测试如何关联到规格场景、在这里什么样的测试才算好测试，以及 `make verify` 和 CI 施加的每一道门禁。完整的约定见 [`.agents/testing.md`](https://github.com/wyx-sg/Coffer/blob/main/.agents/testing.md)。

标准一句话就能说清：**`make verify` 加上 `make verify-e2e` 为绿，就必须意味着产品能用**，不需要任何手工复测。

## 四个层级 {#the-four-tiers}

| 层级 | 测什么 | 放在哪里 | 单个测试预算 | 运行方式 |
| --- | --- | --- | --- | --- |
| **单元** | 纯逻辑：领域函数、值对象、单个类。没有 I/O | `backend/tests/unit/`，以及就近放置的 `frontend/src/**/*.test.ts(x)` | < 100 ms | `make verify-unit` |
| **集成** | 多个模块加真实的本地基础设施：真实 SQLite、真实子进程、真实文件系统、`keyring` 测试后端。没有网络 | `backend/tests/integration/` | < 2 s | `make verify-integration` |
| **契约** | 新鲜度检查看不到的传输一致性：守护进程提供的每个路由都有归属的能力，MCP 端点和内置工具的行为符合协议和规格 | `backend/tests/contract/` | < 1 s | `make verify-contract` |
| **E2E** | 通过真实入口测试组装好的产品：浏览器访问界面，以及真实 MCP 客户端经由 shim 和守护进程访问上游服务器 | `e2e/web/specs/`、`e2e/mcp/specs/` | < 30 s | `make verify-e2e` |

预算只是指导，不是门禁。如果一个测试超出预算一个数量级，那是在提示它应该属于另一个层级。

测试套件有意**以集成测试为主**：按数量是集成 ≫ 单元 > 契约 > e2e。集成层级跑在真实的 SQLite 文件和真实子进程上，速度依然很快，所以大多数行为都在真实连接所在的地方被钉住。单元层级留给纯逻辑，并由一个脚本强制执行（见[单元测试纯度](#unit-purity)）。

### 运行测试 {#running-tests}

```sh
make verify-unit                     # purity check, backend unit, frontend Vitest
make verify-integration
make verify-contract
make verify-e2e                      # both Playwright projects

# one file or one test
.venv/bin/python3 -m pytest backend/tests/integration/surfaces/http/test_feature_routes.py -q
.venv/bin/python3 -m pytest backend/tests -k "dev_channel" -q
cd frontend && npx vitest run src/components/PageHeader.test.tsx
cd e2e && npx playwright test --project=web shell_skills
```

`make verify-benchmark` 运行所有标记为 `benchmark` 的性能预算测试。它会设置 `COFFER_RUN_BENCHMARKS=1`，让那些慢到进不了 `make verify` 的测试也一起运行，有一个单独的 CI job 负责运行它。哪项预算在哪里运行，见[性能预算](#performance-budgets)。`make coverage` 生成 pytest 和 Vitest 的覆盖率报告。用它来发现没测到的分支，而不是把它当成指标。

## 好测试是什么样的 {#what-a-good-test-looks-like}

每个函数、HTTP 路由和 CLI 命令都有一个断言其真实结果的测试：状态码和响应体、退出码和输出，或者最终状态。它还要覆盖错误分支和边界分支。规格中的每个场景都至少由一个测试通过真实入口驱动。只有在真实回归时会失败的测试才有存在的价值。评审会拒绝：

- **同义反复。** 断言一个你刚刚原样传进去的字面量。
- **缺失断言。** 在真实契约很容易检查的情况下，只检查「没抛异常」、`status_code == 200` 或 `exit_code == 0`。当状态码*就是*契约时（比如缺少认证时的 `401`），只断言状态码没问题。
- **空转的循环和条件。** `for x in results: assert …`，却没有保证 `results` 非空。
- **过度 mock。** mock 了被测单元本身，于是测试只验证了 mock。
- **宽松到不可能失败的断言。** `len(x) >= 0`，或者延迟上限是真实值的 100 倍。

### mock 理念 {#mocking-philosophy}

只要够快，就优先用真东西：

- 真实 SQLite，放在内存或临时文件里
- 真实子进程，使用短时运行的子进程
- 真实文件系统，放在 `tmp_path` 下
- `keyring` 测试后端，它是另一个真实实现，而不是 mock

只 mock **非本地**的东西（外部 HTTP 服务、LLM API）、以测试关心的方式**不确定**的东西（时钟、随机数），或者万不得已时 mock **慢**的东西。需要 mock 慢东西的测试，往往放错了层级。

### 基于性质的测试 {#property-based-tests}

有些规则必须对所有输入都成立，而不只是对几个挑出来的输入成立。这类测试写下规则本身，由 [Hypothesis](https://hypothesis.readthedocs.io/) 生成输入。同步的删除闸门和同步轮次的合并决策就是这样测试的：

- **删除闸门。** 用生成的区域去对照用整数写出的阈值（20 个文件，或 5 个以上且超过该区域的一半）。同时检查移动永远不算作丢失。
- **一个轮次。** 生成的 vault 分叉在内存里的 git 上跑过真实的轮次引擎。任何冲突都必须让这一轮停下，丢失过多的合并必须被拦住。这两种情况都不允许检出任何东西，也不允许推送。其他所有干净的合并都必须被应用并推送，而且下一轮必须无事可做。

这些测试属于单元层，在 `make verify` 中运行。默认配置每个测试抽取 100 个样例，每次运行都是同样的 100 个。它不给单个样例设时间上限，也不往仓库里写样例数据库。改动了被测代码之后，运行 `HYPOTHESIS_PROFILE=thorough make verify-unit` 做更深的搜索：每个测试抽取 2000 个随机样例。某条性质失败时，Hypothesis 会把输入缩小到最小的失败用例并打印出来。把这个用例写成一个普通的样例测试，放在这条性质旁边。

### 测试并行运行 {#tests-run-in-parallel}

后端的单元和集成层级把测试分散到每个核一个 worker 进程上，这让集成层级从本地 verify 最慢的一步变成了较快的几步之一。每个 worker 都是一次完整、独立的测试运行：它有自己的一次性 home、自己的临时工作目录和自己的临时文件夹，所以下面描述的各项保护在每个 worker 里都和单进程时完全一样地成立。

当你需要单进程时（在调试器里单步执行某个测试、读不交错的输出，或者追查一个依赖测试顺序的失败），把 worker 数设为零，该层级就会串行运行。

要让一个测试能和其他测试安全并存，它创建的任何东西都不能用其他进程也可能选中的名字。在测试自己的临时目录里建文件，向操作系统要一个空闲端口而不是写死一个，永远不要往检出目录本身写东西。当一个测试依赖被测代码写死、测试又挪不动的某样东西时，把它标记为属于某个命名分组：同一分组中的所有测试在同一个 worker 上依次运行。这是最后的手段，因为每个分组都是并行运行中的一座小小的串行孤岛。

### 测试从不碰你真实的 home {#tests-never-touch-your-real-home}

Coffer 存在磁盘上的几乎所有东西都在你的 home 目录下：保险库及其数据库、笔记和日志，以及 Coffer 所连接的各编程智能体的配置。一个忘了把其中某个路径指到别处的测试并不会失败，它会悄悄地在你的真实数据上运行。

这种事发生过。当定位知识树的那个设置没有设置时，Coffer 退回到了 home 目录下的默认位置。一个启动应用却没设置它的测试，在一位开发者真实的保险库上跑了知识迁移，挪动了他的文件。再多设一个变量只能堵住这一条路径，所以测试套件现在一次性对所有路径强制执行这条规则，分两层。

**重定向 home。** 在任何 Coffer 代码加载之前，测试运行会把 home 目录指向一个一次性位置。它还会丢弃从你 shell 继承来的所有 Coffer 设置，以及可能把智能体或 git 引向其他目录的变量。然后每个测试都会得到一个全新的、自己的 home，并已设置好让 git 能在其中提交。测试启动的程序（比如守护进程、MCP shim 或命令行）继承同一个一次性 home，所以它们也碰不到真实的 home。

**真实 home 上的绊线。** 重定向仍然可能被撤销，最容易的方式是某个测试修改或删除了 home 变量。没有这个变量时，系统会退回到你真实的 home。所以测试套件还会监视解释器自身的文件、数据库和进程启动事件。任何试图在你真实 home 下的 Coffer 目录或智能体配置目录中读写的操作，都会在发生*之前*被拒绝，所以什么都不会被写入。启动一个没有设置 home 或设置为真实 home 的程序，也会以同样的方式被拒绝。每一次拒绝还会被记录下来，因为能容忍文件不可读的代码可能会悄悄吞掉错误。之后该测试会失败，并列出它试图碰触的东西，即使其他一切都没出错。有一组专门的测试证明了这一点：它们故意瞄准真实 home，并同时检查每次尝试都被拒绝、以及没有任何东西出现。

如果绊线让你的测试失败了，报错信息会写出每一个路径。修复方法几乎总是在测试自己的临时目录里构建该路径，或者使用下面的某种隔离环境。不要把任何东西指向你真实的 home。

### 隔离 home {#isolated-homes}

在测试里，一台「机器」就是一个 home 目录。测试套件提供了现成的隔离环境，测试永远不需要自己拼装：

- **单台机器。** 一个测试进程已经在使用的全新 home。Coffer 从它推导出自己的每一个目录，和已安装的副本完全一样。同一个 home 可以交给测试启动的程序，让该程序以这台机器的身份运行。
- **共享一个远端的两台机器。** 两个相互独立的 home，除了一个它们都能访问的真实 git 仓库之外什么都不共享。保险库同步的场景就在它们之间通过真实的同步代码和真实的 git 上演，没有任何伪造。
- **伪造的智能体配置。** 一个智能体的配置目录（比如 Claude Code 或 Codex 的），依照 Coffer 自身使用的同一份智能体描述，布置在一个隔离 home 里。因此测试写入的文件恰好落在 Coffer 会去找的地方。默认位置和自定义位置都支持。
- **伪造的聊天渠道。** 一个即时通讯平台的替身。它记录 Coffer 发送的一切（消息、卡片、编辑、正在输入指示、表情回应、文件），并允许测试投递收到的消息和按钮点击。它的各项能力可以单独开关，所以同一个替身既能扮演原地编辑消息的平台，也能扮演流式回复的平台。

当一个测试需要一种新的隔离环境时，把它加在这些旁边，而不是在某个测试文件里临时搭一个。

## 验收标记 {#acceptance-markers}

`openspec/specs/**/spec.md` 中的每个 `#### Scenario:` 都需要至少一个覆盖它的测试，层级不限。测试带一个引用能力 id 和场景名的标记：

::: code-group

```python [pytest]
@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="a stored setting for a feature the registry does not name is ignored",
)
def test_a_stored_setting_for_a_retired_feature_is_ignored(home): ...
```

```ts [Vitest]
import { acceptance } from "@/test/acceptance";

acceptance("chat", "chat runs on the built-in model when no connection", () => {
  // ...
});
```

```ts [Playwright]
import { acceptance } from "./_acceptance";

acceptance("web-ui", "activity gives each record its own tab", async ({ page }) => {
  // ...
});
```

```rust [Rust]
// acceptance(spec = "desktop-app", scenario = "a spawned daemon outlives the app")
#[test]
fn a_spawned_daemon_leaves_the_apps_process_group() { /* ... */ }
```

:::

`make verify-acceptance` 做两项检查。首先，`openspec validate --all --strict` 让任何没有场景的需求失败。然后 `scripts/audit_acceptance.py` 在以下情况下失败：

- 某个场景没有覆盖它的标记
- 某个标记指向不存在的能力或场景（进行中的 change 新增的场景在该 change 归档前视为存在，并会被列出）
- 标记打在一个永远不会运行的测试上（`@pytest.mark.skip`、Rust 的 `#[ignore]`）
- 同一份规格里一个场景名用了两次

pytest 标记在 `backend/pyproject.toml` 中注册，并在 `--strict-markers` 下运行。TypeScript 审计会先去掉注释，所以被注释掉的调用不算数。Rust 标记只有在下一个 `fn` 之前紧跟着 `#[test]` 或 `#[tokio::test]` 时才算数。Rust 测试在 `make desktop-test` 和 `desktop` workflow 下运行，不在 `make verify` 下。场景怎么写，见[规格驱动的工作流](/zh/contributing/spec-workflow#acceptance-scenarios-and-markers)。

## 单元测试纯度 {#unit-purity}

`scripts/check_unit_purity.py` 是 `make verify-unit` 里第一个运行的。它解析 `backend/tests/unit/` 下的每个文件，只要导入了 I/O 模块就失败：`subprocess`、`sqlite3`、`httpx`、`fastapi.testclient`、`socket`、`requests`、`urllib.request`、`aiohttp` 或 `keyring`。报错信息会写明文件和行号，并指引你去集成层级。要禁用另一个模块，把它加到脚本里的 `BANNED` 字典。

## 性能预算 {#performance-budgets}

有几项开销有预算，由测试来保证。每个上限都比实测值高出几倍。它在代码开始做不该做的事时失败，而不是在机器忙的时候失败。

| 预算 | 实测 | 上限 | 测试 | 运行于 |
| --- | --- | --- | --- | --- |
| 守护进程启动：在假 home 和空 vault 上，守护进程及其子进程从拉起到第一次报告 `ready` 所花的 CPU 时间 | 2.4–2.7 s CPU（墙钟 2.4–22 s） | 8 s CPU，另有 60 s 墙钟上限防止卡死 | `backend/tests/integration/perf/test_startup_time.py` | `make verify` |
| 网关开销：一次 MCP 工具调用经过网关、相比直连多花的时间的中位数 | 2–5 ms | 50 ms | `backend/tests/integration/perf/test_gateway_overhead.py` | `make verify` |
| 稳态下的一轮调和：两个已连接的智能体、20 个 skill、一个启用中的 provider 连接 | 27–40 ms | 2 s（`PASS_BUDGET_SECONDS`） | `backend/tests/integration/perf/test_reconcile_pass_cost.py` | 只在 `make verify-benchmark` |

实测数据来自一台 Apple Silicon 笔记本，测量时机器上还有别的工作在跑。启动的预算按 CPU 时间算，因为它的墙钟时间取决于机器：在那台笔记本上，负载高时启动一个进程要好几秒，同一次启动的墙钟时间从 2.4 秒到 22 秒不等，而 CPU 时间一直在 2.4 到 2.7 秒之间。启动测试和网关测试各只需几秒，所以和集成层的其他测试一起运行。调和测试光是搭建它的机器就要将近一分钟，所以只有 `make verify-benchmark` 和它的 CI job 运行它。这三个测试都标记了 `benchmark`，所以 `make verify-benchmark` 会跑全部预算。

测试从不自动重试。只在机器负载高时才失败的测试是有 bug 的，bug 在测试里或者在代码里：找到其中对墙钟时间的假设，把它去掉。

## 用 Playwright 做端到端测试 {#end-to-end-tests-with-playwright}

`e2e/playwright.config.ts` 定义了两个项目，`make verify-e2e` 两个都会运行：

| 项目 | 测试文件 | 驱动什么 |
| --- | --- | --- |
| `web` | `e2e/web/specs/*.spec.ts`：`agent_workspace`，以及覆盖活动、智能体、冷启动、知识、MCP 流程、设置和技能的各个 `shell_*` spec | Chromium 访问 Web 界面 |
| `mcp` | `e2e/mcp/specs/*.spec.ts`：stdio 和 HTTP 上的往返、并发客户端、能力停用、会变化的上游、上游崩溃恢复 | 真实 MCP 客户端 → `coffer-mcp-shim`（stdio）→ 守护进程（`/mcp`）→ 上游 MCP 服务器。没有浏览器 |

第一次运行之前：

```sh
make install-e2e-browsers            # Playwright's Chromium
make verify-e2e                      # or: cd e2e && npx playwright test [--project=web|mcp]
```

Playwright 会启动两个 Web 服务器：

- **守护进程。** `e2e/scripts/start_daemon.sh` 在一个全新的临时 `HOME` 下运行它，`COFFER_DB_URL` 也设在其中，端口范围从 `18000` 开始，并设置 `COFFER_DEV_CORS=1`。它最多等 45 秒让 18000 端口空出来，并把选中的 home 记录在 `/tmp/coffer-e2e-home.path`。它把本检出目录的 `backend/` 放到 `PYTHONPATH` 上；如果 `coffer` 仍然解析到另一个检出目录，就拒绝启动，这样测试套件就不会悄悄地测错代码树。
- **Vite**，端口 5173，设置 `VITE_COFFER_BASE_URL=http://127.0.0.1:18000/api/v1`。Vite 服务器从不复用，因为残留的 `make dev` Vite 会指向错误的守护进程。

::: warning 修改端口
守护进程的开发 CORS 允许列表固定为 `http://localhost:5173` 和 `http://127.0.0.1:5173`。如果你从其他端口提供界面，还要把 `COFFER_CORS_ORIGINS` 设为那个来源，它会完全替换允许列表。不设的话，守护进程会以 `403 ORIGIN_NOT_ALLOWED` 拒绝每一个浏览器请求，页面报 "Failed to fetch"，`web` 的 spec 全部失败，尽管其实什么都没坏。

如果另一个检出的开发服务器已经占着这两个端口，就把套件挪开：`COFFER_E2E_WEB_PORT=5183 COFFER_E2E_PORT=18200 make verify-e2e`。配置会自己传入对应的 `COFFER_CORS_ORIGINS`，并使用自己的 HOME 指针，两次运行不会共用同一个守护进程。
:::

CI 失败时，`e2e` job 会把 Playwright 报告和 trace，以及隔离守护进程的日志目录和 `daemon.json`，作为 workflow 产物上传。

## 前端测试 {#frontend-tests}

前端测试在 jsdom 环境中使用 Vitest 和 Testing Library。每个测试都放在它所覆盖的模块旁边（`*.test.ts`、`*.test.tsx`），`make verify-unit` 用 `npx vitest run src` 把它们全部运行。`src/test/setup.ts` 加载真实的 i18n 文案目录，所以组件渲染的是真实文案。用真实的 `QueryClientProvider` 渲染，只 mock 网络边界：`src/lib/api/*` 模块，或者聊天用的 `streamClient`。约定见[前端](/zh/contributing/frontend#testing)。

在本地运行前端测试套件时，请使用 **Node 20**，也就是 CI 使用的版本。

## `make verify` 运行了什么 {#what-make-verify-runs}

同一台机器上同一时间只跑一份集成测试。`make verify-integration` 会拿一把全机锁（`~/.cache/coffer/verify-integration.lock`）：另一个 worktree 或会话的第二份会排队等第一份跑完，而不是互相拖慢到依赖时间的测试纷纷失败；`COFFER_VERIFY_LOCK=off` 可以跳过这把锁。每个集成测试还有 300 秒的上限（`PYTEST_TIMEOUT`），卡住的测试会按名字报失败，而不是把整轮拖住。

`make verify` 先运行 `lint`，然后依次运行 `docs-build`（本站的 VitePress 构建，有解析不了的 Mermaid 图或失效链接就失败）、`verify-unit`、`verify-integration`、`verify-contract` 和 `verify-acceptance`。最后，无论成功还是失败，它都会打印每个阶段的耗时，并把列表保存在 `.coffer-verify.timings`。`make verify-all` 额外加上 `verify-e2e`。

`make lint` 是完整的静态门禁，不只是一次格式化检查。它按顺序运行以下步骤：

| 门禁 | 保护什么 |
| --- | --- |
| `scripts/check_file_sizes.py` | 文件大小限制：后端 Python 和桌面 Rust ≤ 400 行，前端页面 ≤ 200，组件 ≤ 250，hook 和工具函数 ≤ 300。生成的文件除外 |
| 契约新鲜度 | 每项能力的 `api.openapi.yaml` 都由 Pydantic 模型重新生成，必须和签入的文件一致，并且每个对外提供的路由都必须属于某项能力。用 `make contracts` 修复 |
| `scripts/check_response_models.py` | 每个 FastAPI 路由都声明 `response_model=`（流式和文件响应用 `response_class=`），所以没有路由返回无类型的 `dict` |
| `scripts/check_adr_index.py` | `docs/decisions/` 内的链接都能解析，并且决策记录索引恰好列出现存的所有决策记录 |
| `scripts/check_spec_citations.py` | 任何被跟踪文件中的每一处 `spec <capability> "<Title>"` 引用都指向一条真实存在的需求。在 `openspec/` 内，相对于规格的链接（`[x](../skill-manager/spec.md) "<Title>"`）和指向文件所在能力的 `see "<Title>"` 也会检查。跨行折断的标题按合并成一行来读 |
| `scripts/check_architecture_doc.py` | `docs-site/architecture/layering.md` 中的代码布局树列出了每个包、没有列出已经不存在的东西，并且架构页面列出了每一个内置 `coffer__*` 工具 |
| `scripts/check_pyinstaller_specs.py` | 三个 PyInstaller spec 指向存在的文件，并保留 `-X utf8` 运行时选项。没有任何 pull request job 运行 PyInstaller，所以这是唯一的早期预警 |
| `scripts/check_cli_reference.py` | 本站生成的 CLI 参考页面（英文和中文）与代码一致。用 `make docs-reference` 修复偏移 |
| `scripts/check_docs_locales.py` | 本站的英文树和中文树一一对应：页面、侧边栏条目、标题锚点，以及中文页面链接到中文页面 |
| `scripts/check_error_codes_reference.py` | 中英文的[错误码](/zh/reference/error-codes)页列出守护进程在 `surfaces/http/errors.py` 中映射的每一个错误码，每个都标明它实际使用的 HTTP 状态码，且不列出守护进程没有映射的错误码 |
| `scripts/check_removed_commands.py` | `docs-site/` 下的页面、仓库指南（`README.md`、`README.zh-CN.md`、`AGENTS.md`、`CONTRIBUTING.md`、`.agents/`、除 ADR 以外的 `docs/`）、规格、桌面壳源文件、随包发布的技能正文、Web 界面源文件或 e2e spec 中，都没有引用已被移除的 `coffer` 命令、选项或 `coffer__` 工具。每次命中都会写明应改用的命令；有意提到它的行（比如断言它已被移除的场景）列在脚本的 `ALLOWED` 里 |
| `scripts/check_platform_calls.py` | 基础设施层平台部分以外的代码都不询问自己运行在哪个操作系统上。测试不受此限制。见[平台端口](/zh/architecture/platform) |
| `scripts/check_coffer_paths.py` | 每个 `~/.coffer` 路径都在 `infrastructure/vault/home.py` 里构造，它是唯一知道目录布局并遵循 `HOME` 的模块；其他模块自己构造路径就会失败。迁移和真实 home 的测试守卫不受此限制 |
| `scripts/check_agent_type_branches.py` | 智能体描述符及其切面以外的代码都不按智能体类型分支。见[智能体切面](/zh/architecture/agent-facets) |
| `scripts/check_frontend_colors.py` | 前端在 `src/index.css` 之外没有颜色字面量；每种颜色都是主题 token |
| `scripts/check_ignored_sources.py` | 没有 `.gitignore` 规则隐藏源码树中的文件，也没有未锚定的模式命中 `lib/` 或 `env/` 这类常见源码文件夹名（那样会在任意深度隐藏该文件夹） |
| `scripts/check_bare_tasks.py` | `backend/coffer/` 下的模块启动的裸 `asyncio.create_task` / `ensure_future` 不得超出脚本中列出的额度。后台工作一律走 supervisor（它给任务命名、记录崩溃并在关停时取消）；在原地被 await 的任务连同理由登记在脚本里 |
| `ruff check`、`ruff format --check` | 按 `backend/pyproject.toml` 中的规则，对 `backend/` 和 `evals/` 做 lint 和格式检查 |
| `mypy` | 在设置了 `strict = true` 的 `backend/pyproject.toml` 下，对整个 `coffer` 包做类型检查 |
| `lint-imports` | import-linter 契约：分层方向（`surfaces` → `application` → `domain`）、纯净的 `domain`、`keyring` 只限于密钥代码、类型之间不跨类型导入，以及特定库只限于各自的适配器 |
| `scripts/dump_i18n_backend_keys.py --check` | 每个后端错误码和审计事件类型在前端 locale 覆盖测试读取的 fixture 中都有条目，所以不会有未翻译的上线 |
| `npm run lint` | `codegen:check`（生成的 API 类型与契约一致，API 模块中没有手写的传输类型），然后是 ESLint |
| `npm run typecheck` | 对前端运行 `tsc` |
| `npm run knip` | 前端死代码：未使用的文件、导出和依赖 |

当 `frontend/node_modules` 不存在时，四个前端步骤会被跳过。CI 总会安装它。`lint-imports` 以 `PYTHONPATH=backend` 运行，这样在 git worktree 里它分析的是本检出目录，而不是可编辑安装指向的那个。

::: tip 只改文档也可能让 `make lint` 失败
引用、决策记录索引、架构文档、已移除命令和参考页这几道门禁都会读取 Markdown。改完文档后也要运行 `make lint`。
:::

`make hooks` 安装的 pre-commit Hook 会在提交时追加一些快速检查：行尾空白、文件末尾、YAML、TOML 和 JSON 语法、合并冲突标记、大文件、ruff、prettier，以及对提交信息的 commitlint。

## CI workflow {#ci-workflows}

| Workflow | 触发条件 | 运行什么 |
| --- | --- | --- |
| `verify.yml` | 指向 `main` 的 pull request、推送到 `main` | 并行的多个 job，每个运行一个 Makefile 目标：`lint`（`make lint`）、`test-unit`、`test-integration`、`test-contract`、`test-benchmark`、`test-e2e`、`test-visual`（`make verify-<tier>`；视觉 job 只报告不阻塞，`continue-on-error`，直到基线提交为止）、`audit-acceptance`（`make verify-acceptance`）和 `secrets-scan`（用 gitleaks 扫描完整历史，和本地 `make verify-secrets` 一样）。集成层级被拆成四个并排运行的分片，按每个测试上次测得的耗时做均衡，最后有一个检查只在所有分片都通过时才通过。只改动了没有测试读取的文档的 pull request 会跳过测试 job；检查文档的门禁仍然运行，被跳过的检查计为通过 |
| `ci.yml` | 推送到 `main` 和 `feature/**`、手动触发（`workflow_dispatch`）、每周定时 | 一个 `make verify` job。定时运行的是**最新依赖金丝雀**：它用 `uv sync --upgrade` 而不是锁文件安装，所以破坏 Coffer 的上游发布会按计划暴露出来 |
| `pr-title.yml` | pull request 被创建或编辑 | 按 `.commitlintrc.yaml` 检查标题 |
| `desktop.yml` | `main` 上 `desktop/**` 或 `Makefile` 有改动 | `make desktop-lint` 和 `make desktop-test` |
| `evals.yml` | `main` 上 `evals/`、MCP 领域代码（`backend/coffer/domain/mcp/`）或锁文件有改动 | `make eval`：确定性评测套件，以相对已提交基线的回归作为门禁 |
| `pages.yml` | `docs-site/**` 有改动 | 用本站自带的 Mermaid 版本解析每一张 Mermaid 图（`docs-site/scripts/check_mermaid.mjs`，由 `npm run build` 运行），构建本站，并从 `main` 部署 |
| `release.yml` | 一个 `v*` 标签 | 面向 Apple 芯片 macOS 的冻结二进制、CLI 压缩包和桌面 `.dmg`，然后创建 GitHub Release |

除了金丝雀之外，CI 中的每次后端安装都从 `backend/uv.lock` 冻结安装。金丝雀变红意味着某个上游发布破坏了东西，而不是你的锁文件出现了偏移。

## 评测 {#evals}

有些行为是不确定的或基于排序的，比如工具搜索和工具路由。它们由 [`evals/`](https://github.com/wyx-sg/Coffer/tree/main/evals) 中的评测框架衡量，而不是用通过/失败的测试。`make eval` 运行确定性套件，相对已提交的基线出现回归就失败。`make eval-routing` 额外加上一个需要本地 LLM 的套件。`make eval-curate` 把采集到的真实查询变成带标注的黄金用例。[`.agents/harness.md`](https://github.com/wyx-sg/Coffer/blob/main/.agents/harness.md) 描述了采集、整理和门禁这一循环。

## 相关 {#related}

- [开发环境搭建](/zh/contributing/development)
- [规格驱动的工作流](/zh/contributing/spec-workflow)
- [前端](/zh/contributing/frontend)
- [分层与代码布局](/zh/architecture/layering)
