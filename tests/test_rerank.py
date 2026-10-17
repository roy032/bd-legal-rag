"""CrossEncoderReranker's CPU speed-ups, with a stand-in for the model (no download)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag import rerank  # noqa: E402
from rag.store import Hit  # noqa: E402


class FakeCrossEncoder:
    def __init__(self, *a, **kw):
        self.calls: list[list[tuple[str, str]]] = []

    def predict(self, pairs, batch_size=8, show_progress_bar=False):
        self.calls.append(list(pairs))
        return [float(len(t)) for _, t in pairs]          # longer text = more relevant


def hit(cid: str, text: str) -> Hit:
    return Hit(cid, 0.0, text, text, {})


def make(**kw) -> rerank.CrossEncoderReranker:
    fake = types_module()
    with mock.patch.dict(sys.modules, {"sentence_transformers": fake}):
        return rerank.CrossEncoderReranker(precision="fp32", **kw)


def types_module():
    import types

    m = types.ModuleType("sentence_transformers")
    m.CrossEncoder = FakeCrossEncoder  # type: ignore[attr-defined]
    return m


class TestCrossEncoderReranker(unittest.TestCase):
    def test_ranks_by_score_and_keeps_k(self):
        r = make()
        out = r.rerank("q", [hit("a", "x"), hit("b", "xxx"), hit("c", "xx")], k=2)
        self.assertEqual([h.chunk_id for h in out], ["b", "c"])

    def test_scores_shortest_first_and_caches(self):
        r = make()
        hits = [hit("a", "xxxx"), hit("b", "x"), hit("c", "xx")]
        r.rerank("q", hits, k=3)
        self.assertEqual([t for _, t in r.model.calls[0]], ["x", "xx", "xxxx"])
        r.rerank("q", hits + [hit("d", "xxx")], k=4)
        self.assertEqual([t for _, t in r.model.calls[1]], ["xxx"])     # only the new one
        r.rerank("another question", hits, k=3)
        self.assertEqual(len(r.model.calls[2]), 3)                       # cache is per query

    def test_cache_is_bounded(self):
        r = make(cache_size=2)
        r.rerank("q", [hit("a", "x"), hit("b", "xx"), hit("c", "xxx")], k=3)
        self.assertEqual(len(r._cache), 2)

    def test_precision_resolution(self):
        with mock.patch.object(rerank, "cpu_has_bf16", return_value=True):
            self.assertEqual(rerank.resolve_precision("auto"), "bf16")
            self.assertEqual(rerank.resolve_precision("auto", device="cuda"), "fp32")
        with mock.patch.object(rerank, "cpu_has_bf16", return_value=False):
            self.assertEqual(rerank.resolve_precision("auto"), "fp32")
        self.assertEqual(rerank.resolve_precision("int8"), "int8")
        with self.assertRaises(ValueError):
            rerank.resolve_precision("fp8")


if __name__ == "__main__":
    unittest.main()


class TestTranslateQuery(unittest.TestCase):
    def test_translates_into_the_other_script(self):
        from rag.query import script_language, translate_query

        self.assertEqual(script_language("ধারা ৩০২ কী বলে?"), "bn")
        self.assertEqual(script_language("dhara 302 ki bole"), "en")
        llm = mock.Mock(return_value="ভোক্তা-অধিকার কী?\n")
        self.assertEqual(translate_query("What are consumer rights?", llm), "ভোক্তা-অধিকার কী?")
        self.assertIn("Bangla", llm.call_args[0][1])

    def test_failures_and_echoes_give_none(self):
        from rag.query import translate_query

        self.assertIsNone(translate_query("What is bail?", mock.Mock(side_effect=RuntimeError)))
        self.assertIsNone(translate_query("What is bail?", mock.Mock(return_value="What is bail?")))
        self.assertIsNone(translate_query("What is bail?", mock.Mock(return_value="Bail means...")))

    def test_pipeline_searches_the_translation_but_not_for_named_sections(self):
        from rag.pipeline import RetrievalConfig, SearchPipeline

        dense = mock.Mock()
        dense.store.records = []
        llm = mock.Mock(return_value="ভোক্তা অধিকার")
        p = SearchPipeline(RetrievalConfig(translate=True), dense=dense, llm=llm)
        self.assertIn("ভোক্তা অধিকার", p.queries("consumer rights"))
        p = SearchPipeline(RetrievalConfig(translate=True, resolve_refs=True),
                           dense=dense, llm=llm)
        llm.reset_mock()
        p.queries("What does section 302 say?")
        llm.assert_not_called()


class TestOllamaSpeed(unittest.TestCase):
    def test_keep_alive_sent_and_warm_up(self):
        from rag import llm

        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"response": "ok"}
        with mock.patch("requests.post", return_value=resp) as post:
            self.assertEqual(llm.ollama_llm("m")("s", "p"), "ok")
            self.assertEqual(post.call_args.kwargs["json"]["keep_alive"], llm.OLLAMA_KEEP_ALIVE)
            self.assertTrue(llm.warm_up("ollama", "m"))
            self.assertNotIn("prompt", post.call_args.kwargs["json"])
        self.assertFalse(llm.warm_up("groq"))

    def test_excerpt_length_is_capped(self):
        from rag.answer import format_context

        h = Hit("1:1", 1.0, "x" * 3000, "x" * 3000, {"act_title": "A", "section_number": "1"})
        self.assertLess(len(format_context([h], max_chars=500)), 600)


class TestAmendmentLabel(unittest.TestCase):
    def test_latest_year_from_footnotes(self):
        from rag.answer import amendment_label, source_card

        self.assertIsNone(amendment_label({"amended": False}))
        self.assertEqual(amendment_label({"amended": True}), "amended")
        meta = {"amended": True, "footnotes": [
            "১ দফা (ঙ) বীমা (সংশোধন) আইন, ২০১৯ দ্বারা প্রতিস্থাপিত।",
            "2 Substituted by the Insurance (Amendment) Act, 2012 (Act No. V of 2012)"]}
        self.assertEqual(amendment_label(meta), "amended (latest 2019)")
        card = source_card(1, Hit("1:1", 0.5, "t", "body", {**meta, "url": "u", "act_title": "A"}))
        self.assertEqual((card["amended"], card["text"], card["repealed"]),
                         ("amended (latest 2019)", "body", False))
