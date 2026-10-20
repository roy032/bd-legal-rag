# Topic table on the full index, 2026-10-19

Index: the laptop's `data/index` (43,966 chunks, bge-m3). `-k 5`, with and without `--topics`.

## Dense bge-m3: what the service runs

`--mode dense --synonyms --expand-refs --transliterate --boost-in-force --resolve-refs --max-parts-per-section 2`
(no `--translate`/`--rewrite`: those need the answering model)

| Set | Questions | recall@5 off | recall@5 on | MRR off | MRR on | Worse with topics |
|---|---|---|---|---|---|---|
| eval.jsonl | 86 answerable | 0.907 | 0.936 | 0.775 | 0.804 | none (3 better) |
| tune.jsonl | 22 | 0.818 | 0.818 | 0.735 | 0.788 | none |
| eval_v2_draft.jsonl | 16 | 0.750 | 0.750 | 0.703 | 0.703 | none |
| eval_scenarios.jsonl | 8 | 0.625 | 0.896 | 0.510 | 0.750 | none (3 better) |

## BM25 only (first run, before the placement change below)

| Set | recall@5 off | recall@5 on |
|---|---|---|
| eval.jsonl | 0.471 | 0.581 |
| tune.jsonl | 0.455 | 0.545 |
| eval_v2_draft.jsonl | 0.406 | 0.469 |
| eval_scenarios.jsonl | 0.167 | 0.969 |

## What changed between runs

- First version put the table's sections first. With dense that raised recall but
  pushed bge-m3's correct first hit down (eval MRR 0.775 -> 0.734). Now a governing
  section the search already found keeps its rank and the others take the last places.
- Entries added after a run showed them losing a question: Constitution art. 33 for
  arrest, Contract Act ss. 17/19 for fraud in a contract, the parents' maintenance act,
  Penal Code s. 376 with rape (sexual harassment, s. 10, is now its own topic).
- `bdrag topics` resolves every section to the intended title; the only miss is the Road
  Transport Act, which is not in this index.

The scenario set is not independent: its failures are what the table was built from.
