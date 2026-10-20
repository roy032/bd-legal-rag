#!/usr/bin/env python
"""Load test with nothing but the standard library.

Turns "it feels fast" into numbers you can put in the README: throughput, p50,
p95, p99 and the error rate at a given concurrency. Point it at /search first —
that is the path where your own code is the bottleneck. /ask is dominated by
the model provider and mostly measures them, not you.

  python scripts/loadtest.py --url http://localhost:8000/search --concurrency 8 --requests 200
"""
from __future__ import annotations

import argparse
import json
import statistics
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


if __name__ == "__main__":
    main()
