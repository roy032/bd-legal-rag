#!/usr/bin/env python
"""Phase 1 CLI: download -> parse -> chunk -> JSONL.

Examples
  # Try it on one act (Insurance Act, 2010)
  python scripts/ingest.py --act-ids 1037 --show 3

  # The whole corpus (every act in the chronological index). Hours at a polite
  # delay; safe to stop and re-run — pages already in data/raw are not refetched.
  python scripts/ingest.py --delay 0.5

  # Shrink an existing page cache ~5x (pages are mostly navigation boilerplate)
  python scripts/ingest.py --compact-cache

  # Keep the corpus current: only new acts + acts that new amendments touch
  python scripts/ingest.py --update

  # Re-parse everything already downloaded, without touching the site
  python scripts/ingest.py --offline

  # Re-chunk with a different size without re-downloading anything
  python scripts/ingest.py --act-ids 1037 11 --max-chars 1200 --offline
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ingest.chunk import act_overview_chunk, chunk_section  # noqa: E402
from ingest.fetch import BASE_URL, Fetcher, compact_cache  # noqa: E402
from ingest.parse import parse_act, parse_index, parse_section  # noqa: E402
from ingest.textutils import extract_year  # noqa: E402

INDEX_URL = f"{BASE_URL}/laws-of-bangladesh-chronological-index.html"
# The index marks repealed acts in the title itself: "... Act, 1980 [Repealed]", "... [রহিত]".
REPEALED_IN_INDEX = re.compile(r"\[\s*(?:রহিত|Repealed)\s*\]", re.I)
AMENDING_TITLE = re.compile(r"সংশোধন|রহিতকরণ|amendment|repeal", re.I)
MANIFEST = "manifest.json"


def plan_update(fetcher: Fetcher, targets: list[tuple[int, str | None]], out: Path) -> tuple[set[int], set[int]]:
    """Which acts to (re)download in --update mode.

    new      : in the site's index but not in the last run's manifest.
    refresh  : older acts that a NEW amending act links to. bdlaws edits the
               amended sections in place, so these are the only old pages that
               can have changed — everything else is served from the cache.
    """
    manifest_path = out / MANIFEST
    known: set[int] = set()
    if manifest_path.exists():
        known = {int(k) for k in json.loads(manifest_path.read_text(encoding="utf-8"))["acts"]}
    selected = {aid for aid, _ in targets}
    new = {aid for aid, _ in targets if aid not in known} if known else set()
    refresh: set[int] = set()
    for aid, title in targets:
        if aid not in new or not AMENDING_TITLE.search(title or ""):
            continue
        try:
            act = parse_act(fetcher.get(f"{BASE_URL}/act-{aid}.html"), aid)
            for ref in act.sections:
                sec = parse_section(fetcher.get(ref.url), ref, act)
                refresh.update(r["act_id"] for r in sec.act_refs)
        except Exception as e:  # an unreachable amending act must not stop the update
            log.warning("could not read amending act %s: %s", aid, e)
    refresh &= selected - new
    return new, refresh
log = logging.getLogger("ingest")


def select_acts(fetcher: Fetcher, args) -> list[tuple[int, str | None]]:
    if args.act_ids:
        return [(i, None) for i in args.act_ids]
    refs = parse_index(fetcher.get(INDEX_URL, refresh=args.update))
    log.info("index lists %d acts", len(refs))
    sel = []
    for r in refs:
        y = extract_year(r.title)
        if args.match and not re.search(args.match, r.title, re.I):
            continue
        if args.year_from and (y is None or y < args.year_from):
            continue
        if args.year_to and (y is None or y > args.year_to):
            continue
        if not args.include_repealed and REPEALED_IN_INDEX.search(r.title):
            continue
        sel.append(r)
    if args.limit:
        sel = sel[: args.limit]
    return [(r.act_id, r.title) for r in sel]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--act-ids", type=int, nargs="*", help="specific act ids (the N in /act-N.html)")
    ap.add_argument("--match", help="regex the act title must match (e.g. 'Penal|দণ্ড')")
    ap.add_argument("--year-from", type=int)
    ap.add_argument("--year-to", type=int)
    ap.add_argument("--limit", type=int, help="max number of acts")
    ap.add_argument("--max-chars", type=int, default=1800, help="max chars per chunk body")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (be polite)")
    ap.add_argument("--include-repealed", action="store_true",
                    help="also fetch acts the index marks [Repealed]/[রহিত] (skipped by default)")
    ap.add_argument("--no-compress", action="store_true",
                    help="store downloaded pages as plain .html instead of .html.gz")
    ap.add_argument("--compact-cache", action="store_true",
                    help="gzip every plain .html page already in the cache, then exit")
    ap.add_argument("--update", action="store_true",
                    help="re-read the site's index; download only new acts and the acts new "
                         "amending acts point at; everything else comes from the cache")
    ap.add_argument("--offline", action="store_true",
                    help="use only pages already in the cache; skip anything not downloaded")
    ap.add_argument("--out", default="data/processed")
    ap.add_argument("--cache", default="data/raw")
    ap.add_argument("--show", type=int, default=0, help="print N random chunks at the end")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    if args.compact_cache:
        n, before, after = compact_cache(args.cache)
        print(f"compressed {n} pages: {before / 1e6:.1f} MB -> {after / 1e6:.1f} MB")
        return
    fetcher = Fetcher(cache_dir=args.cache, delay=args.delay, offline=args.offline,
                      compress=not args.no_compress)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    if args.update and args.offline:
        sys.exit("--update needs the network; drop --offline")
    targets = select_acts(fetcher, args)
    log.info("processing %d acts%s", len(targets), " (offline)" if args.offline else "")
    refresh: set[int] = set()
    if args.update:
        new, refresh = plan_update(fetcher, targets, out)
        log.info("update: %d new act(s), %d amended act(s) to re-download: %s",
                 len(new), len(refresh), sorted(refresh)[:20])

    stats: Counter = Counter()
    langs: Counter = Counter()
    lengths: list[int] = []
    sample: list = []
    failures: list[dict] = []
    t0 = time.time()
    with open(out / "acts.jsonl", "w", encoding="utf-8") as fa, \
         open(out / "sections.jsonl", "w", encoding="utf-8") as fs, \
         open(out / "chunks.jsonl", "w", encoding="utf-8") as fc:
        for n, (act_id, _) in enumerate(targets, 1):
            try:
                act = parse_act(fetcher.get(f"{BASE_URL}/act-{act_id}.html",
                                            refresh=act_id in refresh), act_id)
            except Exception as e:  # keep going; one bad page shouldn't kill the run
                (log.debug if args.offline else log.error)("act %s failed: %s", act_id, e)
                stats["acts_failed"] += 1
                failures.append({"act_id": act_id, "url": f"{BASE_URL}/act-{act_id}.html",
                                 "error": f"{type(e).__name__}: {e}"})
                continue
            if n % 25 == 0 or n == len(targets):
                rate = n / max(time.time() - t0, 1e-9)
                log.info("[%d/%d] %s — %d sections%s | %.2f acts/s, eta %.0f min", n, len(targets),
                         act.title, len(act.sections), " (REPEALED)" if act.repealed else "",
                         rate, (len(targets) - n) / max(rate, 1e-9) / 60)
            if not act.sections:
                stats["acts_without_sections"] += 1
            fa.write(json.dumps(asdict(act), ensure_ascii=False) + "\n")
            stats["acts"] += 1
            stats["acts_repealed"] += act.repealed
            langs[act.language] += 1

            chunks = [act_overview_chunk(act)]
            for ref in act.sections:
                try:
                    sec = parse_section(fetcher.get(ref.url, refresh=act_id in refresh), ref, act)
                except Exception as e:
                    stats["sections_failed"] += 1
                    failures.append({"act_id": act_id, "url": ref.url,
                                     "error": f"{type(e).__name__}: {e}"})
                    continue
                stats["sections"] += 1
                if not sec.text:
                    stats["sections_empty"] += 1
                    log.debug("  empty text: %s", ref.url)
                stats["sections_amended"] += bool(sec.footnotes)
                stats["sections_omitted"] += sec.omitted
                fs.write(json.dumps(asdict(sec), ensure_ascii=False) + "\n")
                chunks.extend(chunk_section(act, sec, max_chars=args.max_chars))
            for c in chunks:
                fc.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
                lengths.append(c.metadata["char_len"])
                stats["chunks"] += 1
                stats["chunks_continuation"] += c.metadata.get("part", 1) > 1
            if len(sample) < 2000:
                sample.extend(chunks[:3])

    (out / MANIFEST).write_text(json.dumps({
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "acts": {str(aid): title for aid, title in targets},
        "refreshed": sorted(refresh),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(out / "failures.jsonl", "w", encoding="utf-8") as ff:
        for row in failures:
            ff.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Report — look at these numbers every time you change the parser.
    lengths.sort()
    report = {
        **stats,
        "languages": dict(langs),
        "chunk_chars": {
            "min": lengths[0] if lengths else 0,
            "median": lengths[len(lengths) // 2] if lengths else 0,
            "p95": lengths[int(len(lengths) * 0.95)] if lengths else 0,
            "max": lengths[-1] if lengths else 0,
        },
        "offline": args.offline,
        "seconds": round(time.time() - t0, 1),
    }
    (out / "stats.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failures:
        print(f"{len(failures)} page(s) failed — see {out / 'failures.jsonl'}; re-run to retry them.")

    for c in random.sample(sample, min(args.show, len(sample))):
        print("\n" + "=" * 80 + f"\n{c.chunk_id}  {json.dumps({k: c.metadata[k] for k in ('type', 'url')}, ensure_ascii=False)}\n" + "-" * 80)
        print(c.text[:1200])


if __name__ == "__main__":
    main()
