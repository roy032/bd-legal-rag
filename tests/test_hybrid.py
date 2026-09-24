"""Phase 4 tests: BM25, fusion, reranking, query expansion, pipeline wiring."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from rag.embed import HashingEmbedder  # noqa: E402
from rag.fusion import reciprocal_rank_fusion  # noqa: E402
from rag.lexical import BM25Index, tokenize  # noqa: E402
from rag.pipeline import RetrievalConfig, SearchPipeline  # noqa: E402
from rag.query import expand_section_refs, hyde, multi_query  # noqa: E402
from rag.rerank import LexicalOverlapReranker  # noqa: E402
from rag.retrieve import Retriever  # noqa: E402
from rag.store import Hit, NumpyStore  # noqa: E402
from test_rag import CORPUS, chunk  # noqa: E402

# One extra doc whose only link to the query is an exact section number —
# the case dense embeddings are worst at.
EXACT = chunk("e", "The Penal Code, 1860 > Section 304A: Causing death by negligence\n\n"
                   "Whoever causes the death of any person by doing any rash or negligent act...",
              act_id=2, act_title="The Penal Code, 1860", language="en", section_id=304,
              section_number="304A")
DOCS = CORPUS + [EXACT]


def hit(cid, score=1.0, meta=None):
    return Hit(cid, score, "t", "b", meta or {"act_id": 1, "section_id": 1})


class TestTokenizer(unittest.TestCase):
    def test_folds_bangla_digits_and_drops_punctuation(self):
        self.assertEqual(tokenize("ধারা ৩০২।"), ["ধারা", "302"])
        self.assertEqual(tokenize("Section 304A, 1860."), ["section", "304a", "1860"])

    def test_stemmer_only_touches_long_bangla_words(self):
        self.assertEqual(tokenize("ধারায় ধারার", stem=True), ["ধারা", "ধারা"])
        self.assertEqual(tokenize("murder cases", stem=True), ["murder", "cases"])  # English untouched
        self.assertEqual(tokenize("রা", stem=True), ["রা"])                          # too short to strip


class TestBM25(unittest.TestCase):
    def setUp(self):
        self.idx = BM25Index()
        self.idx.add(DOCS)

    def test_exact_section_number_wins(self):
        hits = self.idx.search("section 304A", k=2)
        self.assertIn(hits[0].chunk_id, ("b", "e"))
        self.assertGreater(hits[0].score, 0)

    def test_bangla_query_matches_bangla_doc(self):
        self.assertEqual(self.idx.search("হত্যার শাস্তি", k=1)[0].chunk_id, "a")

    def test_rare_terms_outweigh_common_ones(self):
        common = self.idx.idf("বীমা") if "বীমা" in self.idx.postings else 0
        rare = self.idx.idf("হত্যা") if "হত্যা" in self.idx.postings else 0
        self.assertGreaterEqual(max(rare, common), 0)
        self.assertEqual(self.idx.idf("nonexistentterm"), 0.0)

    def test_unknown_query_returns_nothing(self):
        self.assertEqual(self.idx.search("zzzzz qqqqq", k=5), [])

    def test_filters(self):
        hits = self.idx.search("death", k=5, filters={"language": "en"})
        self.assertTrue(hits and all(h.metadata["language"] == "en" for h in hits))

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            self.idx.save(d)
            loaded = BM25Index.load(d)
        self.assertEqual(len(loaded), len(DOCS))
        self.assertEqual([h.chunk_id for h in loaded.search("হত্যার শাস্তি", k=3)],
                         [h.chunk_id for h in self.idx.search("হত্যার শাস্তি", k=3)])


class TestFusion(unittest.TestCase):
    def test_document_liked_by_both_lists_wins(self):
        dense = [hit("x"), hit("shared"), hit("y")]
        lexical = [hit("z"), hit("shared"), hit("w")]
        fused = reciprocal_rank_fusion([dense, lexical], k=3)
        self.assertEqual(fused[0].chunk_id, "shared")   # 2nd in both beats 1st in one

    def test_weights_shift_the_winner(self):
        dense = [hit("d1"), hit("d2")]
        lexical = [hit("l1"), hit("l2")]
        self.assertEqual(reciprocal_rank_fusion([dense, lexical], [0.1, 1.0], k=1)[0].chunk_id, "l1")
        self.assertEqual(reciprocal_rank_fusion([dense, lexical], [1.0, 0.1], k=1)[0].chunk_id, "d1")

    def test_rrf_k_trades_top_rank_against_agreement(self):
        # "top" is rank 1 in one list only; "both" is rank 10 in each list.
        a = [hit("top")] + [hit(f"x{i}") for i in range(8)] + [hit("both")]
        b = [hit(f"y{i}") for i in range(9)] + [hit("both")]
        sharp = reciprocal_rank_fusion([a, b], rrf_k=1, k=2)
        flat = reciprocal_rank_fusion([a, b], rrf_k=1000, k=2)
        self.assertEqual(sharp[0].chunk_id, "top")    # small rrf_k: being rank 1 dominates
        self.assertEqual(flat[0].chunk_id, "both")    # large rrf_k: agreement dominates

    def test_mismatched_weights_rejected(self):
        with self.assertRaises(ValueError):
            reciprocal_rank_fusion([[hit("a")], [hit("b")]], [1.0])


class TestReranker(unittest.TestCase):
    def test_reorders_by_query_overlap(self):
        hits = [Hit("far", 0.9, "বীমা পলিসির সংজ্ঞা", "b", {}),
                Hit("near", 0.1, "হত্যার শাস্তি মৃত্যুদণ্ড", "b", {})]
        out = LexicalOverlapReranker().rerank("হত্যার শাস্তি কী?", hits, k=2)
        self.assertEqual(out[0].chunk_id, "near")      # rescued from last place
        self.assertEqual(len(out), 2)

    def test_empty_and_k_limit(self):
        r = LexicalOverlapReranker()
        self.assertEqual(r.rerank("q", [], k=5), [])
        self.assertEqual(len(r.rerank("হত্যা", [hit("a"), hit("b"), hit("c")], k=2)), 2)


class TestQueryTransforms(unittest.TestCase):
    def test_expansion_adds_both_spellings(self):
        out = expand_section_refs("ধারা ৩০২ এ কী আছে?")
        self.assertIn("section 302", out)
        self.assertIn("ধারা 302", out)

    def test_expansion_is_a_no_op_without_a_reference(self):
        q = "ভাড়াটিয়া উচ্ছেদ কীভাবে হয়?"
        self.assertEqual(expand_section_refs(q), q)

    def test_multi_query_parses_lines_and_keeps_original_first(self):
        out = multi_query("হত্যার শাস্তি কী?", lambda s, p: "শাস্তি কত?\n- মৃত্যুদণ্ড কখন?", n=2)
        self.assertEqual(out[0], "হত্যার শাস্তি কী?")
        self.assertIn("মৃত্যুদণ্ড কখন?", out)

    def test_llm_failure_degrades_gracefully(self):
        def boom(s, p):
            raise RuntimeError("no api key")
        self.assertEqual(multi_query("q", boom), ["q"])
        self.assertEqual(hyde("q", boom), "q")


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.emb = HashingEmbedder(dim=256)
        store = NumpyStore(self.emb.dim, self.emb.name)
        store.add(self.emb.encode_passages([c["text"] for c in DOCS]), DOCS)
        self.dense = Retriever(self.emb, store)
        self.bm25 = BM25Index()
        self.bm25.add(DOCS)

    def pipe(self, **cfg):
        return SearchPipeline(RetrievalConfig(**cfg), dense=self.dense, bm25=self.bm25,
                              reranker=cfg.pop("_reranker", None))

    def test_dense_only_keeps_cosine_scores(self):
        hits = self.pipe(mode="dense").search("হত্যার শাস্তি", k=2)
        self.assertEqual(hits[0].chunk_id, "a")
        self.assertLessEqual(hits[0].score, 1.0)       # cosine, not an RRF score

    def test_hybrid_requires_a_bm25_index(self):
        with self.assertRaises(ValueError):
            SearchPipeline(RetrievalConfig(mode="hybrid"), dense=self.dense, bm25=None)

    def test_hybrid_finds_what_each_alone_may_miss(self):
        hits = self.pipe(mode="hybrid").search("section 304A", k=3)
        self.assertTrue({h.chunk_id for h in hits} & {"b", "e"})

    def test_filters_apply_to_both_branches(self):
        hits = self.pipe(mode="hybrid").search("রহিত বিধান", k=5)
        self.assertNotIn("c", [h.chunk_id for h in hits])                    # repealed excluded
        hits2 = self.pipe(mode="hybrid", include_repealed=True).search("রহিত বিধান", k=5)
        self.assertIn("c", [h.chunk_id for h in hits2])

    def test_language_filter(self):
        hits = self.pipe(mode="hybrid").search("death", k=5, language="en")
        self.assertTrue(all(h.metadata["language"] in ("en", "mixed") for h in hits))

    def test_dedupe_limits_parts_of_one_section(self):
        hits = self.pipe(mode="dense", max_parts_per_section=1).search("সংজ্ঞা", k=3)
        keys = [(h.metadata["act_id"], h.metadata["section_id"]) for h in hits]
        self.assertEqual(len(keys), len(set(keys)))

    def test_reranker_is_applied_last(self):
        p = SearchPipeline(RetrievalConfig(mode="dense", candidates=5), dense=self.dense,
                           reranker=LexicalOverlapReranker())
        hits = p.search("হত্যার শাস্তি মৃত্যুদণ্ড", k=2)
        self.assertEqual(hits[0].chunk_id, "a")

    def test_multi_query_uses_the_llm_and_fuses(self):
        calls = []

        def fake_llm(system, prompt):
            calls.append(prompt)
            return "হত্যার দণ্ড\nমৃত্যুদণ্ড"

        p = SearchPipeline(RetrievalConfig(mode="dense", multi_query=2), dense=self.dense,
                           llm=fake_llm)
        hits = p.search("হত্যার শাস্তি কী?", k=2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(hits[0].chunk_id, "a")

    def test_k_is_respected_everywhere(self):
        for mode in ("dense", "bm25", "hybrid"):
            self.assertLessEqual(len(self.pipe(mode=mode).search("ধারা", k=2)), 2)


if __name__ == "__main__":
    unittest.main()
