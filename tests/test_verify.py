"""Live verification of cited sections (rag/verify.py)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.store import Hit  # noqa: E402
from rag.verify import verify_cited  # noqa: E402

PAGE = ('<div class="txt-head">Punishment for murder</div>'
        '<div class="txt-details">302. Whoever commits murder shall be punished with death.</div>')
META = {"type": "section", "act_id": 11, "act_title": "The Penal Code, 1860", "section_id": 3131,
        "section_number": "302", "section_number_ascii": "302", "section_title": "Punishment for murder",
        "url": "http://bdlaws.minlaw.gov.bd/act-11/section-3131.html", "language": "en"}


class Fake:
    def __init__(self, html=None, fail=False):
        self.html, self.fail, self.calls = html, fail, []

    def get(self, url, refresh=False):
        self.calls.append((url, refresh))
        if self.fail:
            raise RuntimeError("site down")
        return self.html


class TestVerify(unittest.TestCase):
    def hit(self, body):
        return Hit("11-3131-1", 1.0, body, body, META)

    def test_current_changed_unavailable(self):
        same = self.hit("302. Whoever commits murder shall be punished with death.")
        old = self.hit("302. Whoever commits murder shall be punished with transportation.")
        fetch = Fake(PAGE)
        self.assertEqual(verify_cited([same, old], [1, 2], fetch), {1: "current", 2: "changed"})
        self.assertTrue(all(refresh for _, refresh in fetch.calls))       # always the live page
        self.assertEqual(verify_cited([same], [1], Fake(fail=True)), {1: "unavailable"})

    def test_only_cited_and_bounded(self):
        hits = [self.hit("x")] * 5
        self.assertEqual(verify_cited(hits, [], Fake(PAGE)), {})
        self.assertEqual(len(verify_cited(hits, [1, 2, 3, 4, 5], Fake(PAGE), max_checks=2)), 2)


if __name__ == "__main__":
    unittest.main()
