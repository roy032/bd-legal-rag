# Launch audit

Written 2026-10-22 against `main` = `141ef03` (1.1.0, PRs #9, #10 and #12). The question
asked: is the app ready to put in front of the public, and what would a strong product
team still fix? Constraint unchanged: free or local models only, no Anthropic API.

## Short answer

The engineering is ahead of the product. Reliability, observability, CI gates, container
hardening, accessibility and personal-data redaction are at a level most launched
products never reach. What was missing was the things a visitor notices on day one, and
the evidence that the answers are right. This round fixes three visitor-facing gaps.
The biggest remaining risks need people, a laptop or hosting, not code.

## What is strong already

Cited answers with guardrails and a repair pass, a topic table that pins the governing
sections, labelled general guidance with the 16430 legal-aid line when the law text does
not cover a question, graceful degradation to retrieval, admission control, a circuit
breaker, single-flight, exact and paraphrase caches, probes, Prometheus histograms, JSON
logs, OpenTelemetry, a quality gate against a committed baseline, a 52-probe red-team
set, axe accessibility checks in CI, a read-only non-root image with an SBOM, and a
bilingual UI with share, print, copy, history and feedback.

## Gaps, in order of how much they would hurt a launch

| # | Gap | Severity | Status |
|---|---|---|---|
| 1 | **No human check of answer correctness.** Every quality number comes from retrieval gold labels or one small judge model. Nobody qualified has read a sample of answers. For a legal product this is the main risk | high | open: needs a Bangladeshi lawyer or law student to grade ~50 answers with a rubric (correct law, correct section, safe advice) |
| 2 | **Share links died on every restart.** Answers lived in a 500-entry dict, so a link pasted into Messenger or WhatsApp broke after a deploy or a busy hour | high | **fixed in this round** |
| 3 | **No follow-up questions.** `rag/chat.py` existed but the service and page never used it; "and the fine?" retrieved nothing | high | **fixed in this round** |
| 4 | **No privacy policy or terms**, and the query log held raw IP addresses | high for a public launch | **fixed in this round** (page needs your review) |
| 5 | **Answers take 20 to 115 s on a laptop CPU.** Caches help repeat questions only | high | open: host the model on a machine with a GPU, or offer the free hosted models already supported (Groq, Gemini) with the consent notice the page already shows |
| 6 | **The index is a snapshot with no refresh schedule.** Parliament amends acts; `BDRAG_VERIFY_LIVE` is opt-in and per answer | medium | open: monthly re-ingest job and the index date on the page |
| 7 | **Statutes only.** No case law, rules, SROs or gazette notifications, which is where much practical law lives | medium | open: state the scope on the page; add rules/SROs if bdlaws exposes them |
| 8 | **One laptop is the whole production.** No backup of `data/answers.sqlite3`, no uptime alert, no domain | medium | open: HF Space with persistent storage or a small VPS, a nightly copy of the data directory, a free uptime monitor |
| 9 | **Query and feedback logs grow forever** | low | open: rotate monthly; the privacy page only promises retention for shared answers |
| 10 | **Known retrieval misses** (English question to a Bangla-only act; wording shared across many acts) | medium | open: laptop items #1 and #8 of [the last plan](next-upgrades-2026-10-21.md) |

## Done in this round

- **Shared links that last.** Answers go to SQLite (`BDRAG_ANSWERS_DB`), deleted after
  `BDRAG_ANSWER_DAYS` (90). A shared link's preview shows the question, carries
  `noindex`, and the page shows the date the answer was given.
- **Follow-up questions.** A Follow up button; the server rewrites the follow-up with
  the turns it stored itself (a request cannot invent history), retrieves with the
  rewrite, and shows "Searched as" so a wrong rewrite is visible.
- **Privacy and terms** at `/privacy`, in English and Bangla; `robots.txt`; a web app
  manifest so phones can add it to the home screen; salted client hashes in the query
  log instead of IP addresses.

## Next, in order

| # | Idea | Effort | Needs | Why |
|---|---|---|---|---|
| 1 | Lawyer review of 50 answers, graded with a fixed rubric, results committed | M | a person | the only credible evidence the answers are right |
| 2 | Check follow-up rewrites with gemma4:e4b on 20 real two-turn conversations | S | laptop | the rewrite prompt is untested on the small local model; a bad rewrite is shown to the user but still costs an answer |
| 3 | Hosting: GPU or free hosted model, a domain, HTTPS, backups, uptime alert | M | money or accounts | latency and availability are what visitors judge first |
| 4 | Monthly re-ingest with the index date shown on the page | S | laptop | stale law is a legal-safety problem |
| 5 | Bangla voice input (browser speech recognition, `bn-BD`) | S | no | many visitors are more comfortable speaking than typing Bangla |
| 6 | "Questions we could not answer" report from the query log, feeding the topic table | S | no | turns refusals into the next content work |
| 7 | Upload a notice or contract and ask about it (local OCR already exists) | L | no | the most common real situation is "I received this paper" |
| 8 | District legal-aid office directory | M | data | 16430 is national; people need the nearest office |

Not recommended now: a service worker for offline use (a cached legal answer that
silently goes stale is worse than an offline notice), accounts, and payment.
