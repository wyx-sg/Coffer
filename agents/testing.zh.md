# Testing — 4 层 + 验收标记

> English: [testing.md](./testing.md)

Coffer 用四个测试层，在 CI 中并行运行。`spec.md` 里的验收场景以标记形式横跨各层，而不是单独成层。本文档反映的是当下已经接通的状态；未实现的部分会显式标注。

## 各层一览

| Tier            | Tests what                                                                                                                                          | Speed budget (per file) | Tools                                                                                                                                                       | Runs in `make verify`?          |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| **Unit**        | Pure functions, single class, domain logic, value objects. No I/O. Fake ports / no real infrastructure. Enforced by `scripts/check_unit_purity.py`. | < 100 ms                | `pytest`                                                                                                                                                     | yes                             |
| **Integration** | Multiple modules + real local infrastructure: real SQLite, real subprocess, real filesystem, `keyring` test backend. No network.                    | < 2 s                   | `pytest` + `httpx.AsyncClient` / `fastapi.TestClient`                                                                                                        | yes                             |
| **Contract**    | Wire-format conformance: hand-written `*.openapi.yaml` ↔ Pydantic models. Blocks PR on drift.                                                       | < 1 s                   | Currently: `pytest` + `TestClient` manual assertions on `/openapi.json`. **Future** (add when contract surface grows): `schemathesis` for backend fuzzing.   | yes                             |
| **E2E**         | Full stack via real surfaces: a real MCP client → `coffer-mcp-shim` (stdio) → daemon (`/mcp` HTTP) → upstream MCP servers → SQLite.                  | < 30 s                  | `Playwright` (`@playwright/test`) + TypeScript 5.x。spec 把真实 shim + daemon 作为 OS 子进程拉起，端到端跨它们驱动 JSON-RPC。                                  | NO (separate `make verify-e2e`) |

**套件形状**：integration ≫ unit > contract > e2e（按测试数量计）。这有意不是经典的 unit 为主的金字塔：integration 层跑真实 SQLite 文件与真实子进程但保持快速（后端全量约 100 秒），所以大多数行为钉在真实接线所在的层。unit 层只留给纯逻辑（由 `scripts/check_unit_purity.py` 机械强制）。

每条测试的预算只是参考，不是卡口——单条慢测试不算 CI 失败。它们的作用是：一旦某条测试比所在层的预算慢一个数量级，就提示「层级是不是放错了？」。不强制总套件预算；套件会随项目成长。

## 覆盖率底线

测试套件就是安全网：**`make verify`(加 `verify-e2e`)绿了，就必须意味着产品是好的，不需要人再手动回归测试。** 这给各个面定下了完整性底线：

1. **每个函数都有单元测试。** 每个函数/方法至少有一个测试真正执行它、并断言它的真实返回值或副作用——包括有意义的分支(错误路径、空/None、边界值),而不是只测 happy path。
2. **每个 HTTP 接口都有测试。** 每个路由(`coffer/surfaces/http/**` 里的每个 method+path)都有测试断言状态码、响应体/结构和副作用——以及它的鉴权与校验失败的响应。
3. **每个 CLI 命令都有测试。** 每个 Typer 命令/子命令(`coffer/surfaces/cli/**`)都有测试断言退出码 **以及** 输出/产生的状态,外加它声明的非零退出路径。
4. **每个核心用户流程都有 e2e 覆盖。** 用户依赖的每条端到端流程(以及 `spec.md` 里每个 `## Acceptance Scenarios` 条目)都有 e2e 或 acceptance 标记的测试,通过真实的表面层驱动它。

**测试必须是真实有用的——绝不能只为了拉高覆盖率数字而写。** 一个测试只有在「真实回归会让它失败」时才配存在。下列反模式要拒绝(评审时要点名):

- **同义反复(Tautological)** —— 断言一个恒为真的东西,或把一个代码从未变换过的字面量原样断言回去(`assert x == x`;断言一个你刚刚穿过无逻辑构造器传进去的输入)。
- **没有有意义的断言** —— 调用了代码,却只检查「没抛异常」/「不是 None」/`status_code == 200`/`exit_code == 0`,而真正的契约(某个具体的值、响应体或副作用)明明可以低成本检查却没检查。(当状态码/退出码本身就是被测契约时——比如缺鉴权返回 `401`、daemon 不可达 `exit 3`——只断言它是合法的。)
- **空循环/空条件** —— `for x in results: assert ...` 却没有保证 `results` 非空的护栏;`if captured: assert ...` 在分支从未跑到时直接通过。要加 `len(...) >= 1` / 无条件断言,让「空」也能失败。
- **过度 Mock** —— mock 掉被测单元本身,或 mock 太多以致测试只验证了 mock。在*边界*用真实的 fake(内存 SQLite、`keyring` 测试后端、假的上游 session)是可以的;mock 掉你声称要测的东西则不行。
- **太松** —— 断言(或性能预算)宽到永远不可能失败(`assert len(x) >= 0`、比真实值大 100 倍的延迟上限)。

**怎么衡量。** `pytest --cov=coffer --cov-report=term-missing` 报告行/分支覆盖率;用它找出未测的函数和分支。覆盖率是*找地板的工具,不是目标*——一行被同义反复的测试「覆盖」了,本质上仍是未测。确实不可达的防御性代码,用 `# pragma: no cover` 加一行理由排除,而不是用假测试去凑。新代码不应降低它所触碰文件的覆盖率。

## 测试文件位置

**后端** —— 按层分目录：

```
backend/tests/
├── unit/                      # pure logic, no I/O (purity-checked)
│   └── <module>/test_*.py
├── integration/               # real local I/O
│   └── <module>/test_*.py
└── contract/                  # OpenAPI / wire-format conformance
    └── test_*.py
```

**E2E** —— 顶层目录，跨越 daemon ↔ shim ↔ MCP 客户端边界：

```
e2e/
├── playwright.config.ts       # Playwright runner 配置（mcp project）
├── package.json               # @playwright/test + TypeScript
└── mcp/
    └── specs/                 # real MCP client → shim → daemon
        └── *.spec.ts
```

跑法：`cd e2e && npm test`（`playwright test`）。

## 布局理由

- **为什么 `e2e/` 在顶层（而不在 `backend/` 之下）**：e2e 是经由真实 surface 走通的接缝——MCP 客户端通过 stdio 与 `coffer-mcp-shim` 对话，shim 通过 `/mcp` 与 daemon 对话，daemon 再扇出到上游 MCP server 与 SQLite。把它塞到 `backend/` 之下会误标归属；它驱动的是组装好的产品，而非某个包的内部。
- **何时在一个目录内继续拆分**：当某一层出现两类明显不同的测试家族，就拆成子目录，并相应拆分 CI job。还不存在的测试不要预先拆分。

## 命名

- 后端 pytest 文件：`test_<thing>.py`。测试函数：`test_<scenario>`（snake_case）。
- 测试名描述行为，不描述实现：`test_health_returns_ok_with_version` ✓，`test_handler_calls_method` ✗。

## 验收场景 —— 跨层标记

`spec.md` 中 `## Acceptance Scenarios` 下的每个场景，必须在任意层（通常是 integration 或 e2e）至少有一个测试覆盖。给测试打标记，以便审计覆盖情况。

**Spec 约定** —— 在 `## Acceptance Scenarios` 下，用 `### <title>` 列出场景（可选的 `Scenario:` 前缀会被剥掉）：

```markdown
## Acceptance Scenarios

### register and list

**Given** ..., **When** ..., **Then** ...

### Scenario: re-register existing

...
```

spec ID 就是 spec 文件夹名（例如 `specs/001-foo/spec.md` → `001-foo`）。

**Python（pytest）：**

```python
import pytest

@pytest.mark.acceptance(spec="001-foo", scenario="register and list")
def test_register_then_appears_in_list(...):
    ...
```

该标记在 `backend/pyproject.toml` 的 `[tool.pytest.ini_options]` 中注册，并开启 `--strict-markers` —— 拼错会导致 collection 失败。

**覆盖度审计** —— `scripts/audit_acceptance.py`（通过 `make verify-acceptance` 运行）扫描每个 `specs/*/spec.md` 和每个测试文件，遇到以下情况会失败：

- spec.md 中列出的场景没有对应的标记（覆盖缺失）
- 标记引用了不存在的场景 / spec ID（孤儿标记 —— 通常意味着 spec 被改过名）

仅依赖标准库，毫秒级运行。零 spec 时空跑通过 —— 在第一个 spec 落地前轨道就已铺好。

## Unit 层纯净度护栏

