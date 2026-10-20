# Free answering models on the full corpus (2026-10-16)

Setup: the full index from the laptop (43,966 chunks, bge-m3), the served retrieval configuration (dense, resolve-refs, k=5) and prompt answer-system/v5. Each model ran as a GGUF (Q4_K_M) through llama.cpp's OpenAI-compatible server, using the new `RAG_LLM=compat` backend on a 4-core cloud CPU. Nothing was paid for and no API key was used.

Raw outputs, including every answer, its citations and the retrieved excerpts: `out-gemma4-e4b.jsonl`, `out-qwen35-4b.jsonl`, `questions.jsonl`.

## Verdict

**Gemma 4 E4B is the free model to use.** Its Bangla reads like the statute text, it applied the right sections, and it ran about twice as fast as Qwen3.5 4B (20 to 115 s per answer on CPU, against 30 to 290 s). Every claim either model made carried a citation to a retrieved excerpt (no invalid citation numbers). The gaps that remain come from retrieval, not from the model.

## Per question

| Question | Qwen3.5 4B | Gemma 4 E4B |
|---|---|---|
| Landlord eviction without notice + doubled rent (bn) | Partly right (Rent Control Act s.7, s.18), but one claim cites the Court-fees Act; 1 uncited sentence | Correct grounds for eviction from Rent Control Act s.18 and notice procedure, quoted closely; does not address the rent doubling directly |
| Unpaid salary + dismissal (en) | Correct on Labour Act s.23/26, says honestly that wage-arrears remedies are not in the excerpts | not run |
| Dowry violence (bn) | NNSDA s.11 punishments, but repeats one clause with a contradictory sentence | NNSDA s.11 plus Dowry Prohibition Act 2018 s.3 and s.4, accurate; drops the 2 to 5 year range for simple hurt |
| Dishonoured cheque (bn) | NI Act s.138 conditions right, but Bangla errors ("যাবজ্জীবন ১ বছর", a Korean word, "নোটিশ পান") and says the fine goes to the drawer (wrong) | NI Act s.138 conditions, notice methods, fine to the holder, civil suit: all correct |
| Defective phone, consumer rights (en) | Refused: the excerpts had no consumer law | not run |
| Facebook defamation (en) | Lists unrelated sections (coins, loans) | Only s.505A (public order); misses defamation |
| Punishment for murder (bn) | Right, slightly garbled ("এবং ফাঁসী") | Right: death or life imprisonment, and fine |
| দণ্ডবিধির ধারা ৩০২ (bn) | Right | not run |

## Retrieval gaps found (not model problems)

- **English consumer question:** the Bangla ভোক্তা অধিকার সংরক্ষণ আইন, ২০০৯ is in the corpus but was not retrieved. English-to-Bangla cross-lingual retrieval misses it.
- **Defamation:** Penal Code s.499/500 and the cyber law were not in the top 5, so both models answered from s.505A.
- **Unpaid wages:** the Labour Act wage-payment sections were not retrieved, only the dismissal sections.

## Running it on the laptop (free, nothing leaves the machine)

```
ollama pull gemma4:e4b
set RAG_LLM=ollama
set RAG_MODEL=gemma4:e4b
.venv\Scripts\python scripts\ask.py "যৌতুকের জন্য স্বামী মারধর করলে কী শাস্তি?"
```

Or use a free hosted model (faster, better on hard questions, but questions and excerpts go to the provider): `set RAG_LLM=gemini` and `set GEMINI_API_KEY=...` (free key from aistudio.google.com), or `RAG_LLM=groq` with a free `GROQ_API_KEY`.
