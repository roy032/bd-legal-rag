# Reports

Dated, point-in-time write-ups. They describe the repository as it was on the date
given, so pull request numbers and "not yet merged" remarks may be out of date; the
current state is in the main [README](../../README.md) and [CHANGELOG](../../CHANGELOG.md).

| Date | Report | Summary |
|---|---|---|
| 2026-10-16 | [Free answering models](free-llm-run/README.md) | Gemma 4 E4B against Qwen3.5 4B on everyday legal scenarios, full corpus, CPU only; raw outputs alongside |
| 2026-10-17 | [Comparison with Bangladesh-Legal-Chatbot](comparison-bangladesh-legal-chatbot.md) | what a similar open project does, and which ideas were worth taking (OCR, doctor, HF Space) |
| 2026-10-17 | [What to upgrade next](next-upgrades-2026-10-17.md) | the prioritised upgrade plan most of 1.1.0 implemented |
| 2026-10-19 | [Topic table on the full index](../../results/topics-full-index-2026-10-19.md) | retrieval with and without the topic table, dense and BM25 |
| 2026-10-21 | [Production upgrades and what comes next](next-upgrades-2026-10-21.md) | probes, load shedding, circuit breaker, metrics, CI gates and supply chain; the ranked list after them |
| 2026-10-22 | [Paraphrase cache threshold](semantic-cache-2026-10-22.md) | bge-m3 similarity of 60 paraphrases against 8,250 near misses; why 0.965 and which gates stop what |

Screenshots of the web UI are in [../screenshots/](../screenshots/).
