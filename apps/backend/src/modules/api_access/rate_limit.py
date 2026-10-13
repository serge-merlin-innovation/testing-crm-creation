import math
from collections import defaultdict, deque
from datetime import datetime, timedelta

REQUESTS_PER_MINUTE = 100
WINDOW = timedelta(minutes=1)


class SlidingWindowLimiter:
    """Per-client sliding window, in process memory.

    One app instance is assumed: with several replicas each would allow its own 100 per minute.
    """

    def __init__(self, limit: int = REQUESTS_PER_MINUTE, window: timedelta = WINDOW) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[datetime]] = defaultdict(deque)

    def hit(self, key: str, now: datetime) -> int | None:
        """Counts one request. Returns None when allowed, else the seconds until a slot frees."""
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return max(1, math.ceil((hits[0] + self.window - now).total_seconds()))
        hits.append(now)
        return None

    def reset(self) -> None:
        self._hits.clear()


limiter = SlidingWindowLimiter()
