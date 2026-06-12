# Stack — Python 后端

> English: [stack.md](./stack.md)

Coffer 后端用 Python 3.12+。

## 后端 — Python / FastAPI / SQLite

### 语言与版本

- **Python 3.12+**
- **FastAPI** 提供 HTTP surface
- **Pydantic v2** 用于模型与校验
- **SQLite** 通过 **SQLAlchemy 2 (async)** + **`aiosqlite`**（唯一的数据访问路径）
- **`cryptography`**（Fernet）用于信封加密的凭据存储
- **`keyring`** 接 OS keychain（仅凭据模块——主密钥 opt-in + legacy 迁移）
- **`anyio`** + `asyncio` 用于异步与子进程管理

功能相关的库（如 MCP SDK）由第一个需要它的 spec 引入，不在此预装。

### 架构

分层 DDD（位于 `backend/coffer/` 下）：

```
surfaces/      — entry points; one subdir per surface, defined per spec
application/   — commands, queries, ports (interfaces), shared services
domain/        — entities, value objects, domain services (PURE)
infrastructure/— adapters for SQLite, keyring, and outbound I/O
```

**依赖方向单向**：`surfaces → application → domain`；`infrastructure` 适配 `application` 中定义的 port。`domain/` 保持纯粹。

分层 import 规则、凭据访问规则，以及「跨层公共模块只在第二个 feature 也需要它时才抽取」这条规则都是不变量 (invariant)，其唯一权威源是 [`.specify/memory/constitution.md`](../.specify/memory/constitution.md)。它们落到本代码库时的 Python 具体形态：

- `domain/` 保持纯 Python + Pydantic——不引入 FastAPI、SQLAlchemy、httpx 或其他外部 SDK。
- `application/` 定义 port，由 `infrastructure/` 适配。
- 只有 credential 模块 import `keyring`，其他地方一律传 credential 引用。

### 代码风格

- **Ruff** 做 lint + format。配置在 `backend/pyproject.toml`。
- 整个包跑 **mypy --strict**。
- 文件大小：每个 Python 文件 **≤ 400 行**。
- 每个函数签名都加类型注解。
- 任何跨越边界（HTTP、MCP、SQLite I/O）的数据都用 Pydantic v2 `BaseModel`。

### HTTP 契约（线格式）

任何功能的权威线格式契约都是 `specs/<NNN>-<short-name>/contracts/*.openapi.yaml`（手写、PR 审查）。后端 Pydantic `BaseModel` 手写以匹配该 yaml。每个 HTTP 路由都用 `response_model=<Foo>Response` 声明一个 Pydantic `BaseModel`——绝不用 `dict[str, Any]`。

CI 卡口（第一个功能 spec 落地时同步加入）：`make verify-contract` 在运行时 OpenAPI dump 与任意 spec yaml 结构不一致时驳回 PR。

### 本地开发

```bash
make install                       # one-time setup
make dev                           # backend on :8000
.venv/bin/uvicorn coffer.main:app --reload --port 8000   # backend only
make lint / make test / make format / make verify
```

## E2E — TypeScript / Playwright

端到端层位于 `e2e/`。仓库主要的 TypeScript surface 是前端
（`frontend/src`，约 18k 行 TS/TSX）；`e2e/` 是在其之上额外的 TypeScript 层。

- **TypeScript 5.x**，ESM 模块（`tsconfig.json`，types 为 `@playwright/test` + `node`）。
- **Playwright**（`@playwright/test`）作为 e2e runner。
- MCP 套件（`e2e/mcp/specs/*.spec.ts`，配置 `e2e/playwright.config.ts`）走通完整链路：
  真实 MCP 客户端 → `coffer-mcp-shim`（stdio）→ daemon（`/mcp` HTTP）→ 上游 MCP
  server → SQLite。测试把 shim 与 daemon 作为 OS 子进程拉起，端到端跨它们驱动 JSON-RPC。
- 跑法：`cd e2e && npm test`（`playwright test`），或 `make verify-e2e`。
