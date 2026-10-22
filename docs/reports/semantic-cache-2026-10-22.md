# Paraphrase cache: choosing the threshold

Measured 2026-10-22 in a cloud session, no laptop index. Command:

    bdrag semcache --embedder st --model BAAI/bge-m3

The threshold only needs the embeddings of the questions, so bge-m3 on CPU was
enough. The section-overlap gate needs the index and was **not** applied here. It can
only stop more merges, so the numbers below are the cache's worst case.

## Pairs

- **60 paraphrases** (`data/eval/paraphrases.jsonl`, `same: true`): rewordings of eval
  questions in English, Bangla and romanised Bangla. Examples: "murder punishment in
  Bangladesh", "চুরি করলে কী শাস্তি হয়?", "cheque bounce what happens".
- **48 near misses** (`same: false`), written to be hard. Each one shares most words
  with its pair but needs a different answer, for example:
  - murder vs attempted murder
  - demanding vs giving dowry
  - daily vs weekly working hours
  - maternity leave vs maternity benefit
  - "pays rent regularly" vs "does not pay rent"
  - kidnapping vs abduction
- **8,202 more negatives**: every pair of answerable eval questions (eval, tune, gaps,
  scenarios) whose gold sections do not overlap.

## Which gate stops what

Of the 8,250 negatives, 7,407 are stopped before similarity is looked at:

| Gate | Negatives stopped |
|---|---|
| script (Bangla, Latin, mixed) | 4,287 |
| topics | 1,447 |
| negation count | 912 |
| numbers | 761 |

The gates stop **none** of the 60 paraphrases.

Among the hand-written near misses, the gates stop 18 of 48. Some examples:

- The negation gate stops "ভাড়া দিলে" vs "ভাড়া না দিলে" (pays rent vs does not pay rent), which have a similarity of 0.913.
- The topic gate stops "ধর্ষণের শাস্তি" vs "ধর্ষণের পর হত্যার শাস্তি" (rape vs rape followed by murder), at 0.906.
- The topic gate also stops "selling adulterated food" vs "selling expired food", at 0.873.

## Similarity of what is left

| Threshold | Paraphrases merged (of 60) | Near misses merged (of 843 left) |
|---|---|---|
| 0.93 | 54 | 2 |
| 0.95 | 48 | 1 |
| 0.955 | 45 | 1 |
| 0.96 | 43 | 0 |
| **0.965** | **40** | **0** |
| 0.97 | 34 | 0 |
| 0.98 | 20 | 0 |

These are the closest near misses that get past every gate:

| Similarity | Question A | Question B |
|---|---|---|
| 0.958 | যৌতুক দাবি করলে কী শাস্তি হয়? (demanding dowry) | যৌতুক দিলে কী শাস্তি হয়? (giving dowry) |
| 0.942 | শ্রমিকের দৈনিক কর্মঘণ্টা কত? (daily hours) | শ্রমিকের সাপ্তাহিক কর্মঘণ্টা কত? (weekly hours) |
| 0.923 | What is the punishment for kidnapping? | What is the punishment for abduction? |
| 0.914 | How much maternity leave does a female worker get ...? | How much maternity benefit is paid ...? |
| 0.909 | What is the punishment for kidnapping? | ... kidnapping a woman or child? (eval pair pc14 / ns03) |

The highest near miss is 0.958, one word apart. 0.965 adds a margin of 0.005 above it,
rounded up, and becomes `TUNED["BAAI/bge-m3"]` in `service/semcache.py`.

## Paraphrases it misses

These score between 0.94 and 0.964 and get a fresh answer:

- "attempting suicide" vs "attempted suicide illegal"
- "punishment" vs "sentence"
- "case" vs "suit" filed after the limitation period

These score below 0.9:

- Short keyword forms such as "money laundering punishment"
- Romanised spelling variants such as "chorir / churir shasti ki" (0.80)

A miss costs one model call. A false merge would give someone the answer to a different
legal question. That trade-off is why the threshold sits above every near miss rather
than at the best F1.

One experiment did not help. Lower-casing the questions and dropping "in Bangladesh"
before embedding *lowered* the paraphrase scores: at 0.965 it merged 30 of 60 instead
of 40. The cache embeds the question exactly as the search does, and that also lets
the two share one embedding.

## Still to do on the laptop

- Run `bdrag semcache --index data/index` to apply the section-overlap gate on the full
  index and confirm it does not stop paraphrases. If it does, lower
  `BDRAG_SEMANTIC_OVERLAP`.
- Add near misses for any wrong merge found in use. The page shows the earlier question
  next to every answer served this way, so a wrong merge is visible. Re-run
  `bdrag semcache` afterwards.
