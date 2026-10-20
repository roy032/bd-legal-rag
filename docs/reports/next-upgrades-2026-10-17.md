# bd-legal-rag: what to upgrade next

Reviewed 2026-10-17 at `main` = `f38b5aa`, plus open PRs #1, #2, #3, [the comparison report](comparison-bangladesh-legal-chatbot.md) and [`free-llm-run/`](free-llm-run/README.md). Nothing in the repo was changed. Constraint respected throughout: free or local models only, no Anthropic API.

## First, the state of the repo

- **`main` is behind all three open PRs, and the PRs conflict with each other.** Each PR merges cleanly into `main` on its own (CI green on #1 and #3; #2 green per earlier run), but pairwise they conflict:
  - #1 + #2: `README.md`, `scripts/ask.py`
  - #1 + #3: `pyproject.toml`, `scripts/build_index.py`, `src/rag/cli.py`, `src/service/static/index.html`
  - #2 + #3: `pyproject.toml`
- #1 is the big one (64 files): it moves every script into `src/bdrag_tools/`, adds prompt v5 (scenario answers), `--rerank-top`, `--rewrite`, the requested-section label, Qdrant verification and the 16 draft eval questions. **The free-model run in [`free-llm-run/`](free-llm-run/README.md) used prompt v5, which is only on PR #1**, so `main` today does not serve what was measured.
- Consequence: every new upgrade built on `main` now adds a fourth branch to reconcile. Landing the PRs is step zero.

## Prioritised list

Effort: S = under a day, M = 1 to 3 days, L = a week or more. Impact is on what a user of the app notices.

| # | Upgrade | Area | Effort | Impact | Why |
|---|---|---|---|---|---|
| 0 | **Merge PR #1, then rebase #2 and #3 on it and merge them** | Repo | S | High | Unblocks everything below; `main` gets prompt v5, free backends, doctor, OCR ingest, HF deploy. Conflicts are mostly mechanical (scripts moved to `bdrag_tools`). |
| 1 | **Re-measure on the laptop after the merge** (retrieval ablation + e2e with `gemma4:e4b`) | Evaluation | S | High | The headline answer numbers are from qwen2.5:7b/14b and predate the glossary (recall@5 0.85 → 0.90) and `TOPIC_ACTS` (unmeasured). You need one honest baseline for the free model you actually serve. |
| 2 | **Add the scenario gaps to the eval set** (consumer EN→BN, defamation s.499/500, unpaid wages, rent doubling, dowry range) and promote the 16 reviewed v2 drafts | Evaluation | S | High | 86 test questions is thin and has almost no scenario questions, which is now the main use case. Without them, fixes for the known gaps can't be shown to work or protected by the CI gate. |
| 3 | **Cross-lingual query: translate the question and retrieve with both** (local model, one call, RRF over the two dense lists) | Retrieval | M | High | English→Bangla misses are structural (consumer act). `TOPIC_ACTS` patches named topics only; translation covers the rest. Gate it so it only runs when the question's language differs from the likely act's, to save latency. |
| 4 | **Make the reranker usable on CPU** — `bge-reranker-v2-m3` over top 15–20 only (`--rerank-top` in #1), int8 ONNX export, cache by (query, chunk) | Retrieval | M | High | Best measured recall@5 (0.88 vs 0.81 dense) and ranking misses are the largest failure bucket (11 of 20), but p95 is 109 s over 50 candidates. Top-20 + ONNX int8 should land at a few seconds; measure it. Fallback: a smaller multilingual reranker (e.g. `bge-reranker-base`-class) if bge-v2-m3 stays slow. |
| 5 | **Fix citation misses: put the resolved/requested section first and labelled** | Answer quality | S | Medium | 8 of 20 misses had the gold section in front of the model but it cited a neighbour (ধারা ৩৪, Article 27). PR #1 adds the label; verify the ordering too and re-measure "cites a gold section". |
| 6 | **Answer latency on CPU** — stream tokens to the UI (SSE already exists), cap excerpts at ~1,500 chars each, `num_ctx` sized to the prompt, keep the model warm (`keep_alive`) | Performance / UX | S–M | High | gemma4:e4b takes 20–115 s per answer on CPU. Users wait less if text starts appearing in a few seconds; shorter context also cuts time-to-first-token roughly in proportion. |
| 7 | **Try a bigger free hosted model as an opt-in** (Groq `llama-3.3-70b-versatile`, `openai/gpt-oss-120b`; Gemini free tier) on the scenario set | Answer quality | S | Medium | PR #2 already supports them. Likely fixes the rent-doubling and dowry-range omissions the 4B models made. Keep `gemma4:e4b` the local default; hosted means questions leave the machine, so label it in the UI. |
| 8 | **Calibrate the judge with a free stronger judge + ~40 human labels** | Evaluation | M | Medium | Correctness/faithfulness are judged by llama3.1:8b, uncalibrated. Use a 70B free judge (Groq) with the existing `calibrate_judge.py`, and label 40 answers yourself to get its agreement rate. |
| 9 | **Amendment / in-force awareness in answers** | Robustness | M | Medium | README names amendments as "the real risk". Show the act's last-amended date on every source card and make the prompt state when a cited excerpt is marked `[amended]`. |
| 10 | **Public free demo on a Hugging Face Space** (deploy files in PR #3) | Deployment | S–M | Medium | Makes it shareable. Use bge-m3 on CPU (fits 16 GB), index pulled from a HF dataset repo, answers via Groq/Gemini secret (CPU-only 4B generation would be too slow for visitors). Add the rate limiter and a daily cap since the key is yours. |
| 11 | **UI: sources toggle with expandable cards, model picker, copy/share answer, Bangla numerals in citations** | UI/UX | S | Medium | Small additions to `index.html`; `/a/{id}` permalinks already exist. |
| 12 | **Count image-only acts before running OCR at scale** | Corpus | S | Low–Medium | PR #3 adds ben+eng Tesseract ingest; only worth running if many acts are scanned. One script over the cached pages tells you. |
| 13 | **Use the `/feedback` endpoint**: write thumbs-down answers to a file and review them weekly into new eval questions | Evaluation | S | Medium (over time) | Turns real usage into eval coverage. |
| 14 | **Contextual chunk headers** (`scripts/contextualize.py` exists) re-run with gemma4 and re-measured | Retrieval | M | Unknown | Could help the "many acts share vocabulary" ranking misses; needs a full re-embed, so only after 1–4. |
| 15 | Leftovers from `IMPROVEMENTS.md`: Qdrant live check, scripts as entry points | Robustness | S | Low | Both are done in PR #1; they disappear once it merges. |

Not worth doing now: switching to LangChain/Chroma, fine-tuning an embedder or LLM (eval set too small to show a gain), a Groq/Gemini-only default (breaks the fully local promise), and an ungrounded "general knowledge" fallback (undermines the refusal guarantee).

## Recommendation

1. **Do #0 now**: merge PR #1, rebase #2 and #3 onto it, merge both. This is the only item that makes the others cheaper.
2. **Then #1 + #2 together on the laptop**: grow the eval set with the scenario gaps, and take one baseline with `gemma4:e4b` on the merged code. Everything after this is a measured change against that baseline.
3. **Then the two retrieval upgrades, #4 (CPU reranker over top 20) and #3 (translate-and-fuse)**, each ablated separately. Ranking misses are the biggest failure bucket and cross-lingual misses are the most visible scenario failures.
4. **#6 (streaming + shorter context)** alongside, since it's the biggest felt improvement for a local 4B model.

Items 7–11 can follow in any order; #10 (HF Space) is the right moment to share the project once 1–6 are in.
