# Two stages so the model cache and the build tools don't ship to production.
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS deps
COPY requirements.txt .
# CPU-only torch first: the default wheel bundles CUDA libraries (several GB)
# that a CPU container never uses.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

FROM base AS runtime
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY data/sample/ ./data/sample/
COPY data/eval/ ./data/eval/

# Never run a public service as root.
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

ENV PYTHONPATH=/app/src \
    BDRAG_INDEX=/app/data/index \
    BDRAG_CHUNKS=/app/data/processed/chunks.jsonl \
    HF_HOME=/app/.cache/huggingface
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"
CMD ["uvicorn", "service.app:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
