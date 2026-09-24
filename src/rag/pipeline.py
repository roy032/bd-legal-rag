"""One configurable search pipeline, shared by the CLI, the service and the evaluator.

    question
      ├─ resolve explicit references ("দণ্ডবিধির ধারা ৩০২") -> act id + section
      ├─ classify (exact reference / comparative / conceptual) -> weight profile
      ├─ variants: romanised Bangla, section-number expansion, synonyms,
      │            LLM rewrites, HyDE
      ├── dense  (bi-encoder, top C)  ┐
      └── BM25   (lexical, top C)     ├─ reciprocal rank fusion
                                      ┘
            ├─ exact references first (lookup, not search)
            ├─ in-force boost (repealed acts / [Omitted] stubs pushed down)
            ├─ dedupe parts of the same section
            ├─ MMR (relevance vs. diversity)
            ├─ cross-encoder rerank (top C -> k)
            └─ parent expansion (answer from the whole section)

Every stage is a flag on RetrievalConfig, and every flag is a row in the
ablation table. `RetrievalConfig` is the interface: the CLI builds one, the
service builds one, tests build one. Nothing constructs an argparse Namespace
to talk to this module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from .banglish import maybe_variant
from .diversity import boost_in_force, mmr
from .fusion import reciprocal_rank_fusion
from .lexical import BM25Index
from .lexicon import ROUTE_WEIGHTS, classify, expand_synonyms
from .parent import ParentIndex, expand_to_parents
from .query import expand_section_refs, hyde, multi_query
from .refs import ActResolver, Reference, apply_reference
from .rerank import get_reranker
from .retrieve import Retriever, dedupe_by_section
from .store import Hit


@dataclass
class RetrievalConfig:
    mode: str = "dense"                  # dense | bm25 | hybrid
    dense_weight: float = 1.0
    bm25_weight: float = 1.0
    rrf_k: int = 60
    candidates: int = 50                 # per source, before fusion/rerank
    rerank: str = "none"                 # none | cross | lexical
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    expand_refs: bool = False
    synonyms: bool = False
    transliterate: bool = False          # romanised Bangla -> Bangla variant
    route: bool = False                  # per-query-type fusion weights
    multi_query: int = 0                 # 0 = off; else number of rewrites requested
    hyde: bool = False
    mmr_lambda: float | None = None      # None = off; 0.7 is a sane start
    boost_in_force: bool = False
    parent_context: bool = False         # hand the model the whole section
    parent_max_chars: int = 4000
    max_parts_per_section: int | None = None
    include_repealed: bool = False
    resolve_refs: bool = False           # act names + section numbers -> exact lookup
    embedder: str = ""
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_args(cls, args) -> RetrievalConfig:
        """Build from an argparse namespace produced by add_retrieval_args."""
        fields = set(cls().to_dict())
        return cls(**{k: v for k, v in vars(args).items() if k in fields})


class SearchPipeline:
    def __init__(self, config: RetrievalConfig, dense: Retriever | None = None,
                 bm25: BM25Index | None = None, reranker=None, llm=None,
                 parents: ParentIndex | None = None, resolver: ActResolver | None = None) -> None:
        if config.mode in ("dense", "hybrid") and dense is None:
            raise ValueError(f"mode '{config.mode}' needs a dense retriever")
        if config.mode in ("bm25", "hybrid") and bm25 is None:
            raise ValueError(f"mode '{config.mode}' needs a BM25 index (build it with --bm25)")
        if config.parent_context and parents is None:
            raise ValueError("parent_context needs a ParentIndex")
        self.config, self.dense, self.bm25 = config, dense, bm25
        self.reranker, self.llm, self.parents = reranker, llm, parents
        if config.resolve_refs and resolver is None:
            records = (bm25.records if bm25 is not None
                       else dense.store.records if dense is not None else [])
            resolver = ActResolver(records)
        self.resolver = resolver

    def reference(self, question: str) -> Reference:
        if not (self.config.resolve_refs and self.resolver):
            return Reference()
        return self.resolver.resolve(question)

    # ---- query side -------------------------------------------------
    def queries(self, question: str) -> list[str]:
        """Every string that will be searched, in the order they were derived."""
        cfg = self.config
        queries = [question]
        if cfg.transliterate and (variant := maybe_variant(question)):
            queries.append(variant)
        if cfg.multi_query and self.llm:
            queries = multi_query(question, self.llm, n=cfg.multi_query) + queries[1:]
        if cfg.hyde and self.llm:
            queries.append(hyde(question, self.llm))
        if cfg.synonyms:
            queries = [expand_synonyms(q) for q in queries]
        if cfg.expand_refs:
            queries = [expand_section_refs(q) for q in queries]
        return list(dict.fromkeys(queries))

    def weights(self, question: str) -> tuple[float, float]:
        cfg = self.config
        if not cfg.route:
            return cfg.dense_weight, cfg.bm25_weight
        profile = ROUTE_WEIGHTS[classify(question)]
        return profile["dense_weight"], profile["bm25_weight"]

    # ---- retrieval --------------------------------------------------
    def search(self, question: str, k: int = 5, language: str | None = None,
               act_id: int | None = None, include_repealed: bool | None = None,
               max_parts_per_section: int | None = None,
               extra_filters: dict[str, Any] | None = None) -> list[Hit]:
        cfg = self.config
        include_repealed = cfg.include_repealed if include_repealed is None else include_repealed
        max_parts = cfg.max_parts_per_section if max_parts_per_section is None else max_parts_per_section
        c = max(cfg.candidates, k)

        filters: dict[str, Any] = dict(extra_filters or {})
        if language:
            filters["language"] = [language, "mixed"]
        if act_id is not None:
            filters["act_id"] = act_id
        if not include_repealed:
            filters["repealed"] = False

        dense_w, bm25_w = self.weights(question)
        ref = self.reference(question)
        searches: list[tuple[str, dict]] = [(q, filters) for q in self.queries(question)]
        if ref.act_ids and not ref.numbers and act_id is None:
            # The question names an act: also search inside that act only.
            searches += [(question, {**filters, "act_id": aid}) for aid in ref.act_ids]
        lists: list[list[Hit]] = []
        weights: list[float] = []
        for q, f in searches:
            if cfg.mode in ("dense", "hybrid"):
                assert self.dense is not None
                lists.append(self.dense.store.search(
                    self.dense.embedder.encode_queries([q])[0], k=c, filters=f))
                weights.append(dense_w)
            if cfg.mode in ("bm25", "hybrid"):
                assert self.bm25 is not None
                lists.append(self.bm25.search(q, k=c, filters=f))
                weights.append(bm25_w)

        if not lists:
            return []
        # A single list keeps its own scores (cosine / BM25); only fusion needs RRF.
        candidates = (lists[0] if len(lists) == 1
                      else reciprocal_rank_fusion(lists, weights, rrf_k=cfg.rrf_k, k=c))

        if cfg.boost_in_force:
            candidates = boost_in_force(candidates)
        if ref:
            assert self.resolver is not None
            candidates = apply_reference(candidates, ref, self.resolver)
        if max_parts:
            candidates = dedupe_by_section(candidates, max_parts=max_parts)
        if cfg.mmr_lambda is not None and self.dense is not None:
            vectors = self.dense.embedder.encode_passages([h.text for h in candidates[:c]])
            candidates = mmr(candidates[:c], vectors, k=max(k, 1), lambda_=cfg.mmr_lambda)
        if self.reranker:
            candidates = self.reranker.rerank(question, candidates[:c], k)

        hits = candidates[:k]
        if cfg.parent_context and self.parents:
            hits = expand_to_parents(hits, self.parents, max_chars=cfg.parent_max_chars)
        return hits

    def describe(self) -> dict:
        return self.config.to_dict()


def load_records(index_dir: str | Path, chunks_path: str | Path | None = None) -> list[dict]:
    """The chunk records behind an index — needed for exact lookup and parents."""
    import json

    index_dir = Path(index_dir)
    for name in ("records.jsonl", "bm25_records.jsonl"):
        path = index_dir / name
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return [json.loads(line) for line in f if line.strip()]
    if chunks_path and Path(chunks_path).exists():
        with open(chunks_path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    raise SystemExit(f"no chunk records found in {index_dir}")


def index_fingerprint(index_dir: str | Path) -> str:
    """Identity of the built index — embedder, size and build time.

    Used as part of the answer-cache key: rebuild the index at the same path and
    every cached answer is invalidated, because it is no longer an answer this
    system would give.
    """
    import hashlib
    import json

    path = Path(index_dir) / "index.json"
    if not path.exists():
        return "none"
    info = json.loads(path.read_text(encoding="utf-8"))
    info["mtime"] = int(path.stat().st_mtime)
    return hashlib.sha256(json.dumps(info, sort_keys=True).encode()).hexdigest()[:16]


# --------------------------------------------------------------------- wiring

def add_retrieval_args(ap) -> None:
    """Shared flags, so every entry point builds the same pipeline."""
    ap.add_argument("--mode", choices=["dense", "bm25", "hybrid"], default="dense")
    ap.add_argument("--dense-weight", type=float, default=1.0)
    ap.add_argument("--bm25-weight", type=float, default=1.0)
    ap.add_argument("--rrf-k", type=int, default=60)
    ap.add_argument("--candidates", type=int, default=50, help="per-source pool before fusion/rerank")
    ap.add_argument("--rerank", choices=["none", "cross", "lexical"], default="none")
    ap.add_argument("--rerank-model", default="BAAI/bge-reranker-v2-m3")
    ap.add_argument("--expand-refs", action="store_true", help="also search 'section 302' for 'ধারা ৩০২'")
    ap.add_argument("--synonyms", action="store_true", help="expand legal synonyms (উচ্ছেদ ↔ eviction)")
    ap.add_argument("--transliterate", action="store_true", help="also search a Bangla variant of romanised input")
    ap.add_argument("--route", action="store_true", help="pick fusion weights by query type")
    ap.add_argument("--multi-query", type=int, default=0, help="N LLM rewrites, fused (costs a call)")
    ap.add_argument("--hyde", action="store_true", help="embed a hypothetical provision (costs a call)")
    ap.add_argument("--mmr-lambda", type=float, help="0..1 relevance/diversity trade-off; omit to disable")
    ap.add_argument("--boost-in-force", action="store_true", help="push amended/repealed text down")
    ap.add_argument("--parent-context", action="store_true", help="answer from the whole section")
    ap.add_argument("--parent-max-chars", type=int, default=4000)
    ap.add_argument("--max-parts-per-section", type=int)
    ap.add_argument("--include-repealed", action="store_true")
    ap.add_argument("--resolve-refs", action="store_true",
                    help="look up 'দণ্ডবিধির ধারা ৩০২' directly instead of searching for it")


def build_pipeline(config, index_dir: str | Path, embedder, llm=None,
                   records: list[dict] | None = None) -> SearchPipeline:
    """Build from a RetrievalConfig (an argparse namespace is accepted too)."""
    from .store import NumpyStore

    cfg = config if isinstance(config, RetrievalConfig) else RetrievalConfig.from_args(config)
    cfg = replace(cfg, embedder=getattr(embedder, "name", cfg.embedder))
    index_dir = Path(index_dir)

    dense = None
    if cfg.mode in ("dense", "hybrid"):
        store = NumpyStore.load(index_dir)
        if embedder.dim != store.dim:
            raise SystemExit(f"index dim {store.dim} ({store.embedder_name}) "
                             f"!= embedder dim {embedder.dim} ({embedder.name}) — rebuild the index")
        dense = Retriever(embedder, store)
    bm25 = None
    if cfg.mode in ("bm25", "hybrid"):
        if not (index_dir / "bm25.json").exists():
            raise SystemExit(f"no BM25 index in {index_dir} — rebuild with: "
                             f"python scripts/build_index.py --bm25")
        bm25 = BM25Index.load(index_dir)
    parents = None
    if cfg.parent_context:
        parents = ParentIndex(records if records is not None else load_records(index_dir))
    reranker = get_reranker(cfg.rerank, model=cfg.rerank_model)
    return SearchPipeline(cfg, dense=dense, bm25=bm25, reranker=reranker, llm=llm, parents=parents)
