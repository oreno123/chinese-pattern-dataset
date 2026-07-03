"""HTTP client with rate limiting and retry for the pattern-dataset project."""
from __future__ import annotations

import time
from typing import Any

import httpx


class RateLimiter:
    """Simple token-bucket-ish rate limiter: max `calls` per `period` seconds."""

    def __init__(self, calls: float, period: float = 1.0) -> None:
        self.min_interval = period / calls if calls > 0 else 0
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()


class HttpClient:
    """HTTP client with retry on transient errors + rate limiting."""

    def __init__(
        self,
        rate_limiter: RateLimiter | None = None,
        max_retries: int = 3,
        timeout: float = 30.0,
    ) -> None:
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)
        self.rate_limiter = rate_limiter or RateLimiter(calls=3.0)
        self.max_retries = max_retries

    def get_json(self, url: str, params: dict | None = None) -> dict:
        return self._request("GET", url, params=params, json_resp=True)

    def download(self, url: str, dest: Any) -> int:
        """Stream-download binary content to a Path-like dest. Returns bytes written."""
        resp = self._request("GET", url, json_resp=False)
        data = resp.content
        with open(dest, "wb") as f:
            f.write(data)
        return len(data)

    def _request(self, method: str, url: str, **kwargs) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            self.rate_limiter.wait()
            try:
                resp = self.client.request(method, url, **kwargs)
                resp.raise_for_status()
                if kwargs.get("json_resp", False):
                    return resp.json()
                return resp
            except httpx.HTTPStatusError as e:
                last_exc = e
                if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                    raise
                # 429 or 5xx: retry
                backoff = (2 ** attempt) * 5
                time.sleep(backoff)
            except (httpx.RequestError, httpx.HTTPError) as e:
                last_exc = e
                backoff = (2 ** attempt) * 2
                time.sleep(backoff)
        raise RuntimeError(f"request failed after {self.max_retries} retries: {last_exc}")

    def close(self) -> None:
        self.client.close()
