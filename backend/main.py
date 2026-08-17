import logging

import backend.bootstrap  # noqa: F401  (import side-effect: see backend/bootstrap.py)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from backend.app.factory import create_app
from backend.core.log_redaction import install_redaction

install_redaction(*logging.getLogger().handlers)

app = create_app()
