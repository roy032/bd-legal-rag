"""Pages a public launch needs: privacy and terms, robots.txt, an installable manifest,
and a query log that does not hold visitors' IP addresses."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    from starlette.testclient import TestClient

    from service.app import ServiceConfig, create_app
    from test_service import fake_components
    HAVE_STARLETTE = True
except ImportError:                       # pragma: no cover
    HAVE_STARLETTE = False


@unittest.skipUnless(HAVE_STARLETTE, "starlette not installed")
class TestLaunchPages(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        pipeline, llm, stream = fake_components()
        self.log = Path(self._tmp.name, "queries.jsonl")
        self.c = TestClient(create_app(
            ServiceConfig(rate_per_min=6000, burst=100, analytics_path=str(self.log)),
            pipeline=pipeline, llm=llm, stream_llm=stream))

    def test_privacy_and_terms_are_served_in_both_languages(self):
        for path in ("/privacy", "/terms"):
            r = self.c.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn("Not legal advice", r.text)
            self.assertIn("এটি আইনি পরামর্শ নয়", r.text)
            self.assertIn("16430", r.text)
        self.assertIn('href="/privacy"', self.c.get("/").text)

    def test_robots_keeps_shared_answers_out_of_search(self):
        text = self.c.get("/robots.txt").text
        self.assertIn("Disallow: /a/", text)
        self.assertIn("Allow: /privacy", text)

    def test_manifest_makes_the_app_installable(self):
        r = self.c.get("/manifest.webmanifest")
        self.assertIn("manifest+json", r.headers["content-type"])
        m = r.json()
        self.assertEqual(m["start_url"], "/")
        self.assertEqual(m["display"], "standalone")
        self.assertTrue(m["icons"])

    def test_query_log_holds_a_pseudonym_not_the_ip(self):
        self.c.post("/ask", json={"question": "হত্যার শাস্তি কী?"})
        self.c.post("/ask", json={"question": "ধারা ৩০২ কী বলে?"})
        rows = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertNotIn("testclient", json.dumps(rows))
        self.assertEqual(len(rows[0]["client"]), 12)
        self.assertEqual(rows[0]["client"], rows[1]["client"])   # repeat visits still group

    def test_query_log_never_holds_an_api_key(self):
        pipeline, llm, stream = fake_components()
        c = TestClient(create_app(
            ServiceConfig(rate_per_min=6000, burst=100, analytics_path=str(self.log),
                          api_keys={"secretkey123": 60}),
            pipeline=pipeline, llm=llm, stream_llm=stream))
        c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}, headers={"x-api-key": "secretkey123"})
        self.assertNotIn("secret", self.log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
