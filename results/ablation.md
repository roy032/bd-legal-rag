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
