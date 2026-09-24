"""On-disk formats: compressed page cache and compact index files."""
import gzip
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.fetch import Fetcher, compact_cache  # noqa: E402
from rag import jsonio  # noqa: E402
from rag.embed import HashingEmbedder  # noqa: E402
from rag.lexical import BM25Index  # noqa: E402
from rag.store import NumpyStore  # noqa: E402

RECORDS = [{"chunk_id": f"c{i}", "text": f"ধারা {i} বীমা text {i}", "body": f"body {i}",
            "metadata": {"act_id": 1, "section_id": i}} for i in range(5)]


class TestJsonIO(unittest.TestCase):
    def test_roundtrip_and_legacy_plain_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp, "r.jsonl")
            written = jsonio.write_jsonl(p, RECORDS)
            self.assertEqual(written.name, "r.jsonl.gz")
            self.assertEqual(jsonio.read_jsonl(p), RECORDS)
            jsonio.write_jsonl(p, RECORDS[:2], compress=False)     # replaces the .gz twin
            self.assertFalse(Path(tmp, "r.jsonl.gz").exists())
            self.assertEqual(jsonio.read_jsonl(p), RECORDS[:2])


class TestCompactIndex(unittest.TestCase):
    def test_one_copy_of_records_and_shared_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            emb = HashingEmbedder(dim=64)
            store = NumpyStore(64, emb.name)
            store.add(emb.encode_passages([r["text"] for r in RECORDS]), RECORDS)
            store.save(tmp)
            bm25 = BM25Index()
            bm25.add(RECORDS)
            bm25.save(tmp, write_records=False)
            names = sorted(p.name for p in Path(tmp).iterdir())
            self.assertEqual(names, ["bm25.json.gz", "index.json", "records.jsonl.gz", "vectors.npy"])
            loaded = NumpyStore.load(tmp)
            again = BM25Index.load(tmp, records=loaded.records)
            self.assertIs(again.records, loaded.records)
            self.assertEqual(BM25Index.load(tmp).records, RECORDS)   # falls back to records.jsonl
            self.assertEqual(again.search("বীমা 3", k=1)[0].chunk_id, "c3")
            top = loaded.search(emb.encode_queries(["ধারা 2 বীমা text 2"])[0], k=1)
            self.assertEqual(top[0].chunk_id, "c2")


class TestPageCache(unittest.TestCase):
    def test_reads_gzip_and_legacy_pages_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Fetcher(cache_dir=tmp, offline=True)
            url_a = "http://bdlaws.minlaw.gov.bd/act-1.html"
            url_b = "http://bdlaws.minlaw.gov.bd/act-2.html"
            f._cache_path(url_a).write_text("<p>plain</p>", encoding="utf-8")
            gz = f._cache_path(url_b)
            with gzip.open(gz.with_name(gz.name + ".gz"), "wt", encoding="utf-8") as fh:
                fh.write("<p>zipped</p>")
            self.assertEqual(f.get(url_a), "<p>plain</p>")
            self.assertEqual(f.get(url_b), "<p>zipped</p>")
            with self.assertRaises(FileNotFoundError):
                f.get("http://bdlaws.minlaw.gov.bd/act-3.html")
            n, _, _ = compact_cache(tmp)
            self.assertEqual(n, 1)
            self.assertEqual(f.get(url_a), "<p>plain</p>")        # now served from .gz
            self.assertEqual(list(Path(tmp).glob("*.html")), [])


if __name__ == "__main__":
    unittest.main()
