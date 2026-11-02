from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness/readiness probe. Contract: exactly ``{"status":"ok"}``."""
    return {"status": "ok"}
