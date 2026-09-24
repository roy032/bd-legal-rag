# Writing the evaluation set (data/eval/WRITING_GUIDE.md)

Goal: 150–200 questions, labelled with the section(s) that answer them. This file is the
recipe. Budget 4–6 sessions of about 90 minutes; do not try to do it in one sitting.

## Loop

```bash
python scripts/make_eval_template.py --n 40 --out data/eval/batch1.jsonl   # pre-fills gold + shows the text
# write question + reference_answer for each row, delete _source_text
python scripts/make_eval_template.py --validate data/eval/batch1.jsonl     # catches unfilled rows, bad labels
cat data/eval/batch*.jsonl > data/eval/eval.jsonl
```

Write 40, then run `scripts/eval_retrieval.py`. The failures teach you what to write next.

## Target mix (200 questions)

| Type | Count | What it looks like |
|---|---|---|
| `single` | ~100 | "ভাড়া বৃদ্ধির নোটিশ কত দিন আগে দিতে হয়?" — one section answers it |
| `multi` | ~30 | needs two sections: a definition plus an operative rule, or two acts compared |
| `exact_ref` | ~30 | "ধারা ৩০২ কী বলে?", "What does section 304A cover?" |
| `unanswerable` | ~20 | real questions the corpus cannot answer (VAT rates, court fees, procedure not in these acts) |
| `paraphrase` | ~20 | the question a person asks, using none of the section's vocabulary |

Languages: about 45% Bangla, 45% English, 10% code-switched ("Penal Code এর ধারা ৩০২ এ কী আছে?").

## Rules that decide whether the numbers mean anything

1. **Write the question before you look at the section's wording.** Read the provision,
   look away, then ask it the way a tenant, shopkeeper, employee or student would.
2. **Never copy the section's phrasing into the question.** If the section says
   "দায়যুক্ত বীমাকারী", ask about "a company that owes money on policies". Copying its
   words makes retrieval look great and tells you nothing.
3. **Do not let a model write the questions.** A model that reads the section reproduces
   its vocabulary — you end up measuring the model against itself.
4. **Reference answers stay short**: one or two sentences of substance, from the text.
5. **Label every section that genuinely answers it**, not just the first one you found.
6. **Unanswerable means plausible but absent** — a question someone would really ask that
   these acts do not cover. "What is the capital of France?" tests nothing.

## Where to get questions that sound real

- Everyday situations: rent, eviction, notice periods, employment termination, overtime,
  consumer complaints, cheques, land registration, marriage and inheritance registration.
- University life: course policies aside, think tenancy and part-time work questions.
- Search Bangla legal-advice forums and news comment threads for how people phrase these.
- Your own family's actual questions. They are the best source, and they are free.

## Question stems to fill in (write your own version of each)

Bangla: "… কত দিনের মধ্যে করতে হয়?" · "… না করলে কী শাস্তি?" · "… এর সংজ্ঞা কী?" ·
"… কে অনুমতি দেয়?" · "… এর আবেদন কোথায় করতে হয়?" · "… বাতিল করা যায় কি?"

English: "What is the penalty for …?" · "Who is required to register …?" ·
"How long do I have to …?" · "Does the Act apply to …?" · "What counts as … under the Act?"

## Quality check before you trust the set

- Ask a friend to label 20 of your questions independently. If you disagree on more than
  two or three, your labels are fuzzier than you think — say so in the README; it is the
  kind of honesty interviewers notice.
- `--validate` should be silent. It catches empty questions, duplicate ids and questions,
  gold labels missing from the corpus, multi-hop rows with one label, and missing
  reference answers.
- Keep `batch1..n` files separate in git so you can show the set growing.

## Hold out a tuning split

Split off ~30 questions as `data/eval/tune.jsonl` and use **only those** for choosing
fusion weights, `rrf_k` and `--min-score`. Report on the rest. Tuning on the set you
report is fitting your own exam, and it is the first thing a sharp interviewer probes.
