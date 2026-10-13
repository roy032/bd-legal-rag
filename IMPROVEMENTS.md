# Known limitations and next steps

What is still open in this project. What has already been fixed is recorded in [IMPLEMENTED.md](IMPLEMENTED.md).

## Limitations

- **Qdrant has only run in embedded mode.** `tests/test_qdrant.py` checks top-k and scores against `NumpyStore` with Qdrant's local mode, which searches exactly. A Qdrant server uses an HNSW index, so its recall against the exact store still needs measuring on the real index.
- **New retrieval options are not yet measured on the full corpus.** `--rerank-top`, `--rewrite colloquial` and the `[REQUESTED SECTION]` prompt (answer-system/v4) are tested offline; they need a run with bge-m3, a reranker and an answering model to say whether they move the numbers. The ablation has a `dense+rerank@20` row for this.
- **Evaluation set size.** 86 held-out questions is enough to compare configurations, not enough to claim tight confidence intervals. 16 more are drafted in `data/eval/eval_v2_draft.jsonl` and await review (`data/eval/REVIEW_V2.md`).
- **Judge model.** Answer correctness is judged by an LLM. The judge is required to differ from the answering model, but it has not been calibrated against human labels.
- **Corpus scope.** Coverage depends on the acts ingested (1,354); the Road Transport Act 2018, for example, is not in the corpus.

## Next steps

1. Run `bdrag ablate --only dense dense+rerank@20` and `bdrag e2e` with the v4 prompt on the full index, and update the README tables.
2. Review the drafted v2 questions and the `sr02` gold label.
3. Grade 20 answers with `bdrag calibrate-judge` to get the judge's kappa.
4. Measure a Qdrant server's HNSW recall against `NumpyStore` on the real index.