`scripts/check_unit_purity.py` 用 AST 扫描 `backend/tests/unit/**/*.py`，一旦某测试 import 了已知 I/O 模块（`subprocess`、`sqlite3`、`httpx`、`fastapi.testclient`、`socket`、`requests`、`urllib.request`、`aiohttp`、`keyring`）就失败。在 `make verify-unit` 的第一步运行。

unit 层「无 I/O」规则（上表第 1 行）以前只是文化约束。脚本把它变成机械约束：偷偷写 `from fastapi.testclient import TestClient` 的测试会被定位到文件:行，并提示该挪去 integration。要新增禁用模块，编辑脚本里的 `BANNED` 字典。

## Mock 哲学

只要速度允许，**优先用真实而非 mock**：

- integration 测试用真 SQLite（内存或临时文件）。
- 子进程生命周期测试用真子进程（跑短命子进程）。
- 真文件系统（用 `tmp_path`）。
- `keyring` 测试后端（内存）—— 不是 mock；是另一套真实现。

只在以下情况 mock：

- 依赖**非本地**（外部 HTTP 服务、LLM API）。
- 依赖**非确定**，且测试关心这个不确定性（系统时钟、随机性）。
- 依赖**慢**（最后的退路 —— 通常意味着测试放错了层）。

## Make 目标

```bash
make verify              # fast path: lint + unit + integration + contract + acceptance audit
make verify-all          # verify + e2e (full suite)

make verify-unit         # unit-purity guardrail + unit tier
make verify-integration  # integration tier only
make verify-contract     # contract tier only
make verify-e2e          # e2e tier only (Playwright MCP e2e: shim + daemon)
make verify-acceptance   # audit spec.md scenarios vs test markers

make lint                # ruff + mypy
make format              # ruff format
```

### 验证目标——每个 target 做了什么

| Target                    | 实际执行                                                                                                                                                                       | 何时使用                                                              |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `make verify`             | `lint` → `verify-unit` → `verify-integration` → `verify-contract` → `verify-acceptance`。"提 PR 前"门槛。                                                                      | 每次推送与 PR 前。CI 并行跑相同的若干层。                             |
| `make verify-all`         | `verify` 再加上 `verify-e2e`。                                                                                                                                                | 合并任何触碰到 surface（HTTP、CLI、shim）的变更之前。                 |
| `make verify-unit`        | `scripts/check_unit_purity.py`（AST 扫描禁止的 I/O 导入），再 `pytest backend/tests/unit`。                                                                                   | 在纯 domain 代码上跑紧凑的 TDD 循环。                                 |
| `make verify-integration` | `pytest backend/tests/integration`。                                                                                                                                          | 改动 application service、SQLAlchemy repo、HTTP route 或 CLI 接线后。 |
| `make verify-contract`    | `pytest backend/tests/contract`。                                                                                                                                             | 编辑 `specs/*/contracts/api.openapi.yaml` 或 Pydantic API schema 后。 |
| `make verify-e2e`         | `cd e2e && playwright test` —— Playwright/TypeScript 的 MCP e2e 套件（`e2e/mcp/specs/*.spec.ts`）驱动一个真实 MCP 客户端经由 shim 走到 daemon 与上游 server。                  | 改动 daemon ↔ shim ↔ MCP 客户端边界后。                             |
| `make verify-acceptance`  | `scripts/audit_acceptance.py`：解析每个 `specs/*/spec.md` 的 `## Acceptance Scenarios` 块以及每个 `@acceptance(spec=…, scenario=…)` 标记；遇到未覆盖或孤儿 scenario 即失败。 | 每次编辑 spec.md 后跑；很轻量，不需要任何依赖。                       |

## CI Jobs

`.github/workflows/verify.yml` 并行运行下列 job；全部通过才能合并：

| Job           | What                                                      |
| ------------- | --------------------------------------------------------- |
| `lint`        | ruff + mypy                                               |
| `unit`        | `make verify-unit` (purity check + backend)               |
| `integration` | `make verify-integration`                                 |
| `contract`    | `make verify-contract`                                    |
| `acceptance`  | `python3 scripts/audit_acceptance.py` (no install needed) |
| `e2e`         | `make verify-e2e` (Playwright MCP e2e: shim + daemon)     |

## 某层为空时

某一层暂时没有测试时跑起来直接绿（pytest 收集到 0 条）。Makefile 会检查层目录是否存在，缺失就静默跳过 —— 不要拿不存在的层卡 `make verify`。
