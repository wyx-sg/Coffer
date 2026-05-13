from fastapi import FastAPI
from pydantic import BaseModel

from coffer import __version__

app = FastAPI(
    title="Coffer",
    version=__version__,
    description="Local-first AI agent vault.",
)


class HealthResponse(BaseModel):
    status: str
    version: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)
