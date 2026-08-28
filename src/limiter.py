import time
import threading
import random

class GlobalRateLimiter:
    def __init__(self, min_interval_sec=5.0, jitter_sec=2.0):
        self.min_interval = min_interval_sec
        self.jitter = jitter_sec
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self):
        with self._lock:
            elapsed = time.time() - self._last_call
            delay = self.min_interval + random.uniform(0, self.jitter)
            if elapsed < delay:
                time.sleep(delay - elapsed)
            self._last_call = time.time()

# Singleton instance
rate_limiter = GlobalRateLimiter(min_interval_sec=5.0)
