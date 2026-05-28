# Testing — 4 层 + 验收标记

> English: [testing.md](./testing.md)

Coffer 用四个测试层，在 CI 中并行运行。`spec.md` 里的验收场景以标记形式横跨各层，而不是单独成层。本文档反映的是当下已经接通的状态；未实现的部分会显式标注。

## 各层一览

| Tier            | Tests what                                                                                                                                          | Speed budget (per file) | Tools                                                                                                                                                                                                    | Runs in `make verify`?          |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| **Unit**        | Pure functions, single class, domain logic, value objects. No I/O. Fake ports / no real infrastructure. Enforced by `scripts/check_unit_purity.py`. | < 100 ms                | `pytest` (backend), `vitest` (frontend)                                                                                                                                                                  | yes                             |
| **Integration** | Multiple modules + real local infrastructure: real SQLite, real subprocess, real filesystem, `keyring` test backend. No network.                    | < 2 s                   | `pytest` + `httpx.AsyncClient` / `fastapi.TestClient` (backend), `vitest` + jsdom + React Testing Library across multiple components (frontend)                                                          | yes                             |
| **Contract**    | Wire-format conformance: hand-written `*.openapi.yaml` ↔ Pydantic models ↔ TS types. Blocks PR on drift.                                          | < 1 s                   | Currently: `pytest` + `TestClient` manual assertions on `/openapi.json`. **Future** (add when contract surface grows): `schemathesis` for backend fuzzing, `openapi-typescript` round-trip for TS types. | yes                             |
| **E2E**         | Full stack via real surfaces: browser → frontend → backend → SQLite.                                                                                | < 30 s                  | `Playwright` (web).                                                                                                                                                                                      | NO (separate `make verify-e2e`) |

**金字塔形状**：unit ≫ integration > contract > e2e（按测试数量计）。

每条测试的预算只是参考，不是卡口——单条慢测试不算 CI 失败。它们的作用是：一旦某条测试比所在层的预算慢一个数量级，就提示「层级是不是放错了？」。不强制总套件预算；套件会随项目成长。

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

**前端** —— unit 与源码同处，更高层放在 `tests/<tier>/`：

```
frontend/src/
├── App.tsx
├── App.test.tsx               # unit (co-located, *.test.tsx pattern)
├── components/Button.tsx
└── components/Button.test.tsx # unit (co-located)

frontend/tests/
└── integration/               # multi-component + provider + hook scenarios
    └── *.test.tsx
```

（`frontend/tests/contract/` 在第一个前后端类型一致性测试落地时新建。）

**E2E** —— 顶层目录，跨越前后端边界：

```
e2e/
├── playwright.config.ts
├── package.json               # own npm package — separate node_modules
└── web.spec.ts                # Playwright browser tests
```

## 布局理由

- **为什么 `e2e/` 在顶层（而不在 `frontend/` 或 `backend/` 之下）**：e2e 是栈*之间*的接缝——Playwright 测试要走 browser → frontend → backend → SQLite。把它塞到任一栈下都会误标归属。它还是独立的 npm 包（自己的 `playwright.config.ts`、自己的 `node_modules`、独立的 Playwright 浏览器安装），所以不能与前端的 Vite/Vitest workspace 共用。
- **为什么前端 unit 测试与源码同处，后端用 `tests/<tier>/`**：各自遵循各自生态的惯例。Vitest 在源码旁发现 `*.test.tsx`；pytest 期望一棵 `tests/` 树。我们不和任何一边较劲。
- **何时在一个目录内继续拆分**：当某一层出现两类明显不同的测试家族（例如 `e2e/` 同时有浏览器测试和 Python MCP-shim 套件），就拆成子目录（`e2e/web/`、`e2e/mcp/`），并相应拆分 CI job。还不存在的测试不要预先拆分。

## 命名

- 后端 pytest 文件：`test_<thing>.py`。测试函数：`test_<scenario>`（snake_case）。
- 前端 vitest 文件：组件测试 `<Source>.test.tsx`；工具函数测试 `<Source>.test.ts`。
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

**TypeScript（vitest / Playwright）：**

```ts
import { acceptance } from "@/test/acceptance";

acceptance("001-foo", "register and list", async () => {
  // ...
});
```

helper 是个薄包装，把 spec + scenario 记进测试名。实现在 `frontend/src/test/acceptance.ts`；`frontend/src/test/acceptance.test.ts` 里的 smoke 测试锁住其接线。审计正则同时匹配 `acceptance(...)` 与历史遗留的 `test.acceptance(...)` 形式。

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
make verify-e2e          # e2e tier only (Playwright)
make verify-acceptance   # audit spec.md scenarios vs test markers

make lint                # ruff + mypy + eslint + tsc
make format              # ruff format + prettier
```

### 验证目标——每个 target 做了什么

| Target                    | 实际执行                                                                                                                                                                                       | 何时使用                                                              |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `make verify`             | `lint` → `verify-unit` → `verify-integration` → `verify-contract` → `verify-acceptance`。"提 PR 前"门槛。                                                                                      | 每次推送与 PR 前。CI 并行跑相同的若干层。                             |
| `make verify-all`         | `verify` 再加上 `verify-e2e`（Playwright + 任何 `e2e/*.py` pytest 套件）。                                                                                                                     | 合并任何触碰到 surface（HTTP、CLI、shim、frontend）的变更之前。       |
| `make verify-unit`        | `scripts/check_unit_purity.py`（AST 扫描禁止的 I/O 导入），再 `pytest backend/tests/unit`，再 `vitest run src`。                                                                               | 在纯 domain 代码上跑紧凑的 TDD 循环。                                 |
| `make verify-integration` | `pytest backend/tests/integration` 与 `vitest run tests/integration`。                                                                                                                         | 改动 application service、SQLAlchemy repo、HTTP route 或 CLI 接线后。 |
| `make verify-contract`    | `pytest backend/tests/contract` 与 `vitest run tests/contract`。                                                                                                                               | 编辑 `specs/*/contracts/api.openapi.yaml` 或 Pydantic API schema 后。 |
| `make verify-e2e`         | Playwright (`e2e/playwright.config.ts`)，外加任何 `e2e/*.py` pytest 套件（当前 MCP shim e2e 就在那里）。                                                                                       | 改动 daemon ↔ shim ↔ MCP 客户端边界后。                             |
| `make verify-acceptance`  | `scripts/audit_acceptance.py`：解析每个 `specs/*/spec.md` 的 `## Acceptance Scenarios` 块以及每个 `@acceptance(spec=…, scenario=…)` 标记；遇到未覆盖或孤儿 scenario 即失败。                   | 每次编辑 spec.md 后跑；很轻量，不需要任何依赖。                       |
| `make bundle-binaries`    | `scripts/build_binaries.sh`——在宿主机上用 PyInstaller 构建 `dist/coffer-daemon` 与 `dist/coffer-mcp-shim`。见 [ADR-007](../docs/decisions/ADR-007-distribution-pyinstaller-tauri-sidecar.md)。 | 在干净机器上验证分发包之前。                                          |

## CI Jobs

`.github/workflows/verify.yml` 并行运行下列 job；全部通过才能合并：

| Job           | What                                                      |
| ------------- | --------------------------------------------------------- |
| `lint`        | ruff + mypy + eslint + tsc                                |
| `unit`        | `make verify-unit` (purity check + backend + frontend)    |
| `integration` | `make verify-integration`                                 |
| `contract`    | `make verify-contract`                                    |
| `acceptance`  | `python3 scripts/audit_acceptance.py` (no install needed) |
| `e2e`         | `make verify-e2e` (Playwright)                            |

每个层 job 内部同时跑后端和前端部分（所以瓶颈是某一层内更慢的那一栈，而不是跨层）。

## 某层为空时

某一层暂时没有测试时跑起来直接绿（pytest 收集到 0 条；vitest 收集到 0 条）。Makefile 会检查层目录是否存在，缺失就静默跳过 —— 不要拿不存在的层卡 `make verify`。
