"""HTTP layer: one session, timeouts, retries with backoff, per-host rate limiting.

Every call returns a FetchResult rather than raising, so callers can tell the
difference between "the source answered and the job is gone" (ok=True, status
404) and "we could not reach the source" (ok=False). Only the former is ever
allowed to contribute to marking a vacancy closed.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests

from .config import SETTINGS

log = logging.getLogger(__name__)

USER_AGENT = "london-job-dashboard/1.0 (personal job search; +https://github.com)"

# Minimum seconds between requests to the same host
HOST_MIN_INTERVAL = {
    "api.adzuna.com": 2.6,           # Adzuna free tier: 25 hits/minute
    "www.reed.co.uk": 1.0,
    "boards-api.greenhouse.io": 0.4,
    "api.lever.co": 0.4,
    "api.eu.lever.co": 0.4,
    "api.ashbyhq.com": 0.4,
    "api.smartrecruiters.com": 0.5,
    "api.anthropic.com": 0.5,
}
DEFAULT_INTERVAL = 1.0


@dataclass
class FetchResult:
    ok: bool                 # True if the server gave a definitive HTTP answer
    status: int | None = None
    data: Any = None
    text: str = ""
    error: str = ""
    attempts: int = 0

    @property
    def not_found(self) -> bool:
        return self.ok and self.status in (404, 410)


@dataclass
class Http:
    session: requests.Session = field(default_factory=requests.Session)
    timeout: int = SETTINGS["http_timeout"]
    retries: int = 3
    _last: dict = field(default_factory=dict)
    calls: dict = field(default_factory=dict)

    def __post_init__(self):
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    def _throttle(self, host: str) -> None:
        gap = HOST_MIN_INTERVAL.get(host, DEFAULT_INTERVAL)
        wait = self._last.get(host, 0) + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.monotonic()

    def request(self, method: str, url: str, *, want_json: bool = True, **kw) -> FetchResult:
        host = urlparse(url).netloc
        kw.setdefault("timeout", self.timeout)
        last_err = ""
        for attempt in range(1, self.retries + 1):
            self._throttle(host)
            self.calls[host] = self.calls.get(host, 0) + 1
            try:
                r = self.session.request(method, url, **kw)
            except requests.RequestException as e:  # network/timeout -> retry
                last_err = f"{type(e).__name__}: {e}"[:300]
                time.sleep(min(2 ** attempt, 20))
                continue
            if r.status_code == 429 or r.status_code >= 500:
                last_err = f"HTTP {r.status_code}"
                retry_after = r.headers.get("Retry-After", "")
                delay = int(retry_after) if retry_after.isdigit() else 2 ** attempt * 2
                time.sleep(min(delay, 60))
                continue
            if r.status_code in (401, 403):
                # Access refused: definitive for *the source*, never for the vacancy
                return FetchResult(ok=False, status=r.status_code, error=f"HTTP {r.status_code} (access refused)",
                                   text=r.text[:500], attempts=attempt)
            data = None
            if want_json and r.status_code < 400:
                try:
                    data = r.json()
                except ValueError:
                    return FetchResult(ok=False, status=r.status_code, error="invalid JSON",
                                       text=r.text[:500], attempts=attempt)
            return FetchResult(ok=True, status=r.status_code, data=data,
                               text="" if want_json else r.text, attempts=attempt)
        return FetchResult(ok=False, error=last_err or "unknown error", attempts=self.retries)

    def get(self, url: str, **kw) -> FetchResult:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw) -> FetchResult:
        return self.request("POST", url, **kw)
