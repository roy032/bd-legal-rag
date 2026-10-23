"""Shared answers: links that outlive a restart, expire on schedule, and preview well."""
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from service.answers import AnswerStore  # noqa: E402

try:
    from starlette.testclient import TestClient

    from service.app import ServiceConfig, create_app, share_page
    from test_service import fake_components
    HAVE_STARLETTE = True
except ImportError:                       # pragma: no cover
    HAVE_STARLETTE = False


class TestAnswerStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self._tmp.name, "sub", "answers.sqlite3"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_answer_survives_a_restart(self):
        first = AnswerStore(self.db)
        first.put("abc", {"question": "হত্যার শাস্তি কী?", "answer": "মৃত্যুদণ্ড"})
        first.close()
        again = AnswerStore(self.db)
        self.addCleanup(again.close)
        self.assertTrue(again.durable)
        self.assertEqual(again.get("abc")["answer"], "মৃত্যুদণ্ড")
        self.assertIsNone(again.get("nope"))

    def test_old_answers_expire_and_are_purged(self):
        store = AnswerStore(self.db, max_age_days=1)
        self.addCleanup(store.close)
        store.put("old", {"created": time.time() - 2 * 86400, "answer": "x"})
        store.put("new", {"answer": "y"})
        self.assertIsNone(store.get("old"))
        self.assertEqual(store.purge(), 1)
        self.assertEqual(len(store), 1)
        forever = AnswerStore(self.db, max_age_days=0)
        self.addCleanup(forever.close)
        self.assertEqual(forever.get("new")["answer"], "y")

    def test_memory_store_is_bounded(self):
        store = AnswerStore("", max_memory=3)
        self.assertFalse(store.durable)
        for i in range(5):
            store.put(str(i), {"answer": i})
        self.assertEqual(len(store), 3)
        self.assertIsNone(store.get("0"))
        self.assertEqual(store.get("4")["answer"], 4)

    def test_unwritable_path_falls_back_to_memory(self):
        blocker = Path(self._tmp.name, "file")
        blocker.write_text("not a directory")
        store = AnswerStore(str(blocker / "answers.sqlite3"))
        self.assertFalse(store.durable)
        store.put("a", {"answer": 1})
        self.assertEqual(store.get("a")["answer"], 1)


@unittest.skipUnless(HAVE_STARLETTE, "starlette not installed")
class TestSharedLinks(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self._tmp.name, "answers.sqlite3"))

    def tearDown(self):
        self._tmp.cleanup()

    def app(self):
        pipeline, llm, stream = fake_components()
        app = create_app(ServiceConfig(rate_per_min=6000, burst=100, answers_path=self.db),
                         pipeline=pipeline, llm=llm, stream_llm=stream)
        self.addCleanup(app.state.recent.close)
        return app

    def test_link_works_after_a_restart(self):
        first = TestClient(self.app()).post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()
        self.assertIsInstance(first["created"], int)
        again = TestClient(self.app()).get(f"/a/{first['id']}?format=json")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["answer"], first["answer"])

    def test_link_preview_names_the_question_and_is_not_indexed(self):
        c = TestClient(self.app())
        answer_id = c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()["id"]
        page = c.get(f"/a/{answer_id}", headers={"accept": "text/html"}).text
        self.assertIn("<title>হত্যার শাস্তি কী? · Bangladesh Law Assistant</title>", page)
        self.assertIn('og:title" content="হত্যার শাস্তি কী?', page)
        self.assertIn('<meta name="robots" content="noindex">', page)
        missing = c.get("/a/deadbeef00", headers={"accept": "text/html"})
        self.assertEqual(missing.status_code, 200)        # the page says it expired
        self.assertIn("noindex", missing.text)

    def test_preview_escapes_the_question(self):
        page = share_page({"question": '"><script>alert(1)</script> \\1', "answer": "a [1] **b**"})
        self.assertNotIn("<script>alert", page)
        self.assertIn("&quot;&gt;&lt;script&gt;", page)
        self.assertIn("\\1", page)
        self.assertIn('name="description" content="a b"', page)


if __name__ == "__main__":
    unittest.main()
