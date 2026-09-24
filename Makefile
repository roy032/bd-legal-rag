.PHONY: help install dev test lint typecheck coverage ingest index eval ablate tune sweep \
        calibrate failures gate serve demo loadtest docker-build docker-run clean
PY ?= python
EVAL ?= data/eval/eval.jsonl
INDEX ?= data/index

help:            ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "  %-14s %s\n",$$1,$$2}'

install:         ## install the package and its runtime dependencies
	$(PY) -m pip install -e ".[serve]"

dev:             ## install everything, including dev tools
	$(PY) -m pip install -e ".[serve,embed,llm,dev]"

test:            ## run every test (offline, no API key needed)
	$(PY) -m unittest discover -s tests -v

lint:            ## ruff
	ruff check src scripts tests

typecheck:       ## mypy
	mypy

coverage:        ## test coverage report
	coverage run -m unittest discover -s tests && coverage report -m | tail -30

ingest:          ## scrape + parse + chunk (ACTS="--year-from 2000 --limit 30")
	$(PY) scripts/ingest.py $(ACTS)

index:           ## build the dense + BM25 indexes
	$(PY) scripts/build_index.py --bm25

eval:            ## retrieval metrics on the evaluation set
	$(PY) scripts/eval_retrieval.py --eval $(EVAL) --index $(INDEX) --label dev

ablate:          ## the full sweep -> results/ablation.md
	$(PY) scripts/ablate.py --eval $(EVAL) --index $(INDEX) --out results/ablation.md

tune:            ## grid-search fusion weights on the TUNING split
	$(PY) scripts/tune.py --eval data/eval/tune.jsonl --index $(INDEX)

sweep:           ## chunk-size sweep (re-chunks, re-indexes, re-evaluates)
	$(PY) scripts/sweep_chunking.py --eval $(EVAL)

calibrate:       ## pick the abstention threshold
	$(PY) scripts/calibrate_guard.py --eval $(EVAL) --index $(INDEX) --mode hybrid --expand-refs

failures:        ## which stage is losing you the most?
	$(PY) scripts/failure_report.py --eval $(EVAL) --index $(INDEX) --out results/failures.json

gate:            ## CI quality gate: fail if retrieval regressed
	$(PY) scripts/ci_eval_gate.py --eval $(EVAL) --index $(INDEX)

serve:           ## run the API + UI on :8000
	BDRAG_INDEX=$(INDEX) $(PY) -m uvicorn service.app:get_app --factory --app-dir src \
		--host 0.0.0.0 --port 8000 --reload

demo:            ## end-to-end on the bundled sample corpus, no downloads
	$(PY) scripts/build_index.py --chunks data/sample/chunks.jsonl --out data/sample/index \
		--embedder hashing --bm25
	$(PY) scripts/ablate.py --eval data/eval/sample_eval.jsonl --chunks data/sample/chunks.jsonl \
		--index data/sample/index --embedder hashing --rerank-kind lexical -k 5

loadtest:        ## throughput and p95 against a running server
	$(PY) scripts/loadtest.py --url http://localhost:8000/search --concurrency 8 --requests 200

docker-build:    ## build the container
	docker build -t bd-legal-rag .

docker-run:      ## run the container with the local index mounted
	docker run --rm -p 8000:8000 -v $(PWD)/data:/app/data \
		-e RAG_LLM -e RAG_MODEL -e OLLAMA_HOST -e ANTHROPIC_API_KEY -e OPENAI_API_KEY bd-legal-rag

clean:           ## remove caches and build artefacts
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
