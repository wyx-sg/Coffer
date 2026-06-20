# Tasks — 001 MCP Gateway

> **For agentic workers:** Use `superpowers:subagent-driven-development` (recommended)
> or `superpowers:executing-plans` to implement this plan task-by-task. Checkbox
> (`- [ ]`) syntax tracks progress.

**Input**: design documents from [`./`](./)
**Prerequisites**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/api.openapi.yaml](./contracts/api.openapi.yaml)

**Convention**: `[T###] [P?] [Story] Description`. `[P]` = parallelisable (different
files, no dependency). `[USn]` = user story tag from [spec.md](./spec.md). TDD
sub-steps follow the writing-plans skill: write failing test → run it → minimal
implementation → run it → commit. Skip sub-step 1+2 only when the task is pure
config (dep add, schema migration, etc.).

**File-size guard**: backend files ≤ 400 LOC. `scripts/check_file_sizes.py` enforces.

**Commit convention** (per [`agents/workflow.md`](../../agents/workflow.md)): `<type>(mcp-gateway): <subject>`, ≤ 72-char subject, Conventional Commits + `Co-authored-by: Claude <noreply@anthropic.com>` footer.

---

## Phase 1 — Setup (shared infrastructure)

Goal: dependencies, scaffolding, importlinter contracts, structured logging,
SQLAlchemy + Alembic skeleton, FastAPI + Typer composition roots, daemon
discovery primitives, `/api/v1/daemon/status`. No business logic.

**Checkpoint**: `make verify` green; `coffer daemon start` → `curl /api/v1/daemon/status` → `{status: "ready"}`.

---

### T001 [P] Add backend runtime dependencies

**Files:**

- Modify: `backend/pyproject.toml`

- [x] **Step 1: Update the `[project]` dependencies block**

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.7",
    "sqlalchemy[asyncio]>=2.0,<3.0",
    "aiosqlite>=0.20",
    "alembic>=1.13",
    "keyring>=25.0",
    "httpx>=0.27",
    "typer>=0.12",
    "rich>=13.7",
    "structlog>=24.1",
    "mcp>=1.0",
    "psutil>=5.9",
]
```

- [x] **Step 2: Reinstall to validate**

```bash
.venv/bin/pip install -e ./backend[dev]
```

Expected: install succeeds; `python -c "import sqlalchemy, alembic, typer, structlog, mcp, psutil"` runs clean.

- [x] **Step 3: Commit**

```bash
git add backend/pyproject.toml
git commit -m "build(mcp-gateway): add runtime dependencies for the daemon"
```

---

### T002 Add importlinter contracts 5 (cross-kind isolation) and 6 (kind-agnostic core)

**Files:**

- Modify: `backend/pyproject.toml`

- [x] **Step 1: Append two contracts under `[tool.importlinter]`**

```toml
# Contract 5: cross-kind imports forbidden. As more kinds land, append to each
# layer's source_modules. With only `mcp` registered, this is vacuously true
# but the rule is in place from day one.
[[tool.importlinter.contracts]]
name = "Cross-kind imports forbidden (mcp)"
type = "forbidden"
source_modules = [
    "coffer.domain.mcp",
    "coffer.application.mcp",
    "coffer.infrastructure.mcp",
    "coffer.surfaces.http.mcp",
]
forbidden_modules = []   # populated when a second kind ships

# Contract 6: kind-agnostic core does not import kind-specific modules.
[[tool.importlinter.contracts]]
name = "Kind-agnostic core does not import kind-specific code"
type = "forbidden"
source_modules = [
    "coffer.application.resource_service",
    "coffer.application.audit_service",
    "coffer.application.retention_service",
    "coffer.application.retention_worker",
    "coffer.domain.resource",
    "coffer.domain.audit",
    "coffer.domain.retention",
    "coffer.infrastructure.persistence.models",
    "coffer.surfaces.http.resource_routes",
    "coffer.surfaces.http.audit_routes",
    "coffer.surfaces.http.retention_routes",
]
forbidden_modules = [
    "coffer.domain.mcp",
    "coffer.application.mcp",
    "coffer.infrastructure.mcp",
    "coffer.surfaces.http.mcp",
]
```

- [x] **Step 2: Run importlinter**

```bash
.venv/bin/lint-imports
```

Expected: passes (no violations yet because the kind modules are not created).

- [x] **Step 3: Commit**

```bash
git add backend/pyproject.toml
git commit -m "chore(mcp-gateway): add importlinter contracts 5 and 6"
```

---

### T003 [P] Structured logging setup (structlog + trace_id contextvar)

**Files:**

- Create: `backend/coffer/infrastructure/logging/__init__.py` (empty)
- Create: `backend/coffer/infrastructure/logging/setup.py`
- Create: `backend/tests/unit/infrastructure/logging/__init__.py` (empty)
- Create: `backend/tests/unit/infrastructure/logging/test_trace_id.py`

- [x] **Step 1: Write failing test**

```python
# backend/tests/unit/infrastructure/logging/test_trace_id.py
from coffer.infrastructure.logging.setup import bind_trace_id, get_trace_id

def test_bind_and_get_trace_id():
    bind_trace_id("abc-123")
    assert get_trace_id() == "abc-123"

def test_trace_id_defaults_to_dash():
    bind_trace_id(None)
    assert get_trace_id() == "-"
```

- [x] **Step 2: Run; expect import error**

```bash
.venv/bin/pytest backend/tests/unit/infrastructure/logging/test_trace_id.py -v
```

- [x] **Step 3: Implement**

```python
# backend/coffer/infrastructure/logging/setup.py
"""structlog configuration + trace-id contextvar."""

from __future__ import annotations
import logging
import sys
from contextvars import ContextVar
from typing import Final

import structlog

_TRACE_ID: ContextVar[str | None] = ContextVar("coffer_trace_id", default=None)
_SENTINEL: Final = "-"


def bind_trace_id(trace_id: str | None) -> None:
    _TRACE_ID.set(trace_id)


def get_trace_id() -> str:
    return _TRACE_ID.get() or _SENTINEL


def _add_trace_id(_, __, event_dict: dict[str, object]) -> dict[str, object]:
    event_dict.setdefault("trace_id", get_trace_id())
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Idempotent global structlog setup; safe to call multiple times."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=level,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_trace_id,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level)
        ),
        cache_logger_on_first_use=True,
    )
```

- [x] **Step 4: Run; expect pass**

```bash
.venv/bin/pytest backend/tests/unit/infrastructure/logging/test_trace_id.py -v
```

- [x] **Step 5: Commit**

```bash
git add backend/coffer/infrastructure/logging/ backend/tests/unit/infrastructure/logging/
git commit -m "feat(mcp-gateway): structlog setup with trace_id contextvar"
```

---

### T004 SQLAlchemy declarative base + async engine factory

**Files:**

- Create: `backend/coffer/infrastructure/persistence/__init__.py` (empty)
- Create: `backend/coffer/infrastructure/persistence/base.py`
- Create: `backend/coffer/infrastructure/persistence/engine.py`
- Create: `backend/tests/integration/infrastructure/persistence/__init__.py` (empty)
- Create: `backend/tests/integration/infrastructure/persistence/test_engine.py`

- [x] **Step 1: Write failing integration test**

```python
# backend/tests/integration/infrastructure/persistence/test_engine.py
import pytest
from sqlalchemy import text
from coffer.infrastructure.persistence.engine import create_async_engine_with_pragmas

@pytest.mark.asyncio
async def test_pragmas_applied(tmp_path):
    db = tmp_path / "coffer.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db}")
    async with engine.connect() as conn:
        journal_mode = await conn.scalar(text("PRAGMA journal_mode;"))
        fk = await conn.scalar(text("PRAGMA foreign_keys;"))
    assert journal_mode == "wal"
    assert fk == 1
    await engine.dispose()
```

- [x] **Step 2: Run; expect import failure**

- [x] **Step 3: Implement**

```python
# backend/coffer/infrastructure/persistence/base.py
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared metadata for every kind's ORM models."""
```

```python
# backend/coffer/infrastructure/persistence/engine.py
from __future__ import annotations
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

_PRAGMAS = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA cache_size = -64000",
    "PRAGMA temp_store = MEMORY",
)


def create_async_engine_with_pragmas(url: str) -> AsyncEngine:
    engine = create_async_engine(url, future=True, echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_conn, _record) -> None:
        cursor = dbapi_conn.cursor()
        for pragma in _PRAGMAS:
            cursor.execute(pragma)
        cursor.close()

    return engine


def session_maker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)
```

- [x] **Step 4: Run; expect pass.**

- [x] **Step 5: Commit**

```bash
git add backend/coffer/infrastructure/persistence/ backend/tests/integration/infrastructure/persistence/
git commit -m "feat(mcp-gateway): SQLAlchemy async engine with required PRAGMAs"
```

---

### T005 Alembic skeleton + env.py

**Files:**

- Create: `backend/coffer/infrastructure/persistence/migrations/__init__.py` (empty)
- Create: `backend/coffer/infrastructure/persistence/migrations/alembic.ini`
- Create: `backend/coffer/infrastructure/persistence/migrations/env.py`
- Create: `backend/coffer/infrastructure/persistence/migrations/script.py.mako`
- Create: `backend/coffer/infrastructure/persistence/migrations/versions/__init__.py` (empty)

- [x] **Step 1: Author `alembic.ini`** (concise — full file ≤ 30 lines)

```ini
[alembic]
script_location = %(here)s
prepend_sys_path = ../../../..
sqlalchemy.url = driver://overridden-in-env
file_template = %%(year)d%%(month).2d%%(day).2d_%%(rev)s_%%(slug)s

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

