"""
Simple logging utility for debug messages.
"""

from typing import Optional, Dict, Any
from flask import current_app


def debug_log(message: str, extra: Optional[Dict[str, Any]] = None):
    """Emit log messages only in debug mode, with optional structured context."""
    if current_app and current_app.debug:
        if extra:
            try:
                current_app.logger.info("%s | %s", message, extra)
            except Exception:
                current_app.logger.info(message)
        else:
            current_app.logger.info(message)