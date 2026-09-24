"""Polite, cached HTTP fetching.

Every page is saved under data/raw/ the first time it is downloaded, so you can
re-run parsing and chunking as often as you like without hitting the server.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

BASE_URL = "http://bdlaws.minlaw.gov.bd"


class Fetcher:
    def __init__(
        self,
        cache_dir: str | Path = "data/raw",
        delay: float = 1.0,
        retries: int = 3,
        timeout: float = 30.0,
        offline: bool = False,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.offline = offline          # cache only: re-parse without touching the site
        self._last = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {
                # Identify the crawler honestly, with a way to reach its owner.
                "User-Agent": os.environ.get(
                    "BDRAG_USER_AGENT",
                    "bd-legal-rag/1.0 research crawler (+https://github.com/roy032/bd-legal-rag)"),
                "Accept-Language": "bn,en;q=0.8",
            }
        )

    def _cache_path(self, url: str) -> Path:
        # Readable file name + short hash so ?lang= variants don't collide.
        tail = url.replace(BASE_URL, "").strip("/").replace("/", "__") or "index"
        tail = tail.split("?")[0][:80]
        h = hashlib.sha1(url.encode()).hexdigest()[:8]
        return self.cache_dir / f"{tail}.{h}.html"

    def get(self, url: str, refresh: bool = False) -> str:
        if url.startswith("/"):
            url = BASE_URL + url
        path = self._cache_path(url)
        if path.exists() and not refresh:
            return path.read_text(encoding="utf-8")
        if self.offline:
            raise FileNotFoundError(f"not in cache (offline mode): {url}")

        for attempt in range(1, self.retries + 1):
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                self._last = time.monotonic()
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                # The site serves UTF-8. Charset *guessing* on Bangla pages is
                # unreliable, so only trust an explicit, non-default header.
                if not resp.encoding or resp.encoding.lower() in ("iso-8859-1", "ascii"):
                    resp.encoding = "utf-8"
                html = resp.text
                path.write_text(html, encoding="utf-8")
                return html
            except requests.RequestException as e:
                log.warning("GET %s failed (attempt %d/%d): %s", url, attempt, self.retries, e)
                time.sleep(self.delay * 2**attempt)  # exponential backoff
        raise RuntimeError(f"Could not fetch {url}")