- [x] **Step 2: Author `env.py`**

```python
# backend/coffer/infrastructure/persistence/migrations/env.py
from __future__ import annotations
import asyncio
import os
import pathlib
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence import models  # noqa: F401 — register tables
# Kind-specific models are imported here as kinds land:
# from coffer.infrastructure.mcp import persistence as _mcp_persistence  # noqa: F401

from coffer.infrastructure.persistence.engine import create_async_engine_with_pragmas

cfg = context.config
fileConfig(cfg.config_file_name)

target_metadata = Base.metadata


def _db_url() -> str:
    return os.environ.get(
        "COFFER_DB_URL",
        f"sqlite+aiosqlite:///{pathlib.Path.home()}/.coffer/coffer.db",
    )


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine_with_pragmas(_db_url())
    async with engine.connect() as conn:
        await conn.run_sync(_run_migrations)
    await engine.dispose()


def run_migrations_offline() -> None:
    context.configure(url=_db_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_run_async())
```

- [x] **Step 3: Author `script.py.mako`** (single-line note: use Alembic default — `alembic init` template suffices; copy as-is from a freshly-`alembic init`-ed directory).

- [x] **Step 4: Commit**

```bash
git add backend/coffer/infrastructure/persistence/migrations/
git commit -m "feat(mcp-gateway): Alembic env wired to shared metadata"
```

---

### T006 HTTP error envelope + global exception handler

**Files:**

- Create: `backend/coffer/domain/errors.py`
- Create: `backend/coffer/surfaces/http/__init__.py` (empty)
- Create: `backend/coffer/surfaces/http/errors.py`
- Create: `backend/tests/unit/domain/test_errors.py`

- [x] **Step 1: Write failing test**

```python
# backend/tests/unit/domain/test_errors.py
from coffer.domain.errors import (
    CofferError, ResourceNotFound, ResourceAlreadyExists,
    UnknownKind, ConfigValidationError,
)

def test_resource_not_found_carries_ref():
    err = ResourceNotFound("mcp_server", "filesystem")
    assert err.kind == "mcp_server"
    assert err.name == "filesystem"
    assert "mcp_server:filesystem" in str(err)
    assert isinstance(err, CofferError)

def test_unknown_kind_carries_kind():
    err = UnknownKind("nope")
    assert err.kind == "nope"
    assert isinstance(err, CofferError)
```

- [x] **Step 2: Run; expect fail.**

- [x] **Step 3: Implement**

```python
# backend/coffer/domain/errors.py
"""Domain-level error hierarchy.

Surfaces map these to HTTP status codes via FastAPI exception handlers.
"""
from __future__ import annotations


class CofferError(Exception):
    """Root of every domain-raised exception."""
    code: str = "INTERNAL_ERROR"


class ResourceNotFound(CofferError):
    code = "RESOURCE_NOT_FOUND"

    def __init__(self, kind: str, name: str) -> None:
        super().__init__(f"resource not found: {kind}:{name}")
        self.kind = kind
        self.name = name


class ResourceAlreadyExists(CofferError):
    code = "RESOURCE_ALREADY_EXISTS"

    def __init__(self, kind: str, name: str) -> None:
        super().__init__(f"resource already exists: {kind}:{name}")
        self.kind = kind
        self.name = name


class UnknownKind(CofferError):
    code = "UNKNOWN_KIND"

    def __init__(self, kind: str) -> None:
        super().__init__(f"unknown kind: {kind!r}")
        self.kind = kind


class ConfigValidationError(CofferError):
    code = "CONFIG_INVALID"


class CredentialMissing(CofferError):
    code = "CREDENTIAL_MISSING"

    def __init__(self, ref: str) -> None:
        super().__init__(f"credential not found in keychain: {ref}")
        self.ref = ref


class CredentialLocked(CofferError):
    code = "CREDENTIAL_LOCKED"


class UpstreamUnavailable(CofferError):
    code = "UPSTREAM_UNAVAILABLE"


class UpstreamTimeout(CofferError):
    code = "UPSTREAM_TIMEOUT"


class ToolDisabled(CofferError):
    code = "TOOL_DISABLED"


class InvalidPrefix(CofferError):
    code = "INVALID_PREFIX"
```

```python
# backend/coffer/surfaces/http/errors.py
from __future__ import annotations
from typing import Any
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from coffer.domain import errors
from coffer.infrastructure.logging.setup import get_trace_id


_STATUS = {
    "RESOURCE_NOT_FOUND": 404,
    "RESOURCE_ALREADY_EXISTS": 409,
    "UNKNOWN_KIND": 400,
    "CONFIG_INVALID": 422,
    "CREDENTIAL_MISSING": 400,
    "CREDENTIAL_LOCKED": 503,
    "UPSTREAM_UNAVAILABLE": 503,
    "UPSTREAM_TIMEOUT": 504,
    "TOOL_DISABLED": 403,
    "INVALID_PREFIX": 400,
    "INTERNAL_ERROR": 500,
}


def _envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register(app: FastAPI) -> None:
    @app.exception_handler(errors.CofferError)
    async def _handle_coffer(request: Request, exc: errors.CofferError) -> JSONResponse:  # noqa: ARG001
        body = _envelope(exc.code, str(exc))
        resp = JSONResponse(status_code=_STATUS.get(exc.code, 500), content=body)
        resp.headers["X-Coffer-Trace"] = get_trace_id()
        return resp

    @app.exception_handler(ValidationError)
    async def _handle_pydantic(request: Request, exc: ValidationError) -> JSONResponse:  # noqa: ARG001
        body = _envelope("CONFIG_INVALID", "validation failed", {"errors": exc.errors()})
        resp = JSONResponse(status_code=422, content=body)
        resp.headers["X-Coffer-Trace"] = get_trace_id()
        return resp

    @app.exception_handler(Exception)
    async def _handle_unknown(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
        body = _envelope("INTERNAL_ERROR", "internal error")
        resp = JSONResponse(status_code=500, content=body)
        resp.headers["X-Coffer-Trace"] = get_trace_id()
        return resp
```

- [x] **Step 4: Run; expect pass.**
- [x] **Step 5: Commit**

```bash
git add backend/coffer/domain/errors.py backend/coffer/surfaces/http/__init__.py backend/coffer/surfaces/http/errors.py backend/tests/unit/domain/test_errors.py
git commit -m "feat(mcp-gateway): error hierarchy + HTTP envelope handler"
```

---

### T007 X-Coffer-Token auth dependency + CORS allowlist (loopback)

**Files:**

- Create: `backend/coffer/surfaces/http/auth.py`
- Create: `backend/coffer/surfaces/http/cors.py`
- Create: `backend/tests/integration/surfaces/http/__init__.py` (empty)
- Create: `backend/tests/integration/surfaces/http/test_auth.py`

- [x] **Step 1: Write failing test**

```python
# backend/tests/integration/surfaces/http/test_auth.py
import pytest
from fastapi import FastAPI, Depends
from httpx import AsyncClient, ASGITransport
from coffer.surfaces.http.auth import require_token, set_active_token

@pytest.mark.asyncio
async def test_missing_token_returns_401():
    app = FastAPI()
    app.dependency_overrides = {}
    set_active_token("secret")

    @app.get("/foo")
    async def foo(_=Depends(require_token)) -> dict[str, str]:
        return {"ok": "yes"}

    async with AsyncClient(transport=ASGITransport(app), base_url="http://t") as c:
        r = await c.get("/foo")
        assert r.status_code == 401

@pytest.mark.asyncio
async def test_correct_token_passes():
    app = FastAPI()
    set_active_token("secret")

    @app.get("/foo")
    async def foo(_=Depends(require_token)) -> dict[str, str]:
        return {"ok": "yes"}

    async with AsyncClient(transport=ASGITransport(app), base_url="http://t") as c:
        r = await c.get("/foo", headers={"X-Coffer-Token": "secret"})
        assert r.status_code == 200
```

- [x] **Step 2: Run; expect fail.**
- [x] **Step 3: Implement**

```python
# backend/coffer/surfaces/http/auth.py
from __future__ import annotations
import hmac
from fastapi import HTTPException, Header, status

_ACTIVE_TOKEN: str | None = None


def set_active_token(token: str | None) -> None:
    global _ACTIVE_TOKEN
    _ACTIVE_TOKEN = token


def require_token(x_coffer_token: str | None = Header(default=None)) -> None:
    if _ACTIVE_TOKEN is None:
        raise HTTPException(status_code=503, detail="daemon not ready")
    if x_coffer_token is None or not hmac.compare_digest(x_coffer_token, _ACTIVE_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad token")
```

```python
# backend/coffer/surfaces/http/cors.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ALLOWED_ORIGINS = (
    "http://localhost",
    "http://127.0.0.1",
)


def install(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["X-Coffer-Token", "Content-Type", "Accept"],
        expose_headers=["X-Coffer-Trace"],
        max_age=600,
    )
```

- [x] **Step 4: Run; expect pass.**
- [x] **Step 5: Commit**

