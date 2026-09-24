"""Check cited sections against the live site at answer time.

The index is a snapshot. Between two ingestion runs Parliament can amend a
section, and bdlaws edits the page in place. For the handful of sections an
answer actually cites, one request each is cheap insurance: re-fetch the page,
parse it with the same parser, and say whether the text we answered from is
still the text the site publishes.

  current      the cited text still appears verbatim on the live page
  changed      the page no longer contains it — re-run `ingest.py --update`
  unavailable  the site did not answer in time (the answer is still shown)

Off by default (BDRAG_VERIFY_LIVE=true turns it on): it makes the answer depend
on a government website's latency, which is a product decision, not a default.
"""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from ingest.fetch import Fetcher
from ingest.models import Act, SectionRef
from ingest.parse import parse_section
from ingest.textutils import normalize

from .store import Hit


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", normalize(text)).strip()


def verify_hit(hit: Hit, fetcher: Fetcher) -> str:
    m = hit.metadata
    url = m.get("url")
    if m.get("type") != "section" or not url:
        return "unavailable"
    ref = SectionRef(section_id=int(m["section_id"]), number=str(m.get("section_number") or ""),
                     number_ascii=str(m.get("section_number_ascii") or ""),
                     title=str(m.get("section_title") or ""), chapter=m.get("chapter"), url=url)
    act = Act(act_id=int(m["act_id"]), title=str(m.get("act_title") or ""), act_number=None,
              date=None, preamble=None, year=m.get("act_year"), language=m.get("language", ""),
              repealed=bool(m.get("repealed")), url="")
    try:
        live = parse_section(fetcher.get(url, refresh=True), ref, act)
    except Exception:
        return "unavailable"
    return "current" if _flat(hit.body) in _flat(live.text) else "changed"


def verify_cited(hits: list[Hit], cited: list[int], fetcher: Fetcher,
                 timeout_s: float = 6.0, max_checks: int = 3) -> dict[int, str]:
    """{excerpt number: status} for up to `max_checks` cited excerpts, in parallel,
    with an overall deadline so a slow site cannot hold the answer hostage."""
    todo = [n for n in cited if 1 <= n <= len(hits)][:max_checks]
    if not todo:
        return {}
    pool = ThreadPoolExecutor(max_workers=len(todo))
    futures = {n: pool.submit(verify_hit, hits[n - 1], fetcher) for n in todo}
    out: dict[int, str] = {}
    deadline = time.monotonic() + timeout_s
    for n, fut in futures.items():
        try:
            out[n] = fut.result(timeout=max(deadline - time.monotonic(), 0.01))
        except FutureTimeout:
            out[n] = "unavailable"
    pool.shutdown(wait=False, cancel_futures=True)
    return out
