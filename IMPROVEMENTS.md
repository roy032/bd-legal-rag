# Known limitations and next steps

What is still open in this project. What has already been fixed is recorded in [IMPLEMENTED.md](IMPLEMENTED.md).

## Limitations

- **Qdrant has only run in embedded mode.** `tests/test_qdrant.py` checks top-k and scores against `NumpyStore` with Qdrant's local mode, which searches exactly. A Qdrant server uses an HNSW index, so its recall against the exact store still needs measuring on the real index.
- **New retrieval options are not yet measured on the full corpus.** `--translate`, `--rerank-top 20` with `--rerank-precision`, `--rewrite colloquial`, the `TOPIC_ACTS` glossary and the `[REQUESTED SECTION]` prompt are tested offline only. `RUN_UPGRADES.bat` (`bdrag measure-upgrades`) measures them on the laptop's index and writes `results/UPGRADES.md`.
- **int8 reranking changes the order slightly.** On 20 Bangla/English excerpts its top 5 matched fp32 in 4 of 5 places (Spearman 0.91-0.97); bf16 is the better choice where the CPU supports it natively. Measure int8 on the eval set before serving it.
- **Contextual chunk headers are not re-run.** `bdrag contextualize` could help the "many acts share the vocabulary" ranking misses, but it needs a full re-embed; do it after the measurements above.
- **Evaluation set size.** 86 held-out questions is enough to compare configurations, not enough to claim tight confidence intervals. 16 more are drafted in `data/eval/eval_v2_draft.jsonl` and await review (`data/eval/REVIEW_V2.md`).
- **Judge model.** Answer correctness is judged by an LLM. The judge is required to differ from the answering model, but it has not been calibrated against human labels. (Earlier answers files lack the judge's verdicts, so calibration needs a fresh `bdrag e2e` run.)
- **Corpus scope.** Answers come only from the 1,354 acts ingested. Rules, SROs, gazette notifications and case law are not in the corpus, so questions that depend on them get a partial answer or NOT_FOUND.

## Next steps

1. Run `RUN_UPGRADES.bat` on the laptop; serve `--translate` and the reranker only if they win on `results/UPGRADES.md`.
2. Review the drafted v2 questions and the `sr02` gold label.
3. Grade 40 answers with `bdrag calibrate-judge ... --export grade.csv` (judge: `--judge-provider groq`) to get the judge's kappa.
4. Measure a Qdrant server's HNSW recall against `NumpyStore` on the real index.
