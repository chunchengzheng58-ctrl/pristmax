# -*- coding: utf-8 -*-
"""
Logging Utilities

Provides structured logging with rotation and multiple outputs.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler


def setup_logger(
    name: str = 'semantic_reduction',
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> logging.Logger:
    """
    Setup logger with console and file handlers.

    Args:
        name: Logger name
        log_file: Path to log file (optional)
        level: Logging level
        max_bytes: Max file size before rotation
        backup_count: Number of backup files to keep

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (with rotation)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


class LogContext:
    """
    Context manager for adding context to log messages.
    """

    def __init__(self, logger: logging.Logger, **context):
        self.logger = logger
        self.context = context
        self.original_factory = None

    def __enter__(self):
        # Store original factory
        self.original_factory = logging.getLogRecordFactory()

        # Create new factory with context
        old_factory = self.original_factory

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            for key, value in self.context.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original factory
        if self.original_factory:
            logging.setLogRecordFactory(self.original_factory)


class AuditLogger:
    """
    Audit logger for compliance tracking.
    """

    def __init__(self, log_file: str):
        """
        Initialize audit logger.

        Args:
            log_file: Path to audit log file
        """
        self.log_file = log_file
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger('audit')
        self.logger.setLevel(logging.INFO)

        handler = RotatingFileHandler(
            log_file,
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=10,
            encoding='utf-8'
        )
        handler.setFormatter(logging.Formatter(
            '%(asctime)s|%(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        self.logger.addHandler(handler)

    def log(
        self,
        action: str,
        data_id: str,
        data_type: str,
        original_size: int = 0,
        new_size: int = 0,
        reason: str = '',
        actor: str = 'system'
    ) -> None:
        """
        Log an audit event.

        Args:
            action: Action taken (preserve, reduce, delete)
            data_id: Identifier of the data
            data_type: Type of data (video, log, etc.)
            original_size: Original size in bytes
            new_size: Size after action
            reason: Reason for action
            actor: Who performed the action
        """
        message = f"{actor}|{action}|{data_id}|{data_type}|{original_size}|{new_size}|{reason}"
        self.logger.info(message)

    def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        action: Optional[str] = None
    ) -> list:
        """
        Query audit log entries.

        Args:
            start_time: Start of time range
            end_time: End of time range
            action: Filter by action type

        Returns:
            List of matching log entries
        """
        entries = []

        if not os.path.exists(self.log_file):
            return entries

        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) < 7:
                    continue

                timestamp_str, actor, act, data_id, dtype, orig_sz, new_sz = parts[:7]
                reason = '|'.join(parts[7:]) if len(parts) > 7 else ''

                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                except:
                    continue

                # Apply filters
                if start_time and timestamp < start_time:
                    continue
                if end_time and timestamp > end_time:
                    continue
                if action and act != action:
                    continue

                entries.append({
                    'timestamp': timestamp,
                    'actor': actor,
                    'action': act,
                    'data_id': data_id,
                    'data_type': dtype,
                    'original_size': int(orig_sz),
                    'new_size': int(new_sz),
                    'reason': reason
                })

        return entries


# Default logger instance
_logger: Optional[logging.Logger] = None


def get_logger() -> logging.Logger:
    """Get default logger instance"""
    global _logger
    if _logger is None:
        _logger = setup_logger()
    return _logger
