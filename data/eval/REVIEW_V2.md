# Evaluation set v2 — drafts to review

`eval_v2_draft.jsonl` holds 16 new questions, drafted against the real corpus text
(43,966 chunks) to cover acts the reported set never touches: Majority, Partnership,
Muslim Marriages and Divorces (Registration), Easements, Arms, Parents' Maintenance,
Tobacco Control, Domestic Violence, Human Trafficking 2026, Land Offences 2023.
Every gold id was checked against the section text; the set validates against the
corpus (`bdrag eval --eval data/eval/eval_v2_draft.jsonl ...`).

They are **drafts**. Read each question and reference answer, fix or drop it, then
rename the file to `eval_v2.jsonl` and report it separately from `eval.jsonl`, so the
86 test questions stay comparable with the published numbers.

## A gold label in the reported set worth a second look

`sr02` ("Someone threw me out of my land without legal process. Can I get it back
quickly?") has gold `36:24720` (Specific Relief Act s.9) only. The Land Offences
Prevention and Remedy Act, 2023 s.8 (`1454:52772`) gives exactly this remedy, and
faster: apply to the Executive Magistrate to restore possession. The failure
analysis counts sr02 as the one true retrieval miss; with both sections as gold it
may not be. Changing a gold label after seeing results biases the reported number,
so this is left for you to decide. `v2-14` asks the same thing in Bangla with both
sections as gold.

## Judge calibration

`bdrag calibrate-judge results/<run>.answers.json --sample 20` asks you to grade 20
answers yourself and then reports Cohen's kappa against the LLM judge. It needs a
human; nothing here can stand in for that.
