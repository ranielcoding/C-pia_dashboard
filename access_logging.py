from __future__ import annotations

import logging
import sys


_LOGGER = logging.getLogger("dashboard.access")
_LOGGER.setLevel(logging.INFO)
_LOGGER.propagate = False

if not _LOGGER.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    _LOGGER.addHandler(_handler)


def log_page_access(*, username: str, role: str, page_title: str) -> None:
    """Write a page access event to the terminal running Streamlit."""
    _LOGGER.info(
        "ACESSO | usuario=%s | perfil=%s | pagina=%s",
        username,
        role,
        page_title,
    )
