"""Retry utilities for async operations."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on: tuple[type[Exception], ...] = (Exception,)


class RetryError(Exception):
    """Raised when all retry attempts are exhausted."""
    
    def __init__(self, last_exception: Exception, attempts: int) -> None:
        self.last_exception = last_exception
        self.attempts = attempts
        super().__init__(f"Failed after {attempts} attempts. Last error: {last_exception}")


async def retry_async(
    func: Callable[..., Any],
    *args: Any,
    config: RetryConfig | None = None,
    **kwargs: Any,
) -> T:
    """Retry an async function with exponential backoff."""
    if config is None:
        config = RetryConfig()
    
    last_exception = None
    
    for attempt in range(config.max_attempts):
        try:
            return await func(*args, **kwargs)
        except config.retry_on as e:
            last_exception = e
            
            if attempt == config.max_attempts - 1:
                logger.error(
                    "All retry attempts exhausted",
                    function=func.__name__,
                    attempts=attempt + 1,
                    error=str(e),
                )
                raise RetryError(e, attempt + 1) from e
            
            # Calculate delay
            delay = min(
                config.base_delay * (config.exponential_base ** attempt),
                config.max_delay,
            )
            
            if config.jitter:
                delay *= (0.5 + random.random() * 0.5)
            
            logger.warning(
                "Attempt failed, retrying",
                function=func.__name__,
                attempt=attempt + 1,
                max_attempts=config.max_attempts,
                delay=delay,
                error=str(e),
            )
            
            await asyncio.sleep(delay)


def retry_sync(
    func: Callable[..., Any],
    *args: Any,
    config: RetryConfig | None = None,
    **kwargs: Any,
) -> T:
    """Retry a sync function with exponential backoff."""
    if config is None:
        config = RetryConfig()
    
    last_exception = None
    
    for attempt in range(config.max_attempts):
        try:
            return func(*args, **kwargs)
        except config.retry_on as e:
            last_exception = e
            
            if attempt == config.max_attempts - 1:
                logger.error(
                    "All retry attempts exhausted",
                    function=func.__name__,
                    attempts=attempt + 1,
                    error=str(e),
                )
                raise RetryError(e, attempt + 1) from e
            
            # Calculate delay
            delay = min(
                config.base_delay * (config.exponential_base ** attempt),
                config.max_delay,
            )
            
            if config.jitter:
                delay *= (0.5 + random.random() * 0.5)
            
            logger.warning(
                "Attempt failed, retrying",
                function=func.__name__,
                attempt=attempt + 1,
                max_attempts=config.max_attempts,
                delay=delay,
                error=str(e),
            )
            
            time.sleep(delay)  # type: ignore[name-defined]
