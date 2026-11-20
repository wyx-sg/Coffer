"""HTTP surface for memory (spec memory "Show and edit memory on the Memory
page", "Tidy memory as one change"): ``/api/v1/memory``."""

from fastapi import APIRouter

from coffer.surfaces.http.memory.routes import router as _router

routers: tuple[APIRouter, ...] = (_router,)

__all__ = ["routers"]
