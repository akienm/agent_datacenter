"""
LoggingControlCenter — hierarchical log routing for agent_datacenter devices.

Log tree layout:
  datacenter_logs/
    igor/
      cognition/
        igor.log
      memory/
        igor.log
    postgres/
      postgres.log
    template/
      template.log

Each device gets its own directory; subsystems get a subdirectory within
the device directory. All log files use RotatingFileHandler (10MB, 5 backups).

Usage:
    from agent_datacenter.logcontrol.control_center import LoggingControlCenter
    LoggingControlCenter.configure(Path('datacenter_logs'))
    log = LoggingControlCenter.instance().get_logger('igor', 'cognition')
    log.info('cognition cycle complete')
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


class LoggingControlCenter:
    _instance: LoggingControlCenter | None = None
    _root: Path | None = None

    def __init__(self, root: Path) -> None:
        self._root = root

    @classmethod
    def configure(cls, root: Path) -> LoggingControlCenter:
        """Set the log root and return the singleton instance."""
        cls._instance = cls(root)
        return cls._instance

    @classmethod
    def instance(cls) -> LoggingControlCenter:
        if cls._instance is None:
            raise RuntimeError(
                "LoggingControlCenter not configured. "
                "Call LoggingControlCenter.configure(path) first."
            )
        return cls._instance

    def get_logger(
        self, device_id: str, subsystem: str | None = None
    ) -> logging.Logger:
        """
        Return a Python logger wired to the correct datacenter_logs path.

        Logger name: '{device_id}.{subsystem}' or '{device_id}' if no subsystem.
        Log file:    datacenter_logs/{device_id}/{subsystem}/{device_id}.log
                     or datacenter_logs/{device_id}/{device_id}.log
        """
        if subsystem:
            log_dir = self._root / device_id / subsystem
            logger_name = f"{device_id}.{subsystem}"
        else:
            log_dir = self._root / device_id
            logger_name = device_id

        logger = logging.getLogger(logger_name)
        if logger.handlers:
            return logger  # already configured in this process

        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{device_id}.log"

        handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        return logger
