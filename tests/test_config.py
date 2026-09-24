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


class TestAutoEmbedder(unittest.TestCase):
    def test_auto_follows_the_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "index.json").write_text(json.dumps({"embedder": "hashing-256", "dim": 256}))
            emb = get_embedder("auto", index_dir=tmp)
        self.assertIsInstance(emb, HashingEmbedder)
        self.assertEqual(emb.dim, 256)


if __name__ == "__main__":
    unittest.main()
