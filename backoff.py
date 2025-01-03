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
        self._last_error = None

    def should_retry(self) -> bool:
        """Check if we should retry based on backoff strategy"""
        if self._next_retry_time is None:
            return True
        return datetime.now() >= self._next_retry_time

    def update_backoff_state(self, success: bool, error_type: str = None):
        """
        Update backoff state based on success/failure
        
        Args:
            success (bool): Whether the operation was successful
            error_type (str, optional): Type of error that occurred (e.g., 'connection', 'timeout')
        """
        if success:
            if self._consecutive_failures > 0:
                logger.info("Connection restored after %d failures", self._consecutive_failures)
            # Reset backoff on success
            self._consecutive_failures = 0
            self._next_retry_time = None
            self._last_error = None
        else:
            # Update backoff on failure
            self._consecutive_failures += 1
            self._last_error = error_type
            backoff_seconds = min(
                self._initial_backoff * (3 ** (self._consecutive_failures - 1)),
                self._max_backoff
            )
            self._next_retry_time = datetime.now() + timedelta(seconds=backoff_seconds)
            
            # Log more informative message based on error type
            if error_type == 'connection':
                logger.warning("Connection failed (%d consecutive failures). Backing off for %d seconds. Next retry at %s",
                             self._consecutive_failures, backoff_seconds, self._next_retry_time.strftime('%H:%M:%S'))
            elif error_type == 'timeout':
                logger.warning("Request timed out (%d consecutive failures). Backing off for %d seconds. Next retry at %s",
                             self._consecutive_failures, backoff_seconds, self._next_retry_time.strftime('%H:%M:%S'))
            else:
                logger.warning("Operation failed (%d consecutive failures). Backing off for %d seconds. Next retry at %s",
                             self._consecutive_failures, backoff_seconds, self._next_retry_time.strftime('%H:%M:%S'))

    def get_retry_time_str(self) -> str:
        """Get a string representation of the next retry time"""
        if self._next_retry_time:
            return self._next_retry_time.strftime('%H:%M:%S')
        return ""

    def reset(self):
        """Reset the backoff state"""
        self._consecutive_failures = 0
        self._next_retry_time = None
        self._last_error = None

    def get_failure_count(self) -> int:
        """Get the number of consecutive failures"""
        return self._consecutive_failures

    def get_last_error(self) -> str:
        """Get the type of the last error that occurred"""
        return self._last_error 