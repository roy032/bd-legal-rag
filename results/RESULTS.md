## Results

Measured on the full corpus (43,966 chunks) with the 96-question evaluation set in `data/eval/eval.jsonl`; 95% bootstrap intervals, paired tests against the dense baseline. Regenerate everything with `python scripts/finish.py`.

### Retrieval ablation

| run | pipeline | k | recall@5 | recall@10 | mrr | ndcg@5 | p95 latency (ms) |
|---|---|---|---|---|---|---|---|
| bm25 | bm25 | 10 | 0.372 [0.27–0.48] | 0.436 [0.33–0.55] | 0.270 [0.19–0.36] | 0.287 [0.21–0.38] | 101 |
| dense | dense | 10 | 0.808 [0.72–0.88] | 0.884 [0.81–0.95] | 0.695 [0.61–0.78] | 0.706 [0.62–0.78] | 457 |
| hybrid | hybrid | 10 | 0.669 [0.57–0.77] | 0.756 [0.66–0.84] | 0.520 [0.43–0.61] | 0.542 [0.45–0.63] | 504 |
| +refs | hybrid +refs | 10 | 0.669 [0.58–0.77] | 0.756 [0.67–0.84] | 0.520 [0.43–0.61] | 0.541 [0.45–0.63] | 583 |
| +dedupe | hybrid +refs +dedupe2 | 10 | 0.669 [0.58–0.77] | 0.756 [0.67–0.84] | 0.520 [0.43–0.61] | 0.541 [0.45–0.63] | 608 |
| +synonyms | hybrid +refs +dedupe2 +syn +translit | 10 | 0.674 [0.58–0.77] | 0.773 [0.69–0.85] | 0.505 [0.41–0.60] | 0.532 [0.44–0.62] | 627 |
| +route | hybrid +refs +dedupe2 +syn +translit +route | 10 | 0.686 [0.59–0.78] | 0.791 [0.71–0.87] | 0.511 [0.42–0.60] | 0.539 [0.44–0.63] | 630 |
| +resolve | hybrid +refs +dedupe2 +syn +translit +route +resolve | 10 | 0.733 [0.64–0.83] | 0.837 [0.76–0.91] | 0.567 [0.48–0.65] | 0.593 [0.51–0.68] | 829 |
| +in-force | hybrid +refs +dedupe2 +syn +translit +route +resolve +in-force | 10 | 0.733 [0.64–0.83] | 0.837 [0.76–0.91] | 0.567 [0.48–0.65] | 0.593 [0.51–0.68] | 884 |
| +rerank | hybrid +refs +rerank(cross) +dedupe2 +syn +translit +route +resolve +in-force | 10 | 0.878 [0.80–0.94] | 0.948 [0.90–0.99] | 0.749 [0.67–0.82] | 0.770 [0.70–0.84] | 109172 |

```
Paired comparison on recall@5 vs 'dense' (same questions, 2000 resamples):
  bm25                       -0.436 [-0.547, -0.326]  worse  (n=86)
  hybrid                     -0.140 [-0.233, -0.041]  worse  (n=86)
  +refs                      -0.140 [-0.233, -0.041]  worse  (n=86)
  +dedupe                    -0.140 [-0.233, -0.041]  worse  (n=86)
  +synonyms                  -0.134 [-0.244, -0.023]  worse  (n=86)
  +route                     -0.122 [-0.233, -0.017]  worse  (n=86)
  +resolve                   -0.076 [-0.192, +0.035]  within noise  (n=86)
  +in-force                  -0.076 [-0.192, +0.035]  within noise  (n=86)
  +rerank                    +0.070 [-0.017, +0.157]  within noise  (n=86)
```

### Served configuration

Chosen on the tuning split (recall@5: dense 0.773, hybrid-routed 0.568, hybrid-tuned 0.773), then measured once on the test set: **dense**.

| recall@5 | recall@10 | MRR |
|---|---|---|
| 0.849 [0.77–0.91] | 0.901 [0.83–0.96] | 0.772 [0.69–0.85] |

`--mode dense --expand-refs --synonyms --transliterate --resolve-refs --boost-in-force --max-parts-per-section 2`

### Fusion weights (tuned on the separate 24-question tuning split)

```json
{
 "dense_weight": 1.0,
 "bm25_weight": 0.5,
 "rrf_k": 10,
 "candidates": 50,
 "recall@5": 0.7727
}
```

### Abstention threshold (`calibrate_guard.py`, served configuration)

```
 min_score  answer_rate  gold_kept  correct_abstain   score
    0.0321         1.00       0.86             0.00   0.430
    0.0989         0.94       0.83             0.00   0.413
    0.1657         0.94       0.83             0.00   0.413
    0.2325         0.94       0.83             0.00   0.413
    0.2993         0.94       0.83             0.00   0.413
    0.3661         0.94       0.83             0.00   0.413
    0.4329         0.94       0.83             0.00   0.413
    0.4997         0.94       0.83             0.10   0.463
    0.5666         0.92       0.80             0.40   0.601
    0.6334         0.69       0.62             1.00   0.808
    0.7002         0.17       0.17             1.00   0.587
    0.7670         0.01       0.01             1.00   0.506
```

No threshold fits both goals: refusing most unanswerable questions also refuses a large share of answerable ones, because the top dense score of an off-topic question is often as high as that of a hard real one. The service therefore ships without a score threshold (`BDRAG_MIN_SCORE` unset) and relies on the answer prompt, which tells the model to refuse when the excerpts do not answer, and on the citation checks.

### End to end (answers by a local Ollama model, judged by llama3.1:8b, on a Kaggle T4)

Same retrieval, same five excerpts per question, two answering models fixed in advance.

| | qwen2.5:7b | qwen2.5:14b |
|---|---|---|
| Correct (judge vs. reference answer) | 0.535 [0.45–0.62] | 0.709 [0.64–0.77] |
| Faithful to the cited excerpts (judge) | 0.562 [0.46–0.67] | 0.406 [0.31–0.51] |
| Cites a gold section | 0.698 [0.60–0.79] | 0.767 [0.69–0.85] |
| Citations point at retrieved excerpts | 0.990 [0.97–1.00] | 1.000 [1.00–1.00] |
| Refuses exactly when it should | 0.865 [0.79–0.93] | 0.906 [0.84–0.96] |

The judge is itself an 8B model: its scores are indicative, and the deterministic rows (citations, refusals) are the ones to trust most.
