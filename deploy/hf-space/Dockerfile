# A free Hugging Face Space (Docker SDK, CPU basic: 2 vCPU, 16 GB RAM) serving
# bd-legal-rag. The index is not baked in: start.sh pulls it from a dataset repo,
# so rebuilding the index never needs a new image.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Spaces run the container as uid 1000.
RUN useradd --create-home --uid 1000 user
WORKDIR /home/user/app

ARG BDRAG_REPO=https://github.com/roy032/bd-legal-rag
ARG BDRAG_REF=main
RUN git clone --depth 1 --branch ${BDRAG_REF} ${BDRAG_REPO} . \
 && pip install torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install -e ".[serve,embed,hub,llm]" \
 && chown -R user:user /home/user

COPY --chown=user:user start.sh /home/user/start.sh
USER user
ENV HOME=/home/user HF_HOME=/home/user/.cache/huggingface \
    BDRAG_INDEX=/home/user/app/data/index BDRAG_MODE=dense BDRAG_RATE_PER_MIN=20
EXPOSE 7860
CMD ["bash", "/home/user/start.sh"]
