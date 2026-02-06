"""
Logging configuration for Testflow Framework
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

def setup_logger(name: str = "testflow", log_file: str = None, level=logging.INFO):
    """
    Setup logger with console and file handlers

    Args:
        name: Logger name
        log_file: Optional log file path
        level: Logging level
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Remove existing handlers
    logger.handlers.clear()

    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    simple_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)

    # File handler (if log file specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        logger.addHandler(file_handler)

    return logger

# Create default logger
default_log_file = f"logs/testflow_{datetime.now().strftime('%Y%m%d')}.log"
logger = setup_logger("testflow", default_log_file, logging.INFO)
