from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class ExponentialBackoff:
    def __init__(self, initial_backoff=180, max_backoff=3600):
        """
        Initialize exponential backoff with configurable parameters.
        
        Args:
            initial_backoff (int): Initial backoff time in seconds (default: 180s = 3 minutes)
            max_backoff (int): Maximum backoff time in seconds (default: 3600s = 1 hour)
        """
        self._consecutive_failures = 0
        self._next_retry_time = None
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff

    def should_retry(self) -> bool:
        """Check if we should retry based on backoff strategy"""
        if self._next_retry_time is None:
            return True
        return datetime.now() >= self._next_retry_time

    def update_backoff_state(self, success: bool):
        """Update backoff state based on success/failure"""
        if success:
            # Reset backoff on success
            self._consecutive_failures = 0
            self._next_retry_time = None
        else:
            # Update backoff on failure
            self._consecutive_failures += 1
            backoff_seconds = min(
                self._initial_backoff * (3 ** (self._consecutive_failures - 1)),
                self._max_backoff
            )
            self._next_retry_time = datetime.now() + timedelta(seconds=backoff_seconds)
            logger.warning(f"Connection failed. Backing off for {backoff_seconds} seconds. Next retry at {self._next_retry_time.strftime('%H:%M:%S')}")

    def get_retry_time_str(self) -> str:
        """Get a string representation of the next retry time"""
        if self._next_retry_time:
            return self._next_retry_time.strftime('%H:%M:%S')
        return "" 