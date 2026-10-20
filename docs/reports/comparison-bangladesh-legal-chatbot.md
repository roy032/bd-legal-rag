# What to learn from tonmoyjoy/Bangladesh-Legal-Chatbot

Studied on 2026-10-17 at commit `6834a2d` (2026-05-31), read-only. Nothing in roy032/bd-legal-rag was changed.

## Short version

Their project is a clean, beginner-friendly RAG demo: PDF → 800-character chunks → MiniLM embeddings → Chroma → Groq Llama → Streamlit. It is easy to set up and easy to deploy, and that is its real strength. On retrieval, Bangla, citations, guardrails and evaluation, your repo is well ahead, so there is little to copy in the core pipeline. The things worth taking are around it: an **OCR path for scanned PDFs**, a **one-click free hosted demo**, a **setup checker**, and a **much simpler "first run" story**. Their code also has several bugs worth knowing about so they are not copied (listed below).

## What they built

| Stage | Their choice | Notes from reading the code and their committed index |
|---|---|---|
| Corpus | 4 English PDFs: Constitution, Penal Code, CrPC, Muslim Family Laws Ordinance | Their committed Chroma index has 3,964 chunks and **0 chunks with any Bangla text** (checked in `chroma.sqlite3`). |
| Parsing | PyMuPDF page text; Tesseract OCR if a page has under 30 characters | OCR runs with Tesseract's default language (English). There is no `lang="ben"`, so a scanned Bangla act would come out as garbage. |
| Cleaning | Collapse blank lines, strip control characters | Browser print headers survive: 1,038 of 3,964 chunks (26%) contain the "16/05/2026 The Code of…" print-date line. OCR noise like `Expressions a . os ‘the full` is also in the index. |
| Chunking | `RecursiveCharacterTextSplitter`, 800 chars, 150 overlap, per page | Chunks cross section boundaries and page breaks; metadata is only file name and page. No act/section/chapter fields. |
| Embeddings | `all-MiniLM-L6-v2` (384-dim, English-only) | Will not retrieve Bangla questions in any useful way. |
| Store | Chroma, persisted, committed to git (51 MB) | |
| Retrieval | Plain cosine top-k (default 5) | No BM25, no reranker, no reference resolution, no refusal gate. |
| LLM | Groq free tier: `llama-3.1-8b-instant` (default), `llama-3.3-70b-versatile`, `openai/gpt-oss-120b` | temperature 0.1, 1024 max tokens. |
| Prompt | One system prompt: answer only from context, quote sections, a fixed "could not find" sentence, no personal advice, use headings and bullets | No per-sentence citation requirement, no language rule, no injection rule. |
| UI | Streamlit, dark theme, Bangla title, 6 sample-question buttons, Top-K slider, model dropdown, "show sources" toggle with source cards, clear-chat button, optional per-session Groq key | |
| Evaluation | None. `test_setup.py` is a dependency/config checker, not a test suite. | |
| Deployment | Streamlit Community Cloud with the prebuilt index committed and the Groq key in Streamlit Secrets; a devcontainer for Codespaces | |

## Where yours is already stronger (do not replace)

- **Bangla.** bge-m3 plus Bangla-aware BM25, legacy-Bangla repair, romanised Bangla and a legal glossary, against an English-only embedder and an English-only corpus.
- **Structure.** Act → Chapter → Section parsing, section-aware chunks with cross-references, so citations name the act and section. Theirs cites "file — page".
- **Retrieval quality is measured.** recall@5 0.85 on 86 held-out questions with intervals; theirs has no measurement at all.
- **Grounding.** Per-sentence `[n]` citations, verbatim-quote checks, NOT_FOUND refusals, a corrective re-prompt, injection handling. Their prompt only asks politely.
- **Follow-up questions.** You condense follow-ups into standalone queries (`src/rag/chat.py`); theirs has no conversation memory, each question is independent.
- **Scenario answers.** Your v5 prompt applies the law to the user's facts with a legal-aid note; theirs refuses personal advice.
- **Safe rendering.** Your UI escapes corpus and model text; theirs injects raw HTML (see bugs).
- **No framework lock-in.** LangChain + Chroma would add dependencies without improving anything at 44k chunks; your `NumpyStore` is fine.

## Worth adopting

1. **OCR for scanned acts (with Bangla).** Your `docs/DATA_CARD.md` says scanned-image acts are absent because there is no OCR step. Their fallback (render the page at 300 dpi, OCR it when text extraction returns under ~30 characters) is the right shape. Change it for your corpus: use `tesseract -l ben+eng` (the `tesseract-ocr-ben` language pack), run `fix_legacy_bangla` and your normal parser on the output, and tag such chunks `ocr: true` so the guardrails can treat quotes from them as approximate. First count how many bdlaws acts are image-only before spending time on it.
2. **A free hosted demo.** Their Streamlit Cloud recipe (prebuilt index shipped with the app, key in platform secrets, `config.py` reading env first and secrets second) is a good pattern. For your stack, Streamlit Cloud's ~1 GB RAM is too small for bge-m3; the closer fit is a **Hugging Face Space (Docker, free CPU tier, 16 GB)** running your existing `Dockerfile`, with the index downloaded from a HF dataset repo at start-up and `RAG_LLM=groq` or `gemini` from Space secrets.
3. **A setup checker.** Their `test_setup.py` prints a ✅/❌ list: Python version, each import, API key, PDFs found, index present. A `bdrag doctor` command for your repo would save the laptop runbook a lot of back-and-forth: check the index files and chunk count, bge-m3 cached, `RAG_LLM` set, Ollama reachable at 127.0.0.1:11434 and the model pulled, key present for groq/gemini.
4. **Larger free hosted models to try.** They offer `llama-3.3-70b-versatile` and `openai/gpt-oss-120b` on Groq's free tier. Your groq preset (PR #2) can already call them; run the same 8 scenario questions from `free-llm-run/` against both and compare their Bangla with gemma4:e4b. A 70B+ model may fix the dowry-range and rent-doubling misses that the 4B models had.
5. **UI conveniences.** A model picker and a "show sources" toggle with expandable source cards are small additions to your `index.html`. Your page already has example questions; theirs are grouped by area of law (rights, theft, land, arrest, custody, bail), which is a nice touch for first-time users.
6. **A five-step quick start.** Their README gets someone from clone to a working chatbot in five commands. Yours is complete but long. A short "laptop in 5 commands" block at the top (install, download index, `ollama pull gemma4:e4b`, `bdrag serve`) would help.

## Bugs in their code (avoid when borrowing)

- **Sidebar settings do nothing after the first question.** `rag_chain.py` caches the chain in a module global, built with the Top-K, model and key that existed at first call. Moving the slider or changing the model later has no effect.
- **That cache is shared by every visitor.** On Streamlit Cloud one process serves all sessions, so the first visitor's pasted Groq key ends up being used for everyone.
- **Retrieval runs twice per question.** `query_with_sources` calls `similarity_search` and then the chain retrieves again.
- **HTML injection.** User input and model output are inserted into `st.markdown(..., unsafe_allow_html=True)` without escaping, and Markdown inside those `<div>`s is not rendered.
- **Re-ingest duplicates the index.** `Chroma.from_documents` appends to an existing persist directory, although the docstring says it replaces it.
- **Streaming is advertised but unused.** The UI calls the non-streaming path.

## Prioritised improvements for your project

These combine what their repo suggests with the gaps your own free-model run found (see [`free-llm-run/README.md`](free-llm-run/README.md)).

1. **Fix English → Bangla retrieval.** The English consumer question missed ভোক্তা অধিকার সংরক্ষণ আইন, ২০০৯. Cheapest fix: map English act names and topics to Bangla titles in the lexicon (consumer rights → ভোক্তা অধিকার). Next: translate the question with the local model (gemma4:e4b) and retrieve with both versions, fused. Measure on the eval set.
2. **Fill the topic gaps.** Add defamation/মানহানি → Penal Code s.499/500 and the cyber law, and wages/মজুরি → Labour Act wage-payment sections, to the synonym lexicon; add those three scenarios to `eval.jsonl` so they stay fixed.
3. **Try a 70B+ free model.** Run the scenario set on Groq `llama-3.3-70b-versatile` and `openai/gpt-oss-120b` (item 4 above); keep gemma4:e4b as the fully local default.
4. **Make the reranker usable on CPU.** It gives the best recall (0.88) but p95 is 109 s. Rerank only the top 15–20, try an int8/ONNX export of `bge-reranker-v2-m3`, and re-measure with `--rerank-top`.
5. **Add `bdrag doctor`** (item 3 above).
6. **OCR ingest for scanned acts** with `ben+eng` (item 1 above), after counting how many acts need it.
7. **Free public demo on a Hugging Face Space** (item 2 above).
8. **Small UI additions:** model picker, sources toggle, examples grouped by area of law.

## Not worth adopting

MiniLM embeddings, character/page chunking, page-number citations, LangChain LCEL and Chroma, committing the vector store to git, and the "no personal advice" refusal (your v5 handles scenarios better).
