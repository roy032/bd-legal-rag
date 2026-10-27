#!/usr/bin/env python
"""Synthetic check of a running service, the way a visitor would hit it.

Alive, ready, a canary search that must return a section, and (optionally) the
index age and the home page. Exit status 1 on any failure, so a scheduler (the
uptime workflow, cron, a free uptime monitor's "keyword" check) can alert on it.
Standard library only: it runs anywhere Python does, without installing the package.

  bdrag probe --url https://<you>-bd-legal-rag.hf.space
  bdrag probe --url http://localhost:8000 --max-index-age-days 45 --json-out probe.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

CANARY = "দণ্ডবিধি ধারা ৩০২"          # resolves by reference on every index built from bdlaws


def fetch(url: str, body: dict | None = None, timeout: float = 20.0) -> tuple[int, dict | str, float]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"content-type": "application/json",
                                          "user-agent": "bdrag-probe/1"})
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 (operator-given URL)
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    took = time.perf_counter() - start
    text = raw.decode("utf-8", "replace")
    try:
        return status, json.loads(text), took
    except ValueError:
        return status, text, took


def run(base: str, canary: str = CANARY, max_index_age_days: float = 0,
        slo_search_s: float = 5.0, timeout: float = 20.0, get=fetch) -> list[dict]:
    base = base.rstrip("/")
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str, took: float | None = None) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail,
                       "ms": round(took * 1000) if took is not None else None})

    def attempt(name: str, path: str, body: dict | None = None):
        try:
            return get(base + path, body, timeout)
        except (OSError, ValueError) as e:
            check(name, False, f"{type(e).__name__}: {e}")
            return None

    if (r := attempt("live", "/livez")) is not None:
        check("live", r[0] == 200, f"HTTP {r[0]}", r[2])
    if (r := attempt("ready", "/readyz")) is not None:
        status, body, took = r
        state = body.get("status") if isinstance(body, dict) else None
        check("ready", status == 200 and state == "ready", f"HTTP {status}, {state}", took)
        if max_index_age_days and isinstance(body, dict) and body.get("index_built_at"):
            import calendar
            built = calendar.timegm(time.strptime(body["index_built_at"], "%Y-%m-%dT%H:%M:%SZ"))
            days = (time.time() - built) / 86400
            check("index age", days <= max_index_age_days,
                  f"built {body['index_built_at'][:10]}, {days:.0f} days ago")
    if (r := attempt("search", "/search", {"question": canary, "k": 3})) is not None:
        status, body, took = r
        hits = body.get("results", []) if isinstance(body, dict) else []
        ok = status == 200 and bool(hits) and took <= slo_search_s
        check("search", ok, f"HTTP {status}, {len(hits)} results"
              + (f", {hits[0].get('citation')}" if hits else "")
              + (f", slower than {slo_search_s:g} s" if took > slo_search_s else ""), took)
    if (r := attempt("home page", "/")) is not None:
        status, body, took = r
        check("home page", status == 200 and isinstance(body, str) and "<html" in body.lower(),
              f"HTTP {status}", took)
    return checks


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bdrag probe", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="base URL of the service")
    ap.add_argument("--canary", default=CANARY, help="a search that must return a section")
    ap.add_argument("--max-index-age-days", type=float, default=0, help="0 = do not check")
    ap.add_argument("--slo-search-s", type=float, default=5.0)
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--json-out")
    args = ap.parse_args(argv)
    checks = run(args.url, args.canary, args.max_index_age_days, args.slo_search_s, args.timeout)
    for c in checks:
        ms = f" ({c['ms']} ms)" if c["ms"] is not None else ""
        print(f"{'✅' if c['ok'] else '❌'} {c['check']}: {c['detail']}{ms}")
    failed = [c for c in checks if not c["ok"]]
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"url": args.url, "ok": not failed, "checks": checks,
                       "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f,
                      ensure_ascii=False, indent=2)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
