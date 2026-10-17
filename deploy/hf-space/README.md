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
   - an answering model. Free options:
     - Groq: variables `RAG_LLM=openai`, `RAG_MODEL=llama-3.3-70b-versatile`,
       `OPENAI_BASE_URL=https://api.groq.com/openai/v1`; secret `OPENAI_API_KEY` = your Groq key
     - Gemini: the same with `OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/`,
       `RAG_MODEL=gemini-2.5-flash` and your Gemini key
   Without a model the Space still returns the matching sections, just no written answer.

The first start downloads bge-m3 (~2.3 GB) and takes a few minutes. Free Spaces
sleep after 48 hours without visitors and wake on the next visit. Questions and
retrieved excerpts are sent to the answering-model provider you choose.
