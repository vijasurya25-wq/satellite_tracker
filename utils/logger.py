"""
utils/logger.py
---------------
Centralized logging configuration.
Call `setup_logging()` once at application startup.
"""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """
    Configure root logger with a clean, coloured console handler.
    level: "DEBUG" | "INFO" | "WARNING" | "ERROR"
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    fmt = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
    datefmt = "%H:%M:%S"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt))

    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.handlers.clear()
    root.addHandler(handler)
