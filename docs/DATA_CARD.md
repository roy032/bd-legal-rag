# Data card — Bangladeshi statutes corpus

## What this is
Text of Acts of Bangladesh, scraped from the Ministry of Law's *Laws of
Bangladesh* site (bdlaws.minlaw.gov.bd), parsed into Act → Chapter → Section and
chunked for retrieval. It is the corpus behind this project's question
answering, and the evaluation set is labelled against it.

## Provenance and terms
- **Source:** bdlaws.minlaw.gov.bd, the official publication of Bangladeshi legislation.
- **Nature:** legislation — public law, published by the state for public use.
- **Collection:** `scripts/ingest.py`, one request per second, an identifying
  User-Agent (put your own contact in `src/ingest/fetch.py`), every page cached
  locally so it is fetched once. Nothing is re-published; the tool stores text
  for retrieval and always links back to the official page.
- **Licence:** this repository's MIT licence covers the code only. The statutory
  text is not the author's to license. Check the site's terms before
  redistributing the scraped corpus, and prefer sharing the scraper over the data.

## Contents (fill in from your run's `stats.json`)
| Field | Value |
|---|---|
| Acts | — |
| Sections | — |
| Chunks | — |
| Languages | Bangla / English / mixed — |
| Date range | — |
| Snapshot taken | — |

## Structure
Each chunk carries: act id, act title, act number, year, language, repealed flag,
chapter, section id and number, section title, part/n_parts, cross-references to
other sections (`refs`) and other acts (`act_refs`), amendment footnotes, source
URL, character length.

## Known gaps and biases
- **Schedules (তফসিল), forms and appendices are not parsed.** Fee tables and
  prescribed forms are therefore missing, and people ask about exactly those.
- **The text is the site's consolidated version.** Amendments are already
  applied by the site; amendment footnotes are kept per section (matched by
  their markers) but not tied to the exact clause they changed. See ADR 0008.
- **Point-in-time law is not modelled**: there is one version, "as published now".
- **Repealed acts are skipped at ingest by default** (`--include-repealed` keeps
  them, flagged with the site's repeal note and down-weighted in retrieval).
- **Legacy font-conversion errors.** Many Bangla pages were converted from the
  SutonnyMJ font and contain broken conjuncts (e.g. ক্ষ written as "ত্মগ").
  `fix_legacy_bangla` repairs the patterns found in the corpus; rarer ones remain.
- **Older acts are in English, newer ones in Bangla**, so a language filter is
  also, accidentally, a date filter. Report per-language results with that in mind.
- **No case law, rules (বিধিমালা), SROs or gazette notifications.** Many practical
  questions are answered by those, not by the parent Act.
- **Scanned-image acts are absent** — no OCR step exists.
- **Tables inside sections are flattened** to text and read poorly.

## Appropriate use
Research and information retrieval over public legislation, with citations back
to the official text. **Not** a source of legal advice, and not a substitute for
checking the official page — which every answer links to.

## Maintenance
Re-run the scraper to refresh; the cache makes it cheap. `stats.json` is the
health check: a sudden change in section counts means the site's markup changed
and the parser needs attention.
