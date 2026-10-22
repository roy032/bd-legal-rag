#!/usr/bin/env python
"""Load test with nothing but the standard library.

Turns "it feels fast" into numbers you can put in the README: throughput, p50,
p95, p99 and the error rate at a given concurrency. Point it at /search first —
that is the path where your own code is the bottleneck. /ask is dominated by
the model provider and mostly measures them, not you.

  python scripts/loadtest.py --url http://localhost:8000/search --concurrency 8 --requests 200

With an SLO it becomes a gate: CI starts the container and fails the build when
p95 or the error rate is over budget.

  python scripts/loadtest.py --slo-p95-ms 300 --max-error-rate 0 --json-out load.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from queue import Queue

QUESTIONS = [
    "হত্যার শাস্তি কী?", "ধারা ৩০২ কী বলে?", "সংজ্ঞা কী?",
    "What is causing death by negligence?", "dhara 2 e ki ache",
    "ভাড়াটিয়া উচ্ছেদের নিয়ম কী?",
]


def worker(url: str, jobs: Queue, results: list, lock: threading.Lock, timeout: float) -> None:
    while True:
        item = jobs.get()
        if item is None:
            return
        body = json.dumps({"question": item, "k": 5}).encode()
        req = urllib.request.Request(url, data=body,
                                     headers={"content-type": "application/json"})
        start = time.perf_counter()
        status = 0
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                r.read()
                status = r.status
        except urllib.error.HTTPError as e:
            status = e.code
        except Exception:
            status = 0
        with lock:
            results.append((time.perf_counter() - start, status))
        jobs.task_done()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8000/search")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--requests", type=int, default=200)
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--slo-p95-ms", type=float, help="fail (exit 1) if p95 latency is above this")
    ap.add_argument("--max-error-rate", type=float,
                    help="fail if more than this share of requests failed (0 = none may fail; "
                         "429s count as failures)")
    ap.add_argument("--json-out", help="also write the numbers to this JSON file")
    args = ap.parse_args()

    jobs: Queue = Queue()
    results: list[tuple[float, int]] = []
    lock = threading.Lock()
    threads = [threading.Thread(target=worker, args=(args.url, jobs, results, lock, args.timeout),
                                daemon=True) for _ in range(args.concurrency)]
    for t in threads:
        t.start()

    start = time.perf_counter()
    for i in range(args.requests):
        jobs.put(QUESTIONS[i % len(QUESTIONS)])
    jobs.join()
    for _ in threads:
        jobs.put(None)
    elapsed = time.perf_counter() - start

    latencies = sorted(r[0] for r in results)
    ok = sum(1 for r in results if 200 <= r[1] < 300)
    limited = sum(1 for r in results if r[1] == 429)

    def pct(p: float) -> float:
        return latencies[min(int(len(latencies) * p), len(latencies) - 1)] if latencies else 0.0

    print(f"url           {args.url}")
    print(f"concurrency   {args.concurrency}")
    print(f"requests      {len(results)} ({ok} ok, {limited} rate-limited, "
          f"{len(results) - ok - limited} failed)")
    print(f"throughput    {len(results) / elapsed:.1f} req/s over {elapsed:.1f}s")
    print(f"latency p50   {pct(0.5) * 1000:.0f} ms")
    print(f"        p95   {pct(0.95) * 1000:.0f} ms")
    print(f"        p99   {pct(0.99) * 1000:.0f} ms")
    print(f"        mean  {statistics.mean(latencies) * 1000:.0f} ms" if latencies else "")
    if limited:
        print("\nRate limiting kicked in — raise BDRAG_RATE_PER_MIN for the test, or lower "
              "--concurrency, otherwise you are measuring the limiter.")

    summary = summarize(results, elapsed)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"url": args.url, "concurrency": args.concurrency, **summary}, f, indent=2)
    breaches = slo_breaches(summary, args.slo_p95_ms, args.max_error_rate)
    for b in breaches:
        print(f"SLO FAILED: {b}")
    if breaches:
        sys.exit(1)
    if args.slo_p95_ms is not None or args.max_error_rate is not None:
        print("SLO met")


def summarize(results: list[tuple[float, int]], elapsed: float) -> dict:
    latencies = sorted(r[0] for r in results)
    n = len(results)
    ok = sum(1 for r in results if 200 <= r[1] < 300)

    def pct(p: float) -> float:
        return latencies[min(int(len(latencies) * p), len(latencies) - 1)] if latencies else 0.0

    return {"requests": n, "ok": ok, "error_rate": round((n - ok) / n, 4) if n else 1.0,
            "throughput_rps": round(n / elapsed, 2) if elapsed else 0.0,
            "p50_ms": round(pct(0.5) * 1000, 1), "p95_ms": round(pct(0.95) * 1000, 1),
            "p99_ms": round(pct(0.99) * 1000, 1)}


def slo_breaches(summary: dict, p95_ms: float | None, max_error_rate: float | None) -> list[str]:
    out = []
    if p95_ms is not None and summary["p95_ms"] > p95_ms:
        out.append(f"p95 {summary['p95_ms']:.0f} ms > {p95_ms:.0f} ms")
    if max_error_rate is not None and summary["error_rate"] > max_error_rate:
        out.append(f"error rate {summary['error_rate']:.2%} > {max_error_rate:.2%}")
    if not summary["requests"]:
        out.append("no requests completed")
    return out


if __name__ == "__main__":
    main()