```bash
git add backend/coffer/surfaces/http/auth.py backend/coffer/surfaces/http/cors.py backend/tests/integration/surfaces/http/test_auth.py
git commit -m "feat(mcp-gateway): token + CORS protection on the management API"
```

---

### T008 Daemon discovery (`~/.coffer/daemon.json`) + port allocator

**Files:**

- Create: `backend/coffer/infrastructure/daemon/__init__.py` (empty)
- Create: `backend/coffer/infrastructure/daemon/pid_lock.py`
- Create: `backend/coffer/infrastructure/daemon/port_alloc.py`
- Create: `backend/tests/integration/infrastructure/daemon/__init__.py` (empty)
- Create: `backend/tests/integration/infrastructure/daemon/test_pid_lock.py`
- Create: `backend/tests/integration/infrastructure/daemon/test_port_alloc.py`

- [x] **Step 1: Write failing tests**

```python
# backend/tests/integration/infrastructure/daemon/test_pid_lock.py
from datetime import datetime, timezone
from coffer.infrastructure.daemon.pid_lock import DaemonInfo, write, read

def test_round_trip(tmp_path):
    f = tmp_path / "daemon.json"
    info = DaemonInfo(
        version=1, pid=1234, port=8000,
        token="tok", started_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        binary_path="/usr/local/bin/coffer-daemon",
    )
    write(f, info)
    assert f.stat().st_mode & 0o777 == 0o600
    assert read(f) == info
```

```python
# backend/tests/integration/infrastructure/daemon/test_port_alloc.py
import socket
import pytest
from coffer.infrastructure.daemon.port_alloc import allocate, NoFreePort

def test_picks_default_when_free():
    port = allocate(start=58000, end=58009)
    assert 58000 <= port <= 58009

def test_falls_back_when_default_busy():
    s = socket.socket(); s.bind(("127.0.0.1", 58010)); s.listen()
    try:
        port = allocate(start=58010, end=58019)
        assert 58011 <= port <= 58019
    finally:
        s.close()

def test_raises_when_all_busy():
    sockets = []
    try:
        for p in range(58020, 58025):
            s = socket.socket(); s.bind(("127.0.0.1", p)); s.listen()
            sockets.append(s)
        with pytest.raises(NoFreePort):
            allocate(start=58020, end=58024)
    finally:
        for s in sockets:
            s.close()
```

- [x] **Step 2: Run; expect fail.**
- [x] **Step 3: Implement**

```python
# backend/coffer/infrastructure/daemon/pid_lock.py
from __future__ import annotations
import json
import os
import stat
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class DaemonInfo:
    version: int
    pid: int
    port: int
    token: str
    started_at: datetime
    binary_path: str


def write(path: Path, info: DaemonInfo) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**asdict(info), "started_at": info.started_at.isoformat()}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(path)


def read(path: Path) -> DaemonInfo:
    raw = json.loads(path.read_text())
    return DaemonInfo(
        version=raw["version"],
        pid=raw["pid"],
        port=raw["port"],
        token=raw["token"],
        started_at=datetime.fromisoformat(raw["started_at"]),
        binary_path=raw["binary_path"],
    )
```

```python
# backend/coffer/infrastructure/daemon/port_alloc.py
from __future__ import annotations
import socket


class NoFreePort(Exception):
    pass


def allocate(start: int = 8000, end: int = 8009) -> int:
    for port in range(start, end + 1):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise NoFreePort(f"no free port in {start}-{end}")
```

- [x] **Step 4: Run; expect pass.**
- [x] **Step 5: Commit**

```bash
git add backend/coffer/infrastructure/daemon/ backend/tests/integration/infrastructure/daemon/
git commit -m "feat(mcp-gateway): daemon discovery file + port allocator"
```

---

### T009 FastAPI composition root + `/api/v1/daemon/status`

**Files:**

- Modify: `backend/coffer/main.py`
- Create: `backend/coffer/surfaces/http/app.py`
- Create: `backend/coffer/surfaces/http/daemon_routes.py`
- Create: `backend/coffer/surfaces/http/schemas.py`
- Create: `backend/tests/integration/surfaces/http/test_daemon_status.py`

- [x] **Step 1: Write failing test**

```python
# backend/tests/integration/surfaces/http/test_daemon_status.py
import pytest
from httpx import AsyncClient, ASGITransport
from coffer.surfaces.http.app import create_app

@pytest.mark.asyncio
async def test_status_returns_ready(tmp_path, monkeypatch):
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    app = await create_app()
    async with AsyncClient(transport=ASGITransport(app), base_url="http://t") as c:
        r = await c.get("/api/v1/daemon/status")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
    assert r.json()["version"] == "0.1.0"
```

- [x] **Step 2: Run; expect fail.**
- [x] **Step 3: Implement**

```python
# backend/coffer/surfaces/http/schemas.py
from datetime import datetime
from pydantic import BaseModel


class DaemonStatusOut(BaseModel):
    status: str
    version: str
    started_at: datetime
    port: int
```

```python
# backend/coffer/surfaces/http/daemon_routes.py
from datetime import datetime, timezone
from fastapi import APIRouter
from coffer.surfaces.http.schemas import DaemonStatusOut

router = APIRouter(prefix="/api/v1/daemon", tags=["daemon"])
_STARTED_AT = datetime.now(tz=timezone.utc)
_PORT = 8000  # set by composition root


def set_port(port: int) -> None:
    global _PORT
    _PORT = port


@router.get("/status", response_model=DaemonStatusOut)
async def get_status() -> DaemonStatusOut:
    return DaemonStatusOut(status="ready", version="0.1.0", started_at=_STARTED_AT, port=_PORT)
```

```python
# backend/coffer/surfaces/http/app.py
from __future__ import annotations
from fastapi import FastAPI

from coffer.infrastructure.logging.setup import configure_logging
from coffer.surfaces.http import cors, errors as err_handlers, daemon_routes


async def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Coffer", version="0.1.0", openapi_url="/api/v1/openapi.json")
    cors.install(app)
    err_handlers.register(app)
    app.include_router(daemon_routes.router)
    return app
```

```python
# backend/coffer/main.py  (REPLACE existing 20-line stub)
"""ASGI entry. uvicorn coffer.main:app loads the composition root."""
import asyncio
from coffer.surfaces.http.app import create_app

app = asyncio.run(create_app())
```

- [x] **Step 4: Run; expect pass.**
- [x] **Step 5: Commit**

```bash
git add backend/coffer/main.py backend/coffer/surfaces/http/app.py backend/coffer/surfaces/http/daemon_routes.py backend/coffer/surfaces/http/schemas.py backend/tests/integration/surfaces/http/test_daemon_status.py
git commit -m "feat(mcp-gateway): FastAPI composition root + /api/v1/daemon/status"
```

---

### T010 Typer CLI scaffold + `_client.py`

**Files:**

- Create: `backend/coffer/surfaces/cli/__init__.py` (empty)
- Create: `backend/coffer/surfaces/cli/main.py`
- Create: `backend/coffer/surfaces/cli/_client.py`
- Create: `backend/coffer/surfaces/cli/daemon_cmd.py`
- Modify: `backend/pyproject.toml` → add `[project.scripts]`
- Create: `backend/tests/integration/surfaces/cli/__init__.py` (empty)
- Create: `backend/tests/integration/surfaces/cli/test_daemon_status_cmd.py`

- [x] **Step 1: Write failing test**

```python
# backend/tests/integration/surfaces/cli/test_daemon_status_cmd.py
from typer.testing import CliRunner
from coffer.surfaces.cli.main import app

def test_daemon_status_unreachable_message(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))     # empty home → no daemon.json
    res = CliRunner().invoke(app, ["daemon", "status"])
    assert res.exit_code == 3
    assert "daemon not running" in res.stdout.lower()
```

- [x] **Step 2: Run; expect fail.**
- [x] **Step 3: Implement**

```python
# backend/coffer/surfaces/cli/_client.py
from __future__ import annotations
import os
import sys
from pathlib import Path
import httpx
from coffer.infrastructure.daemon.pid_lock import DaemonInfo, read


def _daemon_json_path() -> Path:
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "daemon.json"


def discover() -> DaemonInfo | None:
    path = _daemon_json_path()
    if not path.exists():
        return None
    try:
        return read(path)
    except (ValueError, KeyError):
        return None


class DaemonNotRunning(SystemExit):
    """Exit-code-3 SystemExit subclass; caught by main.py."""
    code = 3


def client_or_exit() -> tuple[httpx.Client, DaemonInfo]:
    info = discover()
    if info is None:
        print("daemon not running. start it with: coffer daemon start", file=sys.stderr)
        raise DaemonNotRunning()
    base = f"http://127.0.0.1:{info.port}/api/v1"
    return httpx.Client(base_url=base, headers={"X-Coffer-Token": info.token}, timeout=15), info
```

```python
# backend/coffer/surfaces/cli/daemon_cmd.py
from __future__ import annotations
import typer
from coffer.surfaces.cli._client import client_or_exit

app = typer.Typer(help="Daemon lifecycle")


@app.command("status")
def status() -> None:
    """Show daemon status."""
    c, info = client_or_exit()
    with c:
        r = c.get("/daemon/status")
        r.raise_for_status()
        data = r.json()
    typer.echo(f"status:  {data['status']}")
    typer.echo(f"version: {data['version']}")
    typer.echo(f"port:    {info.port}")
    typer.echo(f"pid:     {info.pid}")
```

```python
# backend/coffer/surfaces/cli/main.py
from __future__ import annotations
import typer
from coffer.surfaces.cli import daemon_cmd

app = typer.Typer(help="Coffer CLI", no_args_is_help=True)
app.add_typer(daemon_cmd.app, name="daemon")


def run() -> None:
    app()


if __name__ == "__main__":
    run()
```

- [x] **Step 4: Add scripts to pyproject**

```toml
[project.scripts]
coffer = "coffer.surfaces.cli.main:run"
coffer-mcp-shim = "coffer.surfaces.shim.main:run"   # filled in Phase 3
```

- [x] **Step 5: Run; expect pass; commit**

```bash
.venv/bin/pip install -e ./backend
.venv/bin/pytest backend/tests/integration/surfaces/cli/test_daemon_status_cmd.py -v
git add backend/coffer/surfaces/cli/ backend/pyproject.toml backend/tests/integration/surfaces/cli/
git commit -m "feat(mcp-gateway): Typer CLI scaffold with daemon status"
```

---

### T011 [P] `coffer daemon start/stop` (background daemon process)

**Files:**

- Modify: `backend/coffer/surfaces/cli/daemon_cmd.py`
- Modify: `backend/coffer/surfaces/http/app.py` (add startup hook writing daemon.json)
- Modify: `backend/tests/integration/surfaces/cli/test_daemon_status_cmd.py` (extend)

- [x] **Step 1: Write failing integration test**

```python
# backend/tests/integration/surfaces/cli/test_daemon_lifecycle.py
import time
import subprocess
import pytest

@pytest.mark.timeout(30)
def test_start_then_status_then_stop(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    subprocess.run(["coffer", "daemon", "start"], check=True, timeout=15)
    time.sleep(0.5)
    status = subprocess.run(["coffer", "daemon", "status"], check=True, capture_output=True, text=True)
    assert "ready" in status.stdout
    subprocess.run(["coffer", "daemon", "stop"], check=True, timeout=5)
```

- [x] **Step 2: Run; expect fail.**
- [x] **Step 3: Implement** — extend `daemon_cmd.py` with `start`, `stop`, and a background subprocess spawn helper. Update FastAPI lifespan to write `~/.coffer/daemon.json` with port + token + pid + started_at, and a shutdown handler to remove it. (Detailed code: lifespan + `os.setsid` POSIX / `CREATE_NO_WINDOW` Windows fork; ~120 lines total — split into `daemon_cmd.py` and a new `infrastructure/daemon/bootstrap.py`.)

- [x] **Step 4: Run; expect pass.**
- [x] **Step 5: Commit**

```bash
git commit -am "feat(mcp-gateway): coffer daemon start/stop with detached spawn"
```

---

### T012 [P] Acceptance audit script kept passing through Phase 1

**Files:**

- (No code change.) This is a verification step: every commit in Phase 1 must keep `make verify-acceptance` clean (zero scenarios listed in `spec.md` should be referenced by tests yet, but the audit must not be silently broken).

- [x] **Step 1: Run audit**

```bash
make verify-acceptance
```

Expected: clean (no scenarios covered yet; audit reports zero orphans).

- [x] **Step 2: Verify spec scenarios still parsable**

```bash
.venv/bin/python scripts/audit_acceptance.py
```

- [x] **Step 3: Commit** (no diff; tag a sanity checkpoint in PR description instead).

---

### T013 Phase 1 checkpoint commit

- [x] **Step 1: Run full verify**

```bash
make verify
```

