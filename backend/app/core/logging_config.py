"""
Logging configuration for the application
"""

import copy
import logging
import sys
from datetime import datetime
from pathlib import Path

from uvicorn.config import LOGGING_CONFIG as UVICORN_LOGGING_CONFIG


def setup_logging():
    """Setup application logging configuration"""
    
    # Create logs directory
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    )
    
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler for general logs
    file_handler = logging.FileHandler(
        logs_dir / f"app_{datetime.now().strftime('%Y%m%d')}.log"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(file_handler)
    
    # Error file handler
    error_handler = logging.FileHandler(
        logs_dir / f"errors_{datetime.now().strftime('%Y%m%d')}.log"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(error_handler)
    
    # Task execution logger
    task_logger = logging.getLogger("task_execution")
    task_handler = logging.FileHandler(
        logs_dir / f"tasks_{datetime.now().strftime('%Y%m%d')}.log"
    )
    task_handler.setLevel(logging.DEBUG)
    task_handler.setFormatter(detailed_formatter)
    task_logger.addHandler(task_handler)
    task_logger.setLevel(logging.DEBUG)
    
    # API logger
    api_logger = logging.getLogger("api")
    api_handler = logging.FileHandler(
        logs_dir / f"api_{datetime.now().strftime('%Y%m%d')}.log"
    )
    api_handler.setLevel(logging.INFO)
    api_handler.setFormatter(detailed_formatter)
    api_logger.addHandler(api_handler)
    api_logger.setLevel(logging.INFO)
    
    # Set specific loggers to appropriate levels
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("celery").setLevel(logging.INFO)
    
    logging.info("✅ Logging configuration completed")


def build_uvicorn_log_config():
    """Return a uvicorn log config that includes timestamps in every formatter."""
    config = copy.deepcopy(UVICORN_LOGGING_CONFIG)

    detailed_format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    access_format = (
        "%(asctime)s - %(levelname)s - %(client_addr)s - %(request_line)s - %(status_code)s"
    )

    if "formatters" in config:
        if "default" in config["formatters"]:
            config["formatters"]["default"]["fmt"] = detailed_format
        if "access" in config["formatters"]:
            config["formatters"]["access"]["fmt"] = access_format

    return config
