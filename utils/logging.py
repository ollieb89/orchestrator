import structlog
import logging
import sys
from typing import Optional

def setup_logging(level: str = "INFO", service_name: str = "grid"):
    """Setup structured logging"""
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure root logger
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper()))
    
    return structlog.get_logger(service_name)

class StructuredLogger:
    """Wrapper for structured logging"""
    def __init__(self, name: str):
        self.logger = structlog.get_logger(name)
    
    def info(self, msg: str, **kwargs):
        self.logger.info(msg, **kwargs)
    
    def error(self, msg: str, **kwargs):
        self.logger.error(msg, **kwargs)
    
    def warning(self, msg: str, **kwargs):
        self.logger.warning(msg, **kwargs)
    
    def debug(self, msg: str, **kwargs):
        self.logger.debug(msg, **kwargs)