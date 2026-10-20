---
title: Bangladesh Law Assistant
emoji: ⚖️
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Bangla + English answers from Bangladeshi statutes, cited
---

# Bangladesh Law Assistant (bd-legal-rag)

Answers questions about the laws of Bangladesh in Bangla or English, grounded in
the statute text with the section cited. Source: https://github.com/roy032/bd-legal-rag

## Setting up this Space (free)

1. Push the index once from the machine that built it:
   `python scripts/sync_index.py push --repo <you>/bdrag-index --private`
2. Create a Space with the **Docker** SDK and the free **CPU basic** hardware, then
   upload `Dockerfile`, `start.sh` and this `README.md` from `deploy/hf-space/`.
3. In the Space settings add:
   - variable `BDRAG_INDEX_REPO` = `<you>/bdrag-index`
   - secret `HF_TOKEN` (read access), only if the dataset is private
   - an answering model, as variables plus one secret. Free options:
     - Groq: `RAG_LLM=groq`, `RAG_MODEL=llama-3.3-70b-versatile`; secret `GROQ_API_KEY`
     - Gemini: `RAG_LLM=gemini`, `RAG_MODEL=gemini-flash-latest`; secret `GEMINI_API_KEY`
     - Hugging Face: `RAG_LLM=hf`, `RAG_MODEL=Qwen/Qwen2.5-72B-Instruct`; the `HF_TOKEN` secret
   - optional: let visitors pick a model, default first, e.g.
     `BDRAG_MODELS=groq:llama-3.3-70b-versatile,groq:openai/gpt-oss-120b,gemini:gemini-flash-latest`
     (entries whose key is missing are hidden)
   - optional: `BDRAG_DAILY_LIMIT` (default 500 answers a day across all visitors) to stay
     inside the free tier's quota; `BDRAG_RERANK=cross` with `BDRAG_RERANK_PRECISION=int8`
     to turn on the reranker (a few seconds more per answer on the 2-vCPU Space)
   - optional: `BDRAG_REF` = the branch or tag to serve (default `main`)
   Without a model the Space still returns the matching sections, just no written answer.
4. Optional, keep it in sync automatically: in the GitHub repo add the Actions variable
   `HF_SPACE` = `<you>/<space-name>` and the secret `HF_TOKEN` (write access). The
   "Deploy to Hugging Face Space" workflow then re-uploads these files and rebuilds the
   Space on every push to `main`.

The first start downloads bge-m3 (~2.3 GB) and takes a few minutes. Free Spaces
sleep after 48 hours without visitors and wake on the next visit. Questions and
retrieved excerpts are sent to the answering-model provider you choose.
