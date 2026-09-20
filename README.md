# bd-legal-rag — Phase 1: Ingestion

A bilingual (Bangla + English) RAG assistant for Bangladeshi law.
This phase turns the Laws of Bangladesh website (bdlaws.minlaw.gov.bd) into clean,
structured, retrieval-ready chunks.

```
index page ──► act pages ──► section pages ──► parse ──► chunk ──► data/processed/*.jsonl
               (TOC: chapters + section links)
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m unittest discover -s tests -v                # 10 tests, should all pass

# 1) One act first — look at the output before scaling up
python scripts/ingest.py --act-ids 1037 --show 3       # Insurance Act, 2010

# 2) A starter corpus
python scripts/ingest.py --year-from 2000 --limit 30 --show 5
```

The first run downloads pages at 1 request/second and caches them in `data/raw/`.
Every later run re-parses from the cache, so it takes seconds and doesn't touch the server.

## Output (`data/processed/`)

| File | One line per | Used for |
|---|---|---|
| `acts.jsonl` | act: title, act number, date, year, language, repealed flag, table of contents | filters, act-level questions |
| `sections.jsonl` | section: clean text + amendment footnotes | evaluation labels, debugging |
| `chunks.jsonl` | chunk: `text` (to embed), `body` (to show/cite), `metadata` | **Phase 2 input** |
| `stats.json` | run | quick check on parser quality |

An example chunk:

```json
{
  "chunk_id": "1037-38212-1",
  "text": "বীমা আইন, ২০১০ > প্রথম অধ্যায় - প্রারম্ভিক > ধারা ১: সংক্ষিপ্ত শিরোনাম ও প্রবর্তন\n\n(১) এই আইন ...",
  "body": "(১) এই আইন ...",
  "metadata": {"type": "section", "act_year": 2010, "language": "bn", "section_number_ascii": "1",
               "refs": [], "amended": false, "part": 1, "n_parts": 1, "url": "..."}
}
```

## Design decisions (and interview talking points)

1. **Chunk by legal structure, not by token count.** A section is the unit people cite
   ("ধারা ৩০২"), so it is the unit we retrieve. Fixed 500-token windows would cut clauses
   in half and mix unrelated sections.
2. **Long sections are split at clause boundaries** — `(১)`, `(ক)`, `(a)` — and each later
   part repeats the lead-in ("In this Act, unless the context otherwise requires—"),
   which gives meaning to the clauses that follow.
3. **Context header in every chunk.** `Act > Chapter > Section: title` is prepended to
   the embedded text, so a chunk that only says "(2) The fine shall not exceed..." still
   matches a question about *that* act. `body` stays clean for citations.
4. **An overview chunk per act** (preamble + table of contents) answers "What does the
   Insurance Act cover?", which no single section can answer.
5. **Metadata for later phases:** `language` (filters, per-language evaluation),
   `repealed` (don't cite dead law), `refs` (cross-references to follow in multi-hop
   retrieval, Phase 6), `amended` + `footnotes` (surface amendment history).
6. **Unicode normalization.** Bangla has two encodings of য়/ড়/ঢ়. Text *and* regexes
   are NFC-normalized, or matching fails silently.
7. **Selectors don't depend on CSS class names.** The parser uses URL patterns and
   document order, and finds the section body as the tightest block holding ≥80% of the
   page's non-link text. That survives cosmetic changes to the site.
8. **Polite and reproducible.** A rate limit, retries with backoff, an honest User-Agent
   (put your email in `fetch.py`), and a raw-HTML cache.

## Checking the output (do this)

After each run, look at `stats.json`:

- `sections_empty` should be ~0. If not, open that page in `data/raw/` and see why.
- `acts_without_sections` > 0 means those TOCs didn't parse.
- `chunk_chars.max` should be ≤ `--max-chars`.
- Read 10–20 random chunks with `--show 20`. Most parser bugs are obvious once you look.

Then copy 2–3 **real** pages from `data/raw/` into `tests/fixtures/` and add tests for
them. The current fixtures are synthetic pages built to match the site's observed structure.

## Known limitations / TODO

- **Schedules (তফসিল) and forms** are not linked as sections and are skipped for now.
- **Repealed detection** is a text heuristic. Verify it on a few known repealed acts.
- **Footnote detection** takes trailing lines that start with a number and mention
  substituted/inserted/omitted (প্রতিস্থাপিত/সন্নিবেশিত/বিলুপ্ত). Check it against real pages.
- **Tables inside sections** are flattened to text.

## Next: Phase 2

Embed `chunks.jsonl` (start with `BAAI/bge-m3`), load it into Qdrant, and build the naive
baseline: retrieve top-5 chunks, prompt the model, answer with citations.
