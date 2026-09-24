"""Phase 2 tests — offline: hashing embedder + stub LLM, no network, no API key.
Run: python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from rag.answer import (  # noqa: E402
    answer_question,
    build_prompt,
    check_citations,
    format_context,
    reorder_sandwich,
)
from rag.embed import HashingEmbedder  # noqa: E402
from rag.retrieve import Retriever, dedupe_by_section  # noqa: E402
from rag.store import Hit, NumpyStore  # noqa: E402


def chunk(cid, text, **meta):
    m = {"type": "section", "act_id": 1, "act_title": "বীমা আইন, ২০১০", "act_year": 2010,
         "language": "bn", "repealed": False, "section_id": 1, "section_number": "১",
         "section_title": "", "chapter": None, "url": f"http://x/{cid}", "part": 1, "n_parts": 1}
    m.update(meta)
    return {"chunk_id": cid, "text": text, "body": text, "metadata": m}


CORPUS = [
    chunk("a", "বীমা আইন, ২০১০ > ধারা ৩০২: হত্যার শাস্তি\n\nযে ব্যক্তি হত্যা করিবে সে মৃত্যুদণ্ডে দণ্ডিত হইবে।",
          section_id=302, section_number="৩০২", section_title="হত্যার শাস্তি"),
    chunk("b", "The Penal Code, 1860 > Section 304A: Causing death by negligence\n\nWhoever causes "
               "death by a rash or negligent act shall be punished with imprisonment.",
          act_id=2, act_title="The Penal Code, 1860", act_year=1860, language="en",
          section_id=304, section_number="304A", section_title="Causing death by negligence"),
    chunk("c", "পুরাতন আইন > ধারা ৫: রহিত বিধান\n\nএই বিধান আর কার্যকর নয়।",
          act_id=3, act_title="পুরাতন বীমা আইন, ১৯৩৮", act_year=1938, repealed=True, section_id=5),
    chunk("d1", "বীমা আইন, ২০১০ > ধারা ২: সংজ্ঞা\n\n(ক) “বীমাকারী” অর্থ বীমা ব্যবসা পরিচালনাকারী।",
          section_id=2, section_number="২", section_title="সংজ্ঞা", part=1, n_parts=2),
    chunk("d2", "বীমা আইন, ২০১০ > ধারা ২: সংজ্ঞা\n\n(খ) “পলিসি” অর্থ বীমা চুক্তির দলিল।",
          section_id=2, section_number="২", section_title="সংজ্ঞা", part=2, n_parts=2),
]


def build_store():
    emb = HashingEmbedder(dim=256)
    store = NumpyStore(emb.dim, emb.name)
    store.add(emb.encode_passages([c["text"] for c in CORPUS]), CORPUS)
    return emb, store


class TestEmbedder(unittest.TestCase):
    def test_normalized_and_deterministic(self):
        emb = HashingEmbedder(dim=128)
        v = emb.encode_passages(["হত্যার শাস্তি", "murder"])
        self.assertEqual(v.shape, (2, 128))
        np.testing.assert_allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-5)
        np.testing.assert_allclose(v, emb.encode_passages(["হত্যার শাস্তি", "murder"]))

    def test_similar_text_scores_higher(self):
        emb = HashingEmbedder(dim=512)
        q = emb.encode_queries(["হত্যার শাস্তি কী"])[0]
        near = emb.encode_passages(["হত্যার শাস্তি মৃত্যুদণ্ড"])[0]
        far = emb.encode_passages(["insurance policy definitions"])[0]
        self.assertGreater(float(q @ near), float(q @ far))


class TestStore(unittest.TestCase):
    def setUp(self):
        self.emb, self.store = build_store()

    def test_search_ranks_relevant_first(self):
        hits = self.store.search(self.emb.encode_queries(["হত্যার শাস্তি"])[0], k=3)
        self.assertEqual(hits[0].chunk_id, "a")
        self.assertGreaterEqual(hits[0].score, hits[1].score)
        self.assertEqual(hits[0].citation, "বীমা আইন, ২০১০, ধারা ৩০২")

    def test_filters(self):
        q = self.emb.encode_queries(["death"])[0]
        en = self.store.search(q, k=5, filters={"language": "en"})
        self.assertTrue(all(h.metadata["language"] == "en" for h in en))
        one = self.store.search(q, k=5, filters={"act_id": 2})
        self.assertEqual({h.metadata["act_id"] for h in one}, {2})
        recent = self.store.search(q, k=5, filters={"act_year": lambda y: y and y >= 2000})
        self.assertTrue(all(h.metadata["act_year"] >= 2000 for h in recent))

    def test_k_larger_than_corpus(self):
        hits = self.store.search(self.emb.encode_queries(["x"])[0], k=99)
        self.assertEqual(len(hits), len(CORPUS))

    def test_filter_excludes_everything(self):
        hits = self.store.search(self.emb.encode_queries(["x"])[0], k=3, filters={"act_id": 999})
        self.assertEqual(hits, [])

    def test_save_load_roundtrip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.store.save(d)
            loaded = NumpyStore.load(d)
        self.assertEqual(len(loaded), len(CORPUS))
        self.assertEqual(loaded.embedder_name, self.emb.name)
        q = self.emb.encode_queries(["সংজ্ঞা"])[0]
        self.assertEqual([h.chunk_id for h in loaded.search(q, k=3)],
                         [h.chunk_id for h in self.store.search(q, k=3)])


class TestRetriever(unittest.TestCase):
    def setUp(self):
        self.emb, self.store = build_store()
        self.r = Retriever(self.emb, self.store)

    def test_repealed_excluded_by_default(self):
        ids = [h.chunk_id for h in self.r.search("রহিত বিধান", k=5)]
        self.assertNotIn("c", ids)
        self.assertIn("c", [h.chunk_id for h in self.r.search("রহিত বিধান", k=5, include_repealed=True)])

    def test_language_filter_keeps_mixed(self):
        hits = self.r.search("death", k=5, language="en")
        self.assertTrue(all(h.metadata["language"] in ("en", "mixed") for h in hits))

    def test_retriever_limits_parts_per_section(self):
        hits = self.r.search("সংজ্ঞা", k=3, max_parts_per_section=1)
        keys = [(h.metadata["act_id"], h.metadata["section_id"]) for h in hits]
        self.assertEqual(len(keys), len(set(keys)))

    def test_dedupe_by_section(self):
        hits = [Hit(c["chunk_id"], 1.0, c["text"], c["body"], c["metadata"]) for c in CORPUS]
        kept = dedupe_by_section(hits, max_parts=1)
        self.assertEqual([h.chunk_id for h in kept], ["a", "b", "c", "d1"])


class TestPromptAndCitations(unittest.TestCase):
    def setUp(self):
        self.hits = [Hit(c["chunk_id"], 0.9 - i / 10, c["text"], c["body"], c["metadata"])
                     for i, c in enumerate(CORPUS)]

    def test_context_is_numbered_from_one(self):
        ctx = format_context(self.hits[:2])
        self.assertIn("[1] বীমা আইন, ২০১০, ধারা ৩০২", ctx)
        self.assertIn("[2] The Penal Code, 1860, section 304A", ctx)

    def test_sandwich_puts_best_at_the_ends(self):
        order = [h.chunk_id for h in reorder_sandwich(self.hits)]
        self.assertEqual(order[0], "a")   # best
        self.assertEqual(order[-1], "b")  # second best
        self.assertEqual(sorted(order), sorted(h.chunk_id for h in self.hits))

    def test_prompt_language_reminder(self):
        self.assertIn("বাংলায়", build_prompt("হত্যার শাস্তি কী?", self.hits[:2]))
        self.assertIn("in English", build_prompt("What is the punishment?", self.hits[:2]))

    def test_check_citations(self):
        valid, invalid = check_citations("Murder is punishable [1], see also [2] and [9].", 5)
        self.assertEqual(valid, [1, 2])
        self.assertEqual(invalid, [9])


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.emb, self.store = build_store()
        self.r = Retriever(self.emb, self.store)

    def test_grounded_answer_reports_sources(self):
        def fake_llm(system, prompt):
            self.assertIn("ONLY from the numbered excerpts", system)
            self.assertIn("[1]", prompt)
            return "হত্যার শাস্তি মৃত্যুদণ্ড [1]।"

        ans = answer_question("হত্যার শাস্তি কী?", self.r, fake_llm, k=3)
        self.assertFalse(ans.refused)
        self.assertEqual(ans.cited, [1])
        self.assertEqual(ans.sources[0]["chunk_id"], "a")
        self.assertEqual(ans.invalid_citations, [])
        self.assertGreater(ans.latency_s, 0)

    def test_refusal_is_detected(self):
        ans = answer_question("What is the VAT rate?", self.r,
                              lambda s, p: "NOT_FOUND: no provision on VAT in the excerpts.", k=3)
        self.assertTrue(ans.refused)
        self.assertEqual(ans.sources, [])

    def test_citation_numbers_match_answer_hits(self):
        """A [n] in the answer must point at Answer.hits[n-1] even after reordering."""
        captured = {}

        def fake_llm(system, prompt):
            captured["prompt"] = prompt
            return "See [1] and [3]."

        ans = answer_question("সংজ্ঞা কী?", self.r, fake_llm, k=4, sandwich=True)
        for n in ans.cited:
            head = f"[{n}] {ans.hits[n - 1].citation}"
            self.assertIn(head, captured["prompt"])

    def test_empty_index_refuses(self):
        empty = Retriever(self.emb, NumpyStore(self.emb.dim))
        ans = answer_question("anything", empty, lambda s, p: "should not be called")
        self.assertTrue(ans.refused)


if __name__ == "__main__":
    unittest.main()
