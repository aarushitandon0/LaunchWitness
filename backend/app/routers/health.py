from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.safety.access import ActorDep
from app.selfcheck import mailbox_warning, warnings  # noqa: F401  (mailbox_warning: re-exported for callers)

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(settings: Annotated[Settings, Depends(get_settings)], actor: ActorDep) -> dict:
    """Liveness + the startup self-check. Anyone sees the harmless warnings; the admin sees all of them.
    Never a secret value."""
    out: dict = {"ok": True, "env": settings.godaddy_env}
    found = [w for w in warnings(settings) if w.public or actor.is_admin]
    if found:
        out["warnings"] = [w.text for w in found]
        out["warning_codes"] = [w.code for w in found]
    return out
