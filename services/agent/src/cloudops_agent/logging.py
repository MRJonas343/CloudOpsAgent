"""Structured logging helper for the agent service."""

import logging
import sys


def configure_logging(level: str = "INFO", service: str = "agent") -> None:
    log_format = f"%(asctime)s %(levelname)s service={service} %(message)s"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(log_format))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
