import time
from collections import deque


class SlidingWindow:
    """Limite por chave em memoria. Em servidor com varias instancias, cada uma conta separado."""

    def __init__(self, limit: int, seconds: float, max_keys: int = 10_000):
        self.limit = limit
        self.seconds = seconds
        self.max_keys = max_keys
        self.hits: dict[str, deque] = {}

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if len(self.hits) > self.max_keys:
            self.hits.clear()

        window = self.hits.setdefault(key, deque())
        while window and now - window[0] > self.seconds:
            window.popleft()
        if len(window) >= self.limit:
            return False
        window.append(now)
        return True
