"""
app/utils/logging.py
Structured logging untuk LiterasiAI.
"""
import logging
import sys
from typing import Optional

from config import Config


class LogFormatter(logging.Formatter):
    """Custom formatter dengan warna untuk development."""

    COLORS = {
        "DEBUG":    "\033[36m",
        "INFO":     "\033[32m",
        "WARNING":  "\033[33m",
        "ERROR":    "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record):
        if hasattr(sys, "_MEIPASS"):
            self._style._fmt = "[%(asctime)s] %(levelname)s [%(name)s] %(message)s"
            return super().format(record)

        color = self.COLORS.get(record.levelname, self.RESET)
        self._style._fmt = (
            f"{color}[%(asctime)s] %(levelname)s{RESET} "
            f"[%(name)s] %(message)s"
        )
        return super().format(record)


def setup_logging(name: str = "literasiai", level: Optional[str] = None) -> logging.Logger:
    """
    Setup structured logger untuk aplikasi.
    """
    log_level = level or Config.FLASK_ENV
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(numeric_level)

    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)
    handler.setFormatter(LogFormatter(
        fmt="[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(handler)

    return logger


def get_logger(name: str = "literasiai") -> logging.Logger:
    """Ambil logger instance."""
    return logging.getLogger(name)