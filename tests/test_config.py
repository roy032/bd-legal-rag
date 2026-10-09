"""Service configuration and small operational defaults."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from service.app import ServiceConfig, _client
    HAVE_STARLETTE = True
except ImportError:          # starlette is an optional extra
    HAVE_STARLETTE = False

from rag.embed import HashingEmbedder, get_embedder  # noqa: E402


@unittest.skipUnless(HAVE_STARLETTE, "starlette not installed")
class TestServiceConfig(unittest.TestCase):
    def test_empty_env_values_mean_unset(self):
        env = {"BDRAG_MIN_SCORE": "", "BDRAG_MMR": "", "BDRAG_K": "", "RAG_LLM": "",
               "BDRAG_RATE_PER_MIN": ""}
        with mock.patch.dict(os.environ, env, clear=False):
            cfg = ServiceConfig.from_env()
        self.assertIsNone(cfg.min_score)
        self.assertIsNone(cfg.retrieval.mmr_lambda)
        self.assertEqual(cfg.k, 5)
        self.assertIsNone(cfg.provider)
        self.assertEqual(cfg.rate_per_min, 20)

    def test_env_values_are_read(self):
        with mock.patch.dict(os.environ, {"BDRAG_MIN_SCORE": "0.02", "BDRAG_RESOLVE_REFS": "false"}):
            cfg = ServiceConfig.from_env()
        self.assertEqual(cfg.min_score, 0.02)
        self.assertFalse(cfg.retrieval.resolve_refs)

    def test_logging_is_off_unless_configured(self):
        cfg = ServiceConfig()
        self.assertEqual((cfg.analytics_path, cfg.feedback_path), ("", ""))
        self.assertEqual(ServiceConfig.from_env().analytics_path, "data/queries.jsonl")

    def test_forwarded_for_is_ignored_by_default(self):
        class Req:
            headers = {"x-forwarded-for": "1.2.3.4"}

            class client:
                host = "10.0.0.9"
        self.assertEqual(_client(Req()), "10.0.0.9")
        self.assertEqual(_client(Req(), trust_proxy=True), "1.2.3.4")


@unittest.skipUnless(HAVE_STARLETTE, "starlette not installed")
class TestLazyBuild(unittest.TestCase):
    def test_concurrent_first_requests_load_the_models_once(self):
        """Parallel first requests used to load bge-m3 once each and run out of memory."""
        import threading
        from unittest import mock as m

        from service.app import create_app
        calls = []

        def slow_embedder(*a, **kw):
            calls.append(1)
            import time
            time.sleep(0.2)

        cfg = ServiceConfig(rate_per_min=6000, burst=100, preload=False)
        with m.patch("rag.embed.embedder_for", slow_embedder), \
             m.patch("rag.pipeline.load_records", lambda *a, **k: []), \
             m.patch("rag.pipeline.build_pipeline", lambda *a, **k: object()), \
             m.patch("rag.llm.get_llm", lambda *a, **k: None), \
             m.patch("rag.llm.get_stream_llm", lambda *a, **k: None), \
             m.patch("service.app.index_fingerprint", lambda *a: "x"):
            build = create_app(cfg).state.build
            threads = [threading.Thread(target=build) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(len(calls), 1)


class TestAutoEmbedder(unittest.TestCase):
    def test_auto_follows_the_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "index.json").write_text(json.dumps({"embedder": "hashing-256", "dim": 256}))
            emb = get_embedder("auto", index_dir=tmp)
        self.assertIsInstance(emb, HashingEmbedder)
        self.assertEqual(emb.dim, 256)


if __name__ == "__main__":
    unittest.main()


class TestOllamaHost(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop("OLLAMA_HOST", None)

    def tearDown(self):
        os.environ.pop("OLLAMA_HOST", None)
        if self._saved is not None:
            os.environ["OLLAMA_HOST"] = self._saved

    def test_default_is_ipv4_loopback(self):
        # "localhost" costs ~2 s per request on Windows (IPv6 tried first)
        from rag.llm import ollama_host
        self.assertEqual(ollama_host(), "http://127.0.0.1:11434")

    def test_env_without_scheme_and_bind_all_address(self):
        from rag.llm import ollama_host
        os.environ["OLLAMA_HOST"] = "0.0.0.0:11434"
        self.assertEqual(ollama_host(), "http://127.0.0.1:11434")
        os.environ["OLLAMA_HOST"] = "https://ollama.example.com/"
        self.assertEqual(ollama_host(), "https://ollama.example.com")
