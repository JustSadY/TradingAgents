import logging

from fastapi import HTTPException

import backend.bootstrap  # noqa: F401  (import side-effect: see backend/bootstrap.py)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from backend.app.factory import create_app
from backend.app.lifespan import _load_cron_settings, lifespan
from backend.core.config import get_settings
from backend.core.log_redaction import install_redaction
from backend.realtime.analysis_websocket import (
    _WS_AUTH_REVALIDATION_SECONDS,
    _analysis_websocket_access_is_current,
    _reject_websocket,
    websocket_analysis,
    ws_manager,
)
from backend.startup.seeds import seed_admin_user as _seed_admin_user

install_redaction(*logging.getLogger().handlers)

settings = get_settings()
app = create_app()
