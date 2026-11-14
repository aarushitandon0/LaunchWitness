"""Internal endpoints (called by Caddy on the private network, not exposed publicly)."""

from fastapi import APIRouter

router = APIRouter(prefix="/internal", tags=["internal"])
