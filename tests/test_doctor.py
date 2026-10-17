"""`bdrag doctor`: each check, with no network and no models."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.doctor import FAIL, OK, WARN, check_index, check_llm, run  # noqa: E402


class FakeResponse:
    def __init__(self, models):
        self.models = models

    def json(self):
        return {"models": [{"name": m} for m in self.models]}


class TestDoctor(unittest.TestCase):
    def test_index_present_missing_and_bm25_only(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(check_index(d).status, FAIL)
            (Path(d) / "bm25.json").write_text("{}")
            self.assertEqual(check_index(d).status, WARN)
            (Path(d) / "index.json").write_text(json.dumps({"count": 43966, "embedder": "BAAI/bge-m3", "dim": 1024}))
            self.assertEqual(check_index(d).status, FAIL)          # vectors.npy missing
            (Path(d) / "vectors.npy").write_bytes(b"")
            c = check_index(d)
            self.assertEqual(c.status, OK)
            self.assertIn("43,966 chunks", c.detail)

    def test_sample_index_needs_no_sentence_transformers(self):
        checks = {c.name: c for c in run(str(ROOT / "data/sample/index"))}
        self.assertEqual(checks["index"].status, OK)
        self.assertNotEqual(checks["embedder"].status, FAIL)
        self.assertNotIn("embedding model", checks)

    def test_ollama_model_pulled_or_not(self):
        env = {"RAG_LLM": "ollama", "RAG_MODEL": "gemma4:e4b"}
        ok = check_llm(env, get=lambda url, timeout: FakeResponse(["gemma4:e4b"]))[0]
        self.assertEqual(ok.status, OK)
        missing = check_llm(env, get=lambda url, timeout: FakeResponse(["qwen2.5:7b"]))[0]
        self.assertEqual(missing.status, FAIL)
        self.assertEqual(missing.fix, "ollama pull gemma4:e4b")

    def test_ollama_down(self):
        def down(url, timeout):
            raise ConnectionError("refused")
        c = check_llm({"RAG_LLM": "ollama"}, get=down)[0]
        self.assertEqual(c.status, FAIL)
        self.assertIn("not reachable", c.detail)

    def test_hosted_key_is_checked_never_printed(self):
        c = check_llm({"RAG_LLM": "groq", "RAG_MODEL": "llama-3.3-70b-versatile", "GROQ_API_KEY": "gsk_secret"})[0]
        self.assertEqual(c.status, OK)
        self.assertNotIn("gsk_secret", c.line())
        self.assertEqual(check_llm({"RAG_LLM": "gemini"})[0].status, FAIL)

    def test_no_provider_is_a_warning(self):
        self.assertEqual(check_llm({})[0].status, WARN)


if __name__ == "__main__":
    unittest.main()
