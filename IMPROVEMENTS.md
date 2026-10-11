# Known limitations and next steps

What is still open in this project. What has already been fixed is recorded in [IMPLEMENTED.md](IMPLEMENTED.md).

## Limitations

- **`QdrantStore` is unverified.** I have not run it against a live Qdrant server. The default `NumpyStore` is what the tests and the reported numbers use.
- **Scripts still adjust `sys.path`.** The library is an installable package, but the scripts in `scripts/` still insert `src/` into the path so they run without installing. Moving them to console entry points is the clean fix.
- **Evaluation set size.** 86 held-out questions is enough to compare configurations, not enough to claim tight confidence intervals.
- **Judge model.** Answer correctness is judged by an LLM. The judge is required to differ from the answering model, but it has not been calibrated against many human labels.
- **Corpus scope.** Coverage depends on the acts I ingested, so questions about other acts will not be answered well.

## Next steps

1. Run `QdrantStore` against a local Qdrant and compare its top-k against `NumpyStore` on the same queries.
2. Turn the scripts into entry points and remove the path adjustment.
3. Grow the evaluation set and add a human-labelled sample to calibrate the judge.
