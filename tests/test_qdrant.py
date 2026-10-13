"""QdrantStore against NumpyStore: same records, same queries, same top-k.

NumpyStore is exact, so it is the reference. Qdrant's embedded mode
(location=":memory:") runs the real client and query path with no server.
Skipped when qdrant-client is not installed (`pip install -e ".[qdrant]"`).
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.store import NumpyStore  # noqa: E402

HAVE_QDRANT = importlib.util.find_spec("qdrant_client") is not None


def records(n, rng):
    langs = ["bn", "en", "mixed"]
    return [{"chunk_id": f"c{i}", "text": f"text {i}", "body": f"body {i}",
             "metadata": {"act_id": int(rng.integers(1, 6)), "language": langs[i % 3],
                          "repealed": bool(i % 7 == 0), "section_number": str(i)}}
            for i in range(n)]


@unittest.skipUnless(HAVE_QDRANT, "qdrant-client not installed")
class TestQdrantMatchesNumpy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from rag.store import QdrantStore

        rng = np.random.default_rng(7)
        cls.dim = 32
        cls.recs = records(300, rng)
        vectors = rng.normal(size=(300, cls.dim)).astype(np.float32)
        cls.queries = rng.normal(size=(25, cls.dim)).astype(np.float32)
        cls.numpy = NumpyStore(cls.dim)
        cls.numpy.add(vectors, cls.recs)
        cls.qdrant = QdrantStore(cls.dim, "t", location=":memory:", recreate=True)
        cls.qdrant.add(vectors[:150], cls.recs[:150])
        cls.qdrant.add(vectors[150:], cls.recs[150:])      # second batch must not overwrite

    def same(self, k, **kw):
        for q in self.queries:
            want = self.numpy.search(q, k=k, **kw)
            got = self.qdrant.search(q, k=k, **kw)
            self.assertEqual([h.chunk_id for h in got], [h.chunk_id for h in want])
            np.testing.assert_allclose([h.score for h in got], [h.score for h in want],
                                       atol=1e-4)

    def test_count_and_records(self):
        self.assertEqual(len(self.qdrant), 300)
        self.assertEqual([r["chunk_id"] for r in self.qdrant.records],
                         [r["chunk_id"] for r in self.recs])

    def test_unfiltered_top_k(self):
        self.same(10)

    def test_server_side_filters(self):
        self.same(10, filters={"language": ["bn", "mixed"], "repealed": False})
        self.same(5, filters={"act_id": 3})

    def test_callable_filters_and_where_apply_after_retrieval(self):
        self.same(10, filters={"act_id": lambda a: a in (1, 2), "repealed": False})
        self.same(5, where=lambda m: int(m["section_number"]) % 10 == 0)

    def test_open_store_reads_a_qdrant_index_json(self):
        import json

        from rag.pipeline import open_store

        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "q"
            from rag.store import QdrantStore
            built = QdrantStore(self.dim, "bdlaws", path=str(store_path), recreate=True)
            built.add(np.eye(self.dim, dtype=np.float32)[:3], self.recs[:3])
            built.client.close()
            (Path(tmp) / "index.json").write_text(json.dumps(
                {"dim": self.dim, "embedder": "x", "backend": "qdrant",
                 "collection": "bdlaws", "path": str(store_path)}), encoding="utf-8")
            store = open_store(tmp)
            self.assertEqual(type(store).__name__, "QdrantStore")
            self.assertEqual(store.search(np.eye(self.dim)[1], k=1)[0].chunk_id, "c1")
            store.client.close()


if __name__ == "__main__":
    unittest.main()