- [x] **Step 2: If green, tag in PR description** (don't create a git tag; mark Phase 1 done in the PR body).

---

## Phase 2 — Foundational (kind-agnostic Resource framework)

Goal: domain entities, repositories, services for Resource + Audit + Retention.
Routes, CLI subcommands, and Pydantic API schemas for the kind-agnostic
surfaces. Composition root accepts a kind dict but registers none yet — tests
register a `fake_kind` to exercise the kind-agnostic plumbing.

**Checkpoint**: CRUD a Resource of `fake_kind` through every surface (HTTP, CLI),
audit shows changes, retention worker prunes test-inserted old rows.

---

### T014 [TDD] `ResourceRef` value object

**Files:**

- Create: `backend/coffer/domain/resource.py`
- Create: `backend/tests/unit/domain/__init__.py` (empty if not present)
- Create: `backend/tests/unit/domain/test_resource_ref.py`

- [x] **Step 1: Failing test**

```python
# backend/tests/unit/domain/test_resource_ref.py
import pytest
from coffer.domain.resource import ResourceRef

def test_parse_round_trip():
    ref = ResourceRef.parse("mcp_server:filesystem")
    assert ref == ResourceRef("mcp_server", "filesystem")
    assert str(ref) == "mcp_server:filesystem"

@pytest.mark.parametrize("bad", ["", "no_colon", ":missing_kind", "kind:", "a:b:c"])
def test_invalid_strings_rejected(bad):
    with pytest.raises(ValueError):
        ResourceRef.parse(bad)

def test_frozen_and_hashable():
    a = ResourceRef("k", "n")
    {a}                       # hashable
    with pytest.raises((AttributeError, TypeError)):
        a.kind = "x"           # frozen
```

- [x] **Step 2: Run; expect fail.**
- [x] **Step 3: Implement**

```python
# backend/coffer/domain/resource.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceRef:
    """External identifier for any Resource: `<kind>:<name>`."""
    kind: str
    name: str

    def __post_init__(self) -> None:
        if not self.kind or ":" in self.kind:
            raise ValueError(f"invalid kind: {self.kind!r}")
        if not self.name or ":" in self.name:
            raise ValueError(f"invalid name: {self.name!r}")

    def __str__(self) -> str:
        return f"{self.kind}:{self.name}"

    @classmethod
    def parse(cls, s: str) -> "ResourceRef":
        parts = s.split(":")
        if len(parts) != 2:
            raise ValueError(f"expected '<kind>:<name>', got {s!r}")
        kind, name = parts
        if not kind or not name:
            raise ValueError(f"empty kind or name in {s!r}")
        return cls(kind=kind, name=name)
```

- [x] **Step 4: Run; expect pass.**
- [x] **Step 5: Commit**

```bash
git add backend/coffer/domain/resource.py backend/tests/unit/domain/test_resource_ref.py
git commit -m "feat(mcp-gateway): ResourceRef value object"
```

---

### T015 [TDD] `Resource` entity + `Kind` descriptor + `KindModule`

**Files:**

- Modify: `backend/coffer/domain/resource.py`
- Create: `backend/coffer/domain/kind_module.py`
- Create: `backend/tests/unit/domain/test_resource.py`
- Create: `backend/tests/unit/domain/test_kind.py`

- [x] **Step 1: Failing tests**

```python
# backend/tests/unit/domain/test_resource.py
from datetime import datetime, timezone
from coffer.domain.resource import Resource, ResourceRef

def test_resource_ref_property():
    r = Resource(id=1, kind="mcp_server", name="filesystem", description=None,
                 config={}, enabled=True, created_at=datetime.now(timezone.utc),
                 updated_at=datetime.now(timezone.utc))
    assert r.ref == ResourceRef("mcp_server", "filesystem")
```

```python
# backend/tests/unit/domain/test_kind.py
from pydantic import BaseModel
from coffer.domain.resource import Kind, ResourceRef

class _FooConfig(BaseModel):
    x: int

def test_kind_basic():
    k = Kind(name="foo", display_name="Foo", config_schema=_FooConfig)
    assert k.name == "foo"
    assert k.config_schema is _FooConfig
    assert k.on_delete is None

def test_kind_on_delete_hook():
    calls: list[ResourceRef] = []
    k = Kind(name="foo", display_name="Foo", config_schema=_FooConfig,
             on_delete=lambda ref: calls.append(ref))
    assert k.on_delete is not None
    k.on_delete(ResourceRef("foo", "bar"))
    assert calls == [ResourceRef("foo", "bar")]
```

- [x] **Step 2: Run; expect fail.**
- [x] **Step 3: Append to `domain/resource.py`**

```python
# Append at the bottom of backend/coffer/domain/resource.py
from datetime import datetime
from typing import Any, Callable
from pydantic import BaseModel


@dataclass
class Resource:
    id: int
    kind: str
    name: str
    description: str | None
    config: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime

    @property
    def ref(self) -> ResourceRef:
        return ResourceRef(self.kind, self.name)


@dataclass(frozen=True)
class Kind:
    name: str
    display_name: str
    config_schema: type[BaseModel]
    on_delete: Callable[[ResourceRef], None] | None = None
```

```python
# backend/coffer/domain/kind_module.py
"""Composition-root data carrier — held outside domain on purpose because it
references surface-layer routers."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Sequence


@dataclass(frozen=True)
class KindModule:
    name: str
    display_name: str
    config_schema: type           # Pydantic model type
    on_delete: Callable[..., None] | None = None
    http_routers: Sequence[Any] = ()      # APIRouter instances
    cli_groups: Sequence[Any] = ()        # Typer instances
```

- [x] **Step 4: Run; expect pass.**
- [x] **Step 5: Commit**

```bash
git add backend/coffer/domain/resource.py backend/coffer/domain/kind_module.py backend/tests/unit/domain/test_resource.py backend/tests/unit/domain/test_kind.py
git commit -m "feat(mcp-gateway): Resource entity + Kind + KindModule"
```

---

### T016 [TDD] `AuditEntry` + `AuditEventType`

**Files:**

- Create: `backend/coffer/domain/audit.py`
- Create: `backend/tests/unit/domain/test_audit.py`

- [x] **Step 1: Failing test**

```python
# backend/tests/unit/domain/test_audit.py
from datetime import datetime, timezone
from coffer.domain.audit import AuditEntry, AuditEventType

def test_audit_event_type_enum():
    assert AuditEventType.RESOURCE_CREATED.value == "resource_created"
    assert AuditEventType.CAPABILITY_DISABLED.value == "capability_disabled"

def test_audit_entry_minimal():
    e = AuditEntry(
        id=None,
        timestamp=datetime(2026, 5, 20, tzinfo=timezone.utc),
        event_type=AuditEventType.RESOURCE_CREATED.value,
        resource_kind="mcp_server",
        resource_name="filesystem",
        actor="cli",
        details={"config": {}},
    )
    assert e.event_type == "resource_created"
```

- [x] **Step 2: Run; fail.**
- [x] **Step 3: Implement**

```python
# backend/coffer/domain/audit.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class AuditEventType(StrEnum):
    RESOURCE_CREATED       = "resource_created"
    RESOURCE_UPDATED       = "resource_updated"
    RESOURCE_ENABLED       = "resource_enabled"
    RESOURCE_DISABLED      = "resource_disabled"
    RESOURCE_DELETED       = "resource_deleted"
    CAPABILITY_FIRST_SEEN  = "capability_first_seen"
    CAPABILITY_ENABLED     = "capability_enabled"
    CAPABILITY_DISABLED    = "capability_disabled"
    DAEMON_STARTED         = "daemon_started"
    DAEMON_STOPPED         = "daemon_stopped"
    TOKEN_ROTATED          = "token_rotated"
    RETENTION_UPDATED      = "retention_updated"
    BACKUP_CREATED         = "backup_created"


@dataclass
class AuditEntry:
    id: int | None
    timestamp: datetime
    event_type: str
    resource_kind: str | None
    resource_name: str | None
    actor: str
    details: dict[str, Any] = field(default_factory=dict)
```

- [x] **Step 4: Pass.**
- [x] **Step 5: Commit.**

---

### T017 [TDD] `RetentionPolicy` entity

**Files:**

- Create: `backend/coffer/domain/retention.py`
- Create: `backend/tests/unit/domain/test_retention.py`

- [x] **Step 1: Failing test**

```python
# backend/tests/unit/domain/test_retention.py
from datetime import datetime, timezone
from coffer.domain.retention import RetentionPolicy

def test_retention_policy_minimal():
    p = RetentionPolicy(
        table_name="audit_log", retention_days=365,
        last_pruned_at=None, last_pruned_rows=0,
        updated_at=datetime.now(timezone.utc),
    )
    assert p.retention_days == 365
```

- [x] **Step 2: Run; fail.**
- [x] **Step 3: Implement**

```python
# backend/coffer/domain/retention.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RetentionPolicy:
    table_name: str
    retention_days: int | None       # None = keep forever; >0 = days
    last_pruned_at: datetime | None
    last_pruned_rows: int
    updated_at: datetime
```

- [x] **Step 4: Pass.**
- [x] **Step 5: Commit.**

---

### T018 [TDD] Repository protocols (kind-agnostic)

**Files:**

- Create: `backend/coffer/application/__init__.py` (empty if missing)
- Create: `backend/coffer/application/repos.py`
- (Domain stays pure; protocols live in application.)

- [x] **Step 1: Author the file (no test — pure protocol definitions; types validated by mypy)**

```python
# backend/coffer/application/repos.py
from __future__ import annotations
from datetime import datetime
from typing import Protocol

from coffer.domain.audit import AuditEntry
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.retention import RetentionPolicy


class ResourceRepo(Protocol):
    async def find(self, ref: ResourceRef) -> Resource | None: ...
    async def list(self, kind: str | None = None) -> list[Resource]: ...
    async def create(self, resource: Resource) -> Resource: ...
    async def update_config(self, ref: ResourceRef, config: dict, description: str | None) -> Resource: ...
    async def set_enabled(self, ref: ResourceRef, enabled: bool) -> Resource: ...
    async def delete(self, ref: ResourceRef) -> None: ...


class AuditRepo(Protocol):
    async def insert(self, entry: AuditEntry) -> None: ...
    async def query(
        self, *, kind: str | None = None, name: str | None = None,
        event_type: str | None = None, since: datetime | None = None, limit: int = 50,
    ) -> list[AuditEntry]: ...


class RetentionRepo(Protocol):
    async def get(self, table_name: str) -> RetentionPolicy: ...
    async def list(self) -> list[RetentionPolicy]: ...
    async def upsert(self, table_name: str, retention_days: int | None) -> None: ...
    async def update_retention(self, table_name: str, retention_days: int | None) -> None: ...
    async def touch_pruned(self, table_name: str, rows: int) -> None: ...
    async def delete_older_than(self, table: str, timestamp_column: str, cutoff: datetime) -> int: ...
    async def exists(self, table_name: str) -> bool: ...
```

- [x] **Step 2: Run mypy**

```bash
.venv/bin/mypy backend/coffer/application/repos.py
```

- [x] **Step 3: Commit**

```bash
git add backend/coffer/application/__init__.py backend/coffer/application/repos.py
git commit -m "feat(mcp-gateway): repository protocols for Resource/Audit/Retention"
```

---

### T019 [TDD] SQLAlchemy ORM models (kind-agnostic core tables)

**Files:**

- Create: `backend/coffer/infrastructure/persistence/models.py`
- Create: `backend/tests/integration/infrastructure/persistence/test_models.py`

- [x] **Step 1: Failing integration test (model loads + round-trips to a temp DB)**

```python
# backend/tests/integration/infrastructure/persistence/test_models.py
import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import create_async_engine_with_pragmas, session_maker
from coffer.infrastructure.persistence.models import ResourceModel

@pytest.mark.asyncio
async def test_resource_model_round_trip(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path/'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    async with sm() as s:
        s.add(ResourceModel(kind="fake_kind", name="t", description=None,
                             config_json="{}", enabled=True,
                             created_at=datetime.now(timezone.utc),
                             updated_at=datetime.now(timezone.utc)))
        await s.commit()
    async with sm() as s:
        row = (await s.execute(select(ResourceModel))).scalar_one()
    assert row.kind == "fake_kind"
    await engine.dispose()
```

- [x] **Step 2: Run; fail.**
- [x] **Step 3: Implement**

```python
# backend/coffer/infrastructure/persistence/models.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, TIMESTAMP, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from coffer.infrastructure.persistence.base import Base


class ResourceModel(Base):
    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("kind", "name", name="uq_resources_kind_name"),
        Index("idx_resources_kind_enabled", "kind", "enabled"),
    )


class AuditLogModel(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    resource_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    resource_name: Mapped[str | None] = mapped_column(String, nullable=True)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        Index("idx_audit_resource", "resource_kind", "resource_name", "timestamp"),
        Index("idx_audit_time", "timestamp"),
        Index("idx_audit_eventtype", "event_type", "timestamp"),
    )


class RetentionPolicyModel(Base):
    __tablename__ = "retention_policies"
    table_name: Mapped[str] = mapped_column(String, primary_key=True)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_pruned_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_pruned_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
```

- [x] **Step 4: Pass.**
- [x] **Step 5: Commit.**

---

### T020 Alembic migration `0001_initial`

**Files:**

- Create: `backend/coffer/infrastructure/persistence/migrations/versions/20260520_0001_initial.py`

- [x] **Step 1: Author migration (autogenerate, then hand-trim)**

```bash
.venv/bin/alembic -c backend/coffer/infrastructure/persistence/migrations/alembic.ini revision -m "initial schema"
```

Edit the produced file so `upgrade()` creates `resources`, `audit_log`, `retention_policies` with the exact DDL from [data-model.md](./data-model.md) including all indices and the `CHECK` constraint on `retention_policies.retention_days`.

- [x] **Step 2: Apply forward + backward**

```bash
.venv/bin/alembic -c backend/coffer/infrastructure/persistence/migrations/alembic.ini upgrade head
.venv/bin/alembic -c backend/coffer/infrastructure/persistence/migrations/alembic.ini downgrade base
```

- [x] **Step 3: Commit**

```bash
git add backend/coffer/infrastructure/persistence/migrations/versions/
git commit -m "feat(mcp-gateway): Alembic 0001_initial — resources, audit_log, retention_policies"
```

---

### T021 [TDD] `SqlAlchemyResourceRepo`

**Files:**

- Create: `backend/coffer/infrastructure/persistence/repos.py`
- Create: `backend/tests/integration/infrastructure/persistence/test_resource_repo.py`

- [x] **Step 1: Failing test** — exercise `create / find / list / update_config / set_enabled / delete`, including the `UNIQUE(kind, name)` constraint surfacing as `ResourceAlreadyExists`.
- [x] **Step 2: Run; fail.**
- [x] **Step 3: Implement** `SqlAlchemyResourceRepo` (constructor takes `session_maker`; each method opens a short async session, executes, commits). Convert between ORM and domain via `_to_domain` / `_from_domain` helpers. Catch `IntegrityError` and raise `ResourceAlreadyExists`.
- [x] **Step 4: Pass.**
- [x] **Step 5: Commit.**

(Code structure mirrors test cases; ≤ 250 LOC. Full listing kept verbose in this plan would dwarf surrounding tasks — implementer follows the Protocol shape from T018 and the ORM from T019.)

---

### T022 [TDD] `SqlAlchemyAuditRepo`

Same shape as T021 against `AuditLogModel`. Tests: insert + query by kind / name / event_type / since / limit.

---

### T023 [TDD] `SqlAlchemyRetentionRepo`

Same shape as T021 against `RetentionPolicyModel`. Tests: `upsert`, `update_retention` (None and positive int), `touch_pruned`, `delete_older_than` (SQL injection guard: table name not in `_ALLOWED_TABLES` raises `SecurityError`).

The `delete_older_than` implementation must use **only** allow-listed table and column names — never user-supplied values; this is the SQL-injection guard from [data-model.md](./data-model.md) § "Invariants".

---

### T024 [TDD] `AuditService`

**Files:**

- Create: `backend/coffer/application/audit_service.py`
- Create: `backend/tests/integration/application/__init__.py` (empty)
- Create: `backend/tests/integration/application/test_audit_service.py`

- [x] **Step 1: Test record + query.**
- [x] **Step 2: Run; fail.**
- [x] **Step 3: Implement**

```python
# backend/coffer/application/audit_service.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

from coffer.application.repos import AuditRepo
from coffer.domain.audit import AuditEntry
from coffer.domain.resource import ResourceRef


class AuditService:
    def __init__(self, repo: AuditRepo) -> None:
        self._repo = repo

    async def record(
        self, event_type: str, *,
        ref: ResourceRef | None = None,
        actor: str = "system",
        details: dict[str, Any] | None = None,
    ) -> None:
        await self._repo.insert(AuditEntry(
            id=None,
            timestamp=datetime.now(tz=timezone.utc),
            event_type=event_type,
            resource_kind=ref.kind if ref else None,
            resource_name=ref.name if ref else None,
            actor=actor,
            details=details or {},
        ))

    async def query(self, **filters: Any) -> list[AuditEntry]:
        return await self._repo.query(**filters)
```

- [x] **Step 4: Pass.**
- [x] **Step 5: Commit.**

---

### T025 [TDD] `ResourceService.register` + audit integration

**Files:**

- Create: `backend/coffer/application/resource_service.py`
- Create: `backend/tests/integration/application/test_resource_service.py`

- [x] **Step 1: Failing test (registers a fake_kind resource, verifies persistence + audit row)**
- [x] **Step 2: Run; fail.**
- [x] **Step 3: Implement** `ResourceService.__init__(kinds, repo, audit)` plus `register()` (validates config against `kind.config_schema`, persists, audits `RESOURCE_CREATED`). Raises `UnknownKind` when kind missing; raises `ConfigValidationError` (wrapping Pydantic `ValidationError`) on schema failure.
- [x] **Step 4: Pass.**
- [x] **Step 5: Commit.**

---

### T026 [TDD] `ResourceService.list/get/update_config/set_enabled/delete`

Build out the remaining methods, each with its own integration test asserting persistence + audit behaviour. `delete` invokes `Kind.on_delete` if present (test the hook raising aborts the delete; test no-hook path).

---

### T027 [TDD] `PrunableTable` + `PrunableRegistry`

**Files:**

- Create: `backend/coffer/infrastructure/persistence/retention.py`
- Create: `backend/tests/unit/infrastructure/persistence/test_retention_registry.py`

- [x] **Step 1: Failing test** (register, duplicate rejected, get unknown raises, all() lists everything).
- [x] **Step 2: Run; fail.**
- [x] **Step 3: Implement** per [data-model.md](./data-model.md) §`PrunableTable` definition.
- [x] **Step 4: Pass.**
- [x] **Step 5: Commit.**

---

### T028 [TDD] `RetentionService` (initialize_defaults, list, set, prune)

Same TDD shape. `prune` test must include the SQL-injection guard case from T023 ("table name not in allowlist raises").

---

### T029 [TDD] `RetentionWorker` background task

Test using `asyncio` `freezegun` substitute: advance clock, assert prune called, assert worker survives a failing prune (logs but doesn't propagate).

---

### T030 [TDD] Pydantic API schemas matching `contracts/api.openapi.yaml`

**Files:**

- Modify: `backend/coffer/surfaces/http/schemas.py`

Add all kind-agnostic schemas from the contract: `ResourceOut`, `ResourceCreate`, `ResourceUpdate`, `ResourceListOut`, `ErrorResponse`, `AuditEntryOut`, `AuditListOut`, `RetentionPolicyOut`, `RetentionPolicyListOut`, `RetentionPolicyUpdate`, `PruneResultOut`, `DaemonStatusOut`, `BackupResultOut`, `TokenRotationOut`.

- [x] **Step 1: Contract test** asserts each Pydantic model's `model_json_schema()` is a subset of the corresponding `components.schemas.*` in `contracts/api.openapi.yaml` (use `scripts/check_response_models.py` as the oracle).
- [x] **Step 2: Run; fail (some schemas missing).**
- [x] **Step 3: Add schemas; rerun.**
- [x] **Step 4: Pass.**
- [x] **Step 5: Commit.**

---

### T031 [TDD] `/api/v1/resources/*` routes — kind-agnostic CRUD

**Files:**

- Create: `backend/coffer/surfaces/http/resource_routes.py`
- Create: `backend/tests/integration/surfaces/http/test_resource_routes.py`

Per the contract: `GET /resources`, `POST /resources`, `GET/PATCH/DELETE /resources/{kind}/{name}`, `POST .../enable`, `POST .../disable`.

Tests register a `fake_kind` (Pydantic `class FakeConfig(BaseModel): foo: int`) into a freshly-built FastAPI app, then exercise the full lifecycle through HTTP.

- [x] **Steps 1–5** TDD red-green per endpoint group; commit after each endpoint group works.

---

### T032 [TDD] `/api/v1/audit` route

Same shape; query parameters: `kind`, `name`, `event_type`, `since`, `limit`. Test pagination by `since` parameter.

---

### T033 [TDD] `/api/v1/retention/*` routes

`GET /policies`, `PATCH /policies/{table_name}`, `POST /prune`. Test rejecting unknown table_name with 404. Test SQL-injection attempts (e.g., `; DROP TABLE`) return 404 from the registry check.

---

### T034 [TDD] `/api/v1/vault/backup` and `/api/v1/daemon/*` routes — backup / rotate-token / shutdown

`POST /vault/backup` produces a full vault `.tar.gz` snapshot (db + `knowledge/`/`memory/`/`skills/` trees, master key excluded by default) under `~/.coffer/backups/` and returns `{ "path": "...", "size_bytes": ... }`. `POST /daemon/rotate-token` generates a new token, writes daemon.json atomically, returns the new value (the only response that contains the secret). `POST /daemon/shutdown` schedules a graceful shutdown then returns 204.

---

### T035 [TDD] CLI subcommand groups (kind-agnostic)

- `coffer resource list/show/enable/disable/delete`
- `coffer audit list [--kind --name --event-type --since --limit] [--json]`
- `coffer retention list/set/prune-now`
- `coffer daemon start/stop/status/backup/rotate-token`

One commit per subcommand group. Tests use `typer.testing.CliRunner` against a daemon spawned in-process by a pytest fixture.

---

### T036 Composition root: register `fake_kind` in test mode, real kinds in prod

**Files:**

- Modify: `backend/coffer/surfaces/http/app.py`

Update `create_app` to accept a `kinds: list[KindModule]` argument. Production entry (`coffer.main:app`) still calls `create_app()` (later phases pass in `MCP_KIND`); tests pass `[FAKE_KIND]` for kind-agnostic coverage.

---

### T037 Phase 2 checkpoint

Run full `make verify` + an acceptance audit; tag in PR description.

---

## Phase 3 — User Story 1 + 2 (P1 MVP): MCP gateway core + CLI + shim

Goal: deliver the MCP gateway end-to-end via the CLI surface. After this phase
the feature is shippable to early adopters via `pip install -e .`.

**Checkpoint**: User Story 1 + User Story 2 acceptance scenarios pass in `e2e/mcp/`.

---

### T038 [TDD] [US1] `fake_mcp_server.py` fixture

**Files:**

- Create: `backend/tests/fixtures/__init__.py` (empty)
- Create: `backend/tests/fixtures/fake_mcp_server.py`

Real MCP server using the official `mcp` Python SDK, parameterised by CLI flags
per [research.md](./research.md) § Test fixtures. Verify by hand:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{...}}' | \
  python -m coffer.tests.fixtures.fake_mcp_server --scenario basic
```

Commit when handshake produces a valid JSON-RPC response.

---

### T039 [TDD] [US1] MCP `Namespace` functions (pure)

**Files:**

- Create: `backend/coffer/domain/mcp/__init__.py` (empty)
- Create: `backend/coffer/domain/mcp/namespace.py`
- Create: `backend/tests/unit/domain/mcp/__init__.py` (empty)
- Create: `backend/tests/unit/domain/mcp/test_namespace.py`

- [x] **Step 1: Failing tests** covering `prefix_tool`, `parse_prefixed_tool`, `prefix_resource_uri`, `parse_prefixed_uri`, `prefix_prompt`, round-trip property tests, invalid-input rejection.
- [x] **Step 3: Implement**

```python
# backend/coffer/domain/mcp/namespace.py
from __future__ import annotations
from coffer.domain.errors import InvalidPrefix


def prefix_tool(server: str, tool: str) -> str:
    return f"{server}__{tool}"


def parse_prefixed_tool(prefixed: str) -> tuple[str, str]:
    server, sep, tool = prefixed.partition("__")
    if not sep or not server or not tool:
        raise InvalidPrefix(f"not a coffer-prefixed tool name: {prefixed!r}")
    return server, tool


def prefix_resource_uri(server: str, uri: str) -> str:
    return f"coffer://{server}/{uri}"


def parse_prefixed_uri(prefixed: str) -> tuple[str, str]:
    if not prefixed.startswith("coffer://"):
        raise InvalidPrefix(f"not a coffer-prefixed uri: {prefixed!r}")
    rest = prefixed.removeprefix("coffer://")
    server, sep, original = rest.partition("/")
    if not sep or not server or not original:
        raise InvalidPrefix(f"malformed prefixed uri: {prefixed!r}")
    return server, original


def prefix_prompt(server: str, prompt: str) -> str:
    return f"{server}__{prompt}"


def parse_prefixed_prompt(prefixed: str) -> tuple[str, str]:
    return parse_prefixed_tool(prefixed)
```

- [x] **Step 4: Pass; Step 5: Commit.**

---

### T040 [TDD] [US1] `MCPServerConfig` (Pydantic discriminated union)

**Files:**

- Create: `backend/coffer/domain/mcp/server_config.py`
- Create: `backend/tests/unit/domain/mcp/test_server_config.py`

- [x] **Tests**: valid stdio + valid http + invalid (missing `type`); secret-in-env regex check rejects values matching `^(Bearer|ghp_|sk_|gho_)` patterns; range checks on timeouts.
- [x] **Implementation**: per [data-model.md](./data-model.md) § MCP value objects. Strict Pydantic with `Field(discriminator="type")`.
- [x] **Commit**.

---

### T041 [TDD] [US1] `MCPTool` / `MCPResource` / `MCPPrompt` value objects

`backend/coffer/domain/mcp/capability.py` per data-model.md. Lightweight Pydantic models — they correspond to MCP SDK shapes; no DB.

Also add `MCPCapabilityPreference` and `MCPInvocation` dataclasses in the same file (they are domain entities; their ORM counterparts come later).

---

### T042 SQLAlchemy ORM models for the MCP kind tables

**Files:**

- Create: `backend/coffer/infrastructure/mcp/__init__.py` (empty)
- Create: `backend/coffer/infrastructure/mcp/persistence.py`

`MCPCapabilityPreferenceModel` + `MCPInvocationModel`, both registered against the shared `Base.metadata`.

---

### T043 Alembic migration `0002_mcp_tables`

`alembic revision -m "mcp tables"`; edit to add `mcp_capability_preferences` + `mcp_invocations` with indices and FK CASCADE per [data-model.md](./data-model.md).

Also update `migrations/env.py` to import `coffer.infrastructure.mcp.persistence`.

---

### T044 [TDD] [US1] `MCPCapabilityPreferenceRepo` + `MCPInvocationRepo`

Pattern follows T021–T023.

---

### T045 [TDD] [US1] `CredentialResolver` (keychain → env / header overlay)

**Files:**

- Create: `backend/coffer/application/mcp/__init__.py` (empty)
- Create: `backend/coffer/application/mcp/credential_resolver.py`
- Create: `backend/coffer/infrastructure/credentials/__init__.py` (empty)
- Create: `backend/coffer/infrastructure/credentials/keyring_adapter.py`

The keyring adapter is the **only** file in the codebase allowed to import `keyring`. It exposes `get(key) -> str | None` and `set(key, value)`. `CredentialResolver.materialize(refs: dict[str, str]) -> dict[str, str]` raises `CredentialMissing` per [spec.md](./spec.md) FR-011.

Integration test uses `keyring.backends.fail.Keyring` or the `keyring.testing.backend.SimpleKeyring` test backend per [`agents/testing.md`](../../agents/testing.md).

---

### T046 [TDD] [US1] `StdioUpstreamConnection` (spawn + initialize)

**Files:**

- Create: `backend/coffer/infrastructure/mcp/subprocess.py`

Async wrapper around `asyncio.subprocess.create_subprocess_exec` that:

1. Spawns the upstream with materialised env.
2. Writes the MCP `initialize` request to stdin.
3. Reads framed JSON-RPC from stdout.
4. Returns the upstream's declared capabilities or raises `UpstreamTimeout`.

Tests use `fake_mcp_server.py` fixture with various scenarios (`basic`, `slow` for timeout, `crash` for spawn-then-crash). Each scenario is one task — split into T046-a, T046-b if needed to stay 2-5 min apiece.

---

### T047 [TDD] [US1] `StdioUpstreamConnection.request / on_notification / close`

Build out request/response correlation by JSON-RPC id, notification fan-out via callback, graceful close (SIGTERM → wait 5s → SIGKILL).

---

### T048 [TDD] [US1] `HttpUpstreamConnection`

`backend/coffer/infrastructure/mcp/http_client.py`. Uses `httpx.AsyncClient` for request/response and a background SSE reader task for server-initiated notifications. Tests use a FastAPI in-process app pretending to be an MCP HTTP server.

---

### T049 [TDD] [US1] `SubprocessSupervisor` (lazy spawn + health state machine)

`backend/coffer/application/mcp/supervisor.py`. Owns the `(session, server_name) → UpstreamConnection` dict; lazy on first request; respawn-with-backoff on crash (3 attempts: 1s / 5s / 30s). Health states `healthy / starting / unhealthy / cooldown`.

Test scenarios from [spec.md](./spec.md) Edge Cases: upstream crash mid-call → next call respawns; spawn timeout → unhealthy + cooldown.

---

### T050 [TDD] [US1] Orphan PID file tracking

`backend/coffer/infrastructure/daemon/orphan_sweep.py`:

- spawn-time hook writes `~/.coffer/upstream-pids/<server>-<pid>.json` with `{server, pid, command, spawned_at}`
- close-time hook deletes it
- daemon-startup sweep walks the directory, verifies each PID via `psutil`, kills lingering ones whose command line still matches.

---

### T051 [TDD] [US1] `CapabilityDiscovery.list_tools` (live + cache + preferences reconciliation)

`backend/coffer/application/mcp/discovery.py`. Live query upstream, 60 s in-memory cache per session, reconciliation with `MCPCapabilityPreferenceRepo` on each refresh (insert new caps with `enabled` per server policy; bump `last_seen_at`; do not delete missing caps).

---

### T052 [TDD] [US1] `CapabilityDiscovery.list_resources` + `list_prompts`

Same pattern — split for granular review.

---

### T053 [TDD] [US1] `MCPGatewaySession.initialize` (negotiate downstream + upstream capabilities)

`backend/coffer/application/mcp/gateway.py`. Records downstream client's declared capabilities. Builds coffer's server-capabilities response. Stores per-session state.

Use the `mcp` SDK's helper types so we don't hand-roll protocol JSON shapes.

---

### T054 [TDD] [US1] `MCPGatewaySession.handle_request`: dispatch `tools/list`, `resources/list`, `prompts/list`

Routes to `CapabilityDiscovery` for each capability kind, applies namespace prefix, returns to client. Test with two `fake_mcp_server` instances — assert aggregated, prefixed list.

---

### T055 [TDD] [US1] `MCPGatewaySession.handle_request`: dispatch `tools/call`

Parse prefixed tool name → upstream → original tool name → upstream.request → result returned unchanged. Write `MCPInvocation` row (status `ok` or `error` / `timeout`); never log args or result.

---

### T056 [TDD] [US1] `MCPGatewaySession.handle_request`: dispatch `resources/read` + `prompts/get`

URI / name parsing per `Namespace.parse_prefixed_uri` and `parse_prefixed_prompt`. Returns upstream payload unchanged.

---

### T057 [TDD] [US1] Capability disabled rejection

When the preferences row says `enabled=false` for a target capability, the gateway raises `ToolDisabled` (mapped to JSON-RPC error `-32000`). Invocation log row status `denied`.

---

### T058 [TDD] [US1] Upstream → downstream notification forwarding

Implements `notifications/tools/list_changed`, `resources/list_changed`, `prompts/list_changed`, `resources/updated` (URI rewritten via `prefix_resource_uri`). Cache invalidated on the corresponding session.

---

### T059 [TDD] [US1] `progressToken` passthrough + idle timer reset

Per [research.md](./research.md) § "Streaming progress decision": preserve `_meta.progressToken` in `tools/call`; when upstream emits `notifications/progress` for the matching token, reset the per-request idle timer (not the wall-clock deadline). Do **not** forward the progress notification downstream.

---

### T060 [TDD] [US1] `sampling/createMessage` pass-through with capability negotiation

If downstream declared `sampling`, route upstream→downstream and back. Otherwise return JSON-RPC `method-not-found` to the upstream when it asks. Test both paths.

---

### T061 [TDD] [US1] `roots/list` pass-through

Always relay (no capability negotiation in current MCP spec). Test the round trip.

---

### T062 [TDD] [US1] `MCPGatewaySession.dispose`

Kill all owned subprocesses (SIGTERM → 5s → SIGKILL), close http clients, drop preferences cache. Test no orphans left behind via `~/.coffer/upstream-pids/` after dispose.

---

### T063 [TDD] [US1] `MCP_KIND` composition wire-up

> **Ordering**: this task depends on T064–T070 (the router and CLI files it
> imports). Execute it **after** those tasks land. Listed here in topological
> position for the data flow even though chronological order shifts it later.

**Files:**

- Create: `backend/coffer/application/mcp/kind.py`

```python
# backend/coffer/application/mcp/kind.py
from coffer.domain.kind_module import KindModule
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.surfaces.http.mcp.server_routes import router as mcp_server_router
from coffer.surfaces.http.mcp.capability_routes import router as mcp_capability_router
from coffer.surfaces.http.mcp.invocation_routes import router as mcp_invocation_router
from coffer.surfaces.http.mcp.protocol_routes import router as mcp_protocol_router
from coffer.surfaces.cli.mcp import app as mcp_cli_app


def make_mcp_kind(on_delete):
    return KindModule(
        name="mcp_server",
        display_name="MCP Server",
        config_schema=MCPServerConfig,
        on_delete=on_delete,
        http_routers=(mcp_server_router, mcp_capability_router, mcp_invocation_router, mcp_protocol_router),
        cli_groups=(mcp_cli_app,),
    )
```

Wire it into `create_app()` so production composition registers the kind.

---

### T064 [TDD] [US1] HTTP `/mcp` JSON-RPC endpoint (POST)

**Files:**

- Create: `backend/coffer/surfaces/http/mcp/__init__.py` (empty)
- Create: `backend/coffer/surfaces/http/mcp/protocol_routes.py`

Accept POST requests with JSON-RPC envelope. Route via the `MCPGatewaySession` keyed by a server-issued session id (set on first `initialize`). One contract test per acceptance scenario from User Story 1.

---

### T065 [TDD] [US1] `/mcp` SSE channel (GET)

Server-Sent Events stream of server-initiated messages (notifications + bidirectional request-from-server). One asyncio task per session pushing to the SSE response.

---

### T066 [TDD] [US1] MCP CRUD routes — `/api/v1/resources/mcp_server/*`

`POST /resources` already creates an mcp_server resource via kind-agnostic route; this task adds the kind-specific routes from the contract:

- `GET /resources/mcp_server/{name}/capabilities`
- `POST .../capabilities/{type}/{key}/enable`
- `POST .../capabilities/{type}/{key}/disable`
- `POST .../refresh`
- `POST .../test`
- `GET .../invocations`

One commit per endpoint group.

---

### T067 [TDD] [US1] CLI: `coffer mcp add/remove/list/show/refresh/test`

Subcommand group `coffer mcp` registered through `MCP_KIND.cli_groups`. Each command calls the relevant `/api/v1/resources/mcp_server/*` route.

---

### T068 [TDD] [US1+US2] CLI: `coffer mcp tool enable/disable/list`

Calls `/api/v1/resources/mcp_server/{name}/capabilities/tool/{key}/enable|disable`.

Acceptance scenario from User Story 2 ("disable an individual capability") covered here.

---

### T069 [TDD] [US1] CLI: `coffer mcp resource enable/disable/list` + `coffer mcp prompt enable/disable/list`

Same shape as T068 with `capability_type=resource` and `capability_type=prompt`. Two tasks; commit each.

---

### T070 [TDD] [US1] CLI: `coffer mcp invocations`

Calls `/api/v1/resources/mcp_server/{name}/invocations`. Rich table output (default) and `--json` (script-friendly).

---

### T071 [TDD] [US1] `coffer-mcp-shim` binary — connect

**Files:**

- Create: `backend/coffer/surfaces/shim/__init__.py` (empty)
- Create: `backend/coffer/surfaces/shim/main.py`

`run()` function called by the `pyproject.toml` `[project.scripts]` `coffer-mcp-shim` entry. On invocation:

1. Resolve daemon via `surfaces/cli/_client.discover()`; if not running, spawn (re-use `surfaces/cli/daemon_cmd._spawn_detached`).
2. Open `POST /mcp` + `GET /mcp` (SSE) connections with the token header.
3. `asyncio.gather` two tasks: stdin→POST and SSE→stdout (line-framed JSON-RPC).

Tests live in `e2e/mcp/` because they require multiple processes.

---

### T072 [TDD] [US1] `coffer-mcp-shim` graceful shutdown

Handle stdin EOF (client closed) and SIGTERM. Close upstream connections, exit 0. Test by sending EOF to the shim's stdin via pytest subprocess.

---

### T073 [TDD] [US1] Contract test: coffer's `/mcp` against the official MCP SDK

**Files:**

- Create: `backend/tests/contract/test_mcp_protocol_conformance.py`

Use `mcp.client.streamable_http.streamablehttp_client` to drive coffer's `/mcp` endpoint as if it were any upstream MCP server. Assert:

- `initialize` returns valid `ServerCapabilities` shape
- `tools/list` returns valid `Tool` shape per the SDK's types
- error response uses correct JSON-RPC error codes

---

### T074 [TDD] [US1] e2e: shim → daemon → fake upstream round trip

**Files:**

- Create: `e2e/mcp/__init__.py` (empty)
- Create: `e2e/mcp/pyproject.toml`
- Create: `e2e/mcp/test_shim_round_trip.py`

Full subprocess wiring: start a daemon, register a `fake_mcp_server`-backed upstream, spawn `coffer-mcp-shim`, drive it via stdin, assert stdout output. Each acceptance scenario from US1 / US2 gets one marked test.

---

### T075 [TDD] [US1] e2e: per-tool disable hides tool from clients

Acceptance test mark `(spec="001-mcp-gateway", scenario="disable an individual capability")`. Register fake server with 3 tools, disable one via `coffer mcp tool disable`, restart shim, assert disabled tool absent from `tools/list`.

---

### T076 [TDD] [US1] e2e: list_changed roundtrip

Use `fake_mcp_server --scenario mutating`. Drive a `tools/call` that triggers the fake server to emit `notifications/tools/list_changed`. Assert shim's stdout contains the forwarded notification within 1 second.

---

### T077 [TDD] [US1] e2e: concurrent clients work without interference

Spawn two shims concurrently, drive each from a separate test task, assert both succeed independently and that one upstream subprocess set per shim was created (count files in `~/.coffer/upstream-pids/`).

---

### T078 Phase 3 checkpoint + MVP gate

Run full `make verify-all` + `make verify-acceptance`. Verify every User Story 1 + 2 scenario in [spec.md](./spec.md) has a marked test. Tag in PR description.

---

## Phases 4 – 6 — Detailed task lists deferred until after MVP

The remaining phases below are listed as **deliverables** at this stage and
will be expanded into bite-sized TDD tasks once Phase 3 lands and we have
learnings from the MVP to inform the breakdown.

### Phase 4 — User Story 3 (P2): CLI completeness (parity with REST)

- T079 `--json` flag on every list/show command
- T080 `--verbose` traceback rendering
- T081 Exit code map per error class
- T082 `coffer credentials set/get/list` (credential management)

### Phase 5 — User Story 4 (P3): Auditing & activity logs (audit + invocations + retention)

- T083 Audit + invocations + retention surfacing

### Phase 6 — Hardening

- T084 Daemon graceful-shutdown signal handler
- T085 Upstream health state-machine end-to-end test
- T086 Bounded log rotation (`RotatingFileHandler` size + retention)
- T087 Concurrent-client load smoke (3 simulated clients × 100 tool calls each)
- T088 Backup-before-migrate verification test
- T089 Gateway-overhead latency test (covers SC-003: 100 fast calls, assert median overhead ≤ 50 ms vs direct upstream)
- T090 Credential-leak audit test (covers SC-010: grep every log/audit/invocation artifact after a credentialed session for keychain values; assert zero hits)
- T091 Final acceptance audit: every Edge Case in [spec.md](./spec.md) has a covering test

---

## Cross-phase notes

### Dependencies

- **Phase 1 → Phase 2**: SQLAlchemy setup + Alembic skeleton + composition root scaffold + error envelope are prerequisites for any Resource code.
- **Phase 2 → Phase 3**: `ResourceService`, repo protocols, audit, retention all in place before MCP code lands (MCP kind plugs into them).
- **Phase 3 → Phase 4**: Phase 3 finishes with a working feature over the CLI surface; later phases build against the now-stable contract.

### Parallelisation

Tasks marked `[P]` can be done concurrently by separate agents. The biggest
parallel band is in Phase 2: T019 (models), T030 (Pydantic schemas), and T035
(CLI groups) can each progress on their own files once the Phase 1 scaffold is
in.

### Acceptance audit

After every commit in Phase 3 onward, `make verify-acceptance` must report zero
orphan markers and zero uncovered scenarios. The acceptance script
(`scripts/audit_acceptance.py`) already exists; no test we add may reference a
non-existent scenario in `spec.md`, and no scenario in `spec.md` may go
uncovered by the end of Phase 6.

### File-size guard

`scripts/check_file_sizes.py` already enforces the constitutional caps. If a
task would push a file over its limit, the task itself is wrong-sized — split
the file before writing.
