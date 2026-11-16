"""S13 B: one shared limit on GoDaddy API calls for the whole process (GoDaddy allows 60 requests a minute per
endpoint; we stay under that across ALL endpoints, so monitoring many shops at once can't get us blocked).

A sliding window: at most `calls` in any `period` seconds. A caller over the limit waits (it never fails).
"""

import threading
import time
from collections import deque
from collections.abc import Callable

GODADDY_PER_MINUTE = 50


class RateLimiter:
    def __init__(self, calls: int = GODADDY_PER_MINUTE, period: float = 60.0,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        self.calls, self.period, self.clock, self.sleep = calls, period, clock, sleep
        self._times: deque[float] = deque()
        self._lock = threading.Lock()
        self.waited = 0.0  # total seconds callers waited (for the team's numbers and tests)

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = self.clock()
                while self._times and self._times[0] <= now - self.period:
                    self._times.popleft()
                if len(self._times) < self.calls:
                    self._times.append(now)
                    return
                wait = self._times[0] + self.period - now
            self.waited += max(wait, 0.0)
            self.sleep(max(wait, 0.001))


LIMITER = RateLimiter()  # every real GoDaddy request in this process goes through this one
