import time
import random
import logging
from typing import Callable, TypeVar, Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')

class RetryConfig:
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for attempt with exponential backoff"""
        delay = min(
            self.initial_delay * (self.exponential_base ** attempt),
            self.max_delay
        )
        
        if self.jitter:
            # Add random jitter (±25%)
            delay = delay * (0.75 + random.random() * 0.5)
        
        return delay

def retry(
    config: Optional[RetryConfig] = None,
    exceptions: tuple = (Exception,)
) -> Callable:
    """Decorator for retrying functions with exponential backoff"""
    config = config or RetryConfig()
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(config.max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < config.max_retries - 1:
                        delay = config.get_delay(attempt)
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{config.max_retries}): {e}. "
                            f"Retrying in {delay:.1f}s"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {config.max_retries} attempts"
                        )
            
            raise last_exception
        
        return wrapper
    return decorator

class RetryContext:
    """Context manager for retry logic"""
    def __init__(self, config: Optional[RetryConfig] = None, exceptions: tuple = (Exception,)):
        self.config = config or RetryConfig()
        self.exceptions = exceptions
        self.attempt = 0
    
    def __enter__(self):
        self.attempt = 0
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type and issubclass(exc_type, self.exceptions):
            if self.attempt < self.config.max_retries - 1:
                delay = self.config.get_delay(self.attempt)
                logger.warning(f"Retrying in {delay:.1f}s: {exc_val}")
                time.sleep(delay)
                self.attempt += 1
                return True  # Suppress exception
        return False
