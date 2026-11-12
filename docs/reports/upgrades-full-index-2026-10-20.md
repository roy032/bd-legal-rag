# Translation and the reranker on the full index

Retrieval runs from `RUN_UPGRADES.bat` on the laptop, 2026-10-18 to 2026-10-20, full
corpus (1,354 acts), bge-m3 dense retrieval with the service flags (refs, synonyms,
transliteration, in-force boost, resolve refs), `data/eval/eval.jsonl` (86 answerable,
10 unanswerable), k = 10, CPU only. The checkout was the 1.0 line before the topic table
(PR #5), so these numbers sit beside the topic-table report, not on top of it.

The script stopped after the retrieval runs, so `results/UPGRADES.md` and the
answering-model half (prompt with `[REQUESTED SECTION]`, `--rewrite colloquial`) were
never written. The raw JSON (`results/upg-test-*.json`) stays on the laptop because
`results/*.json` is ignored by git; the numbers below are copied from it.

## Overall

| Run | recall@5 | MRR | hit@1 | nDCG@10 | recall@10 | median s/query | p95 s/query |
|---|---|---|---|---|---|---|---|
| served (baseline) | 0.907 | 0.779 | 0.686 | 0.811 | 0.930 | 0.19 | 0.37 |
| + `--translate` | 0.924 | 0.766 | 0.651 | 0.806 | 0.948 | 54.8 | 91.3 |
| + cross rerank top 20 (`auto` precision) | 0.924 | **0.811** | **0.721** | **0.843** | 0.959 | 26.4 | 38.6 |

All differences are inside the 95% intervals (n = 86; MRR baseline 0.70-0.85).

## By language (recall@5 / MRR)

| Run | Bangla (40) | English (50) | Mixed (6) |
|---|---|---|---|
| served | 0.892 / 0.882 | 0.909 / 0.682 | 1.000 / 0.867 |
| + translate | 0.932 / 0.849 | 0.909 / 0.681 | 1.000 / 0.900 |
| + rerank | 0.932 / 0.834 | 0.909 / 0.770 | 1.000 / 1.000 |

## Per question against the baseline

- **Translate:** recall@5 better on 4, worse on 2 (`rg02`, `sr01` drop out of the top 5); MRR better on 9, worse on 11.
- **Rerank:** recall@5 better on 4, worse on 2 (`pc07`, `ev03`); MRR better on 16, worse on 12. The gain is in English (MRR +0.09) and paraphrases (+0.17); Bangla MRR falls 0.05.

## What this means

- **Do not serve `--translate`.** It costs about 55 s per question on the laptop CPU (an LLM call before retrieval) and lowers MRR and hit@1; the small recall@5 gain is two questions.
- **The reranker is the only option that helped,** mostly on English and paraphrased questions, but at 26 s per query on CPU it is not servable on the laptop. It stays off by default; it is worth turning on only where a GPU (or a CPU with native bf16) brings it under a second or two.
- Still open: the answering-model half of `bdrag measure-upgrades`, and repeating the reranker run on top of the topic table.
