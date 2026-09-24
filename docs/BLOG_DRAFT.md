# Retrieval for Bangla legal text: what actually worked

*(Draft. Replace every "—" with your own numbers before publishing; the
argument only works if the figures are real.)*

## The problem

Bangladesh's statutes are published as public web pages, and they are almost
unusable if you do not already know where to look. You need the section number
to find the section. People, on the other hand, arrive with "কত দিনের নোটিশ দিতে
হয়?" — and often they type it as `kotodin er notish dite hoy`.

I built a bilingual retrieval system over the Acts and measured every step.
This is what moved the numbers and what did not.

## What the corpus is like

— sections across — acts, roughly — in Bangla and — in English, because
legislation before 1987 was written in English and after it in Bangla. That
single fact shapes everything: a language filter is also a date filter, and any
result you report as an average hides two very different populations.

## Baseline

Naive RAG: fixed-size chunks, one multilingual embedding model, top-5, no
evaluation set. It demos beautifully. I had no idea whether it was any good.

## Building the measuring stick first

— hand-written questions, labelled with the sections that answer them, split
across single-section, multi-hop, exact-reference, paraphrase and unanswerable.
Two decisions made it durable:

1. **Labels point at sections, not chunks.** Every later experiment re-chunks the
   corpus; chunk-level labels would have died on the first one.
2. **Unanswerable questions are ~10% of the set**, because a system that never
   refuses is a system that hallucinates and no metric based only on answerable
   questions will tell you.

Writing them by hand mattered more than I expected. My first attempt reused the
sections' own vocabulary; retrieval scored — and meant nothing.

## What helped

| Change | recall@5 | Note |
|---|---|---|
| Dense only (baseline) | — | |
| + BM25, fused with RRF | — | biggest gain on exact-reference questions |
| + section-number expansion | — | free; only fires when a number is present |
| + cross-encoder rerank | — | biggest single gain, +— ms |
| + romanised-Bangla variant | — | measured on the romanised slice only |

## What did not

— (Be specific and keep this section. "Multi-query rewriting cost a call per
question and landed within noise" is more convincing than any win above.)

## The Bangla-specific parts

- **Digit folding.** ৩০২ and 302 must be the same token. One line; large effect
  on exact-reference questions.
- **Suffix stripping is a coin flip.** Bangla is agglutinative, so ধারায়/ধারার
  should reach ধারা — but a crude stripper also turns উচ্ছেদের into উচ্ছে.
  Measure before enabling.
- **Romanised input is not an edge case.** —% of my test queries typed by friends
  were Banglish. Neither embeddings nor BM25 see it without help.

## Grounding, not just citing

Requiring a citation per sentence is easy to check and easy to satisfy
dishonestly: a model can cite excerpt [2] for something [2] does not say. Adding
per-claim entailment moved the honest-sounding failures from — to —.

The failure that worries me most in legal text is the fabricated quotation: it
looks exactly like the real thing. Every quoted span is now checked verbatim
against the cited excerpt.

## What I would do next

—

## Try it

Demo: — · Code: — · The question set is published as a dataset, because there is
very little Bangla legal retrieval evaluation data.
