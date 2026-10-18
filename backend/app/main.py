"""HTTP scaffold. Health must not initialize any external integration."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Qadam Astana API", version="0.1.0")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report process health without reading secrets or connecting to services."""
    return HealthResponse()
