"""Verifiable answers: the claim map, the highlighted clauses, provenance, the
acts list, and what the service returns for each kind of answer."""
import gzip
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from ingest.fetch import Fetcher  # noqa: E402
from rag.answer import Answer, source_card  # noqa: E402
from rag.evidence import (  # noqa: E402
    act_url,
    acts_table,
    best_clause,
    claim_map,
    evidence_spans,
    numbers_in,
    provenance,
    summarize,
    verdict,
)
from rag.store import Hit  # noqa: E402
from test_rag import CORPUS  # noqa: E402

HITS = [Hit(r["chunk_id"], 1.0, r["text"], r["body"], r["metadata"]) for r in CORPUS]
# HITS[0]: বীমা আইন, ২০১০, ধারা ৩০২ (murder, Bangla); HITS[1]: Penal Code s.304A (English)


def hit(body, **meta):
    m = {"type": "section", "act_id": 9, "act_title": "The Test Act, 2001", "language": "en",
         "section_number": "5", "section_title": "Penalty", **meta}
    return Hit("t", 1.0, body, body, m)


class TestClaimMap(unittest.TestCase):
    def test_statuses(self):
        text = ("Whoever causes death by a rash or negligent act shall be punished with imprisonment [2]. "
                "The fine is Tk 50,000 [2]. Courts usually grant bail quickly.\n\n"
                "যে ব্যক্তি হত্যা করিবে সে মৃত্যুদণ্ডে দণ্ডিত হইবে [1]।")
        rows = claim_map(text, HITS)
        self.assertEqual([r["status"] for r in rows], ["linked", "check", "uncited", "linked"])
        self.assertIn("50000", rows[1]["why"])
        self.assertEqual(rows[0]["cites"], [2])
        self.assertFalse(rows[0]["text"].endswith(" ."))          # citation removed cleanly

    def test_wrong_excerpt_needs_checking(self):
        rows = claim_map("Whoever causes death by negligence shall be imprisonment [1].",
                         [hit("A licence must be renewed every year at the district office.")])
        self.assertEqual(rows[0]["status"], "check")

    def test_numbers_in_the_heading_count(self):
        h = hit("Whoever does it shall be punished with a fine.")
        rows = claim_map("Section 5 of the Test Act, 2001 punishes it with a fine [1].", [h])
        self.assertEqual(rows[0]["status"], "linked")

    def test_bangla_digits_match_ascii(self):
        self.assertEqual(numbers_in("৫০,০০০ টাকা ও ৭ বছর"), {"50000", "7"})
        h = hit("সে সাত বৎসর পর্যন্ত কারাদণ্ড বা ৫০,০০০ টাকা অর্থদণ্ডে দণ্ডিত হইবে।", language="bn")
        rows = claim_map("শাস্তি ৫০০০০ টাকা অর্থদণ্ড [1]।", [h])
        self.assertEqual(rows[0]["status"], "linked")

    def test_cross_language_checks_numbers_only(self):
        h = hit("সে সাত বৎসর পর্যন্ত কারাদণ্ডে দণ্ডিত হইবে।", language="bn")
        self.assertEqual(claim_map("The punishment is imprisonment of up to seven years [1].", [h])[0]["status"],
                         "linked")
        self.assertEqual(claim_map("The fine is 10000 taka [1].", [h])[0]["status"], "check")

    def test_tips_are_not_statements(self):
        text = ("Death by negligence is punished with imprisonment [2].\n\n"
                "Practical tips:\n- Keep copies of every document you sign.")
        self.assertEqual(len(claim_map(text, HITS)), 1)

    def test_entailment_verdict_wins(self):
        claim = "Whoever causes death by a rash or negligent act shall be punished with imprisonment"
        ent = {"claims": [{"claim": claim + " .", "cited": [2], "supported": False, "score": 0.1}]}
        self.assertEqual(claim_map(claim + " [2].", HITS, ent)[0]["status"], "check")


class TestEvidence(unittest.TestCase):
    def test_best_clause_is_verbatim(self):
        body = ("(1) Whoever steals shall be punished with imprisonment for three years. "
                "(2) Whoever receives stolen property shall be punished with a fine.")
        clause, score = best_clause("Receiving stolen property is punished with a fine.", body)
        self.assertIn(clause, body)
        self.assertTrue(clause.startswith("(2)"))
        self.assertGreater(score, 0.5)

    def test_spans_per_source(self):
        rows = claim_map("যে ব্যক্তি হত্যা করিবে সে মৃত্যুদণ্ডে দণ্ডিত হইবে [1]।", HITS)
        spans = evidence_spans(rows, HITS)
        self.assertEqual(list(spans), [1])
        self.assertIn(spans[1][0], HITS[0].body)

    def test_summary_and_verdicts(self):
        rows = claim_map("যে ব্যক্তি হত্যা করিবে সে মৃত্যুদণ্ডে দণ্ডিত হইবে [1]।", HITS)
        self.assertEqual(verdict(False, False, False, rows), "grounded")
        self.assertEqual(summarize(rows, "")["linked"], 1)
        self.assertEqual(verdict(False, False, False, rows + [{"status": "uncited"}]), "partly_grounded")
        self.assertEqual(verdict(False, False, False, []), "partly_grounded")
        self.assertEqual(verdict(True, False, False, []), "not_found")
        self.assertEqual(verdict(False, True, False, []), "general_guidance")
        self.assertEqual(verdict(True, False, True, []), "off_topic")

    def test_answer_verification(self):
        a = Answer("q", "যে ব্যক্তি হত্যা করিবে সে মৃত্যুদণ্ডে দণ্ডিত হইবে [1]।", HITS, cited=[1])
        v = a.verification()
        self.assertEqual(v["verdict"], "grounded")
        self.assertIn(1, v["evidence"])
        refused = Answer("q", "NOT_FOUND: nothing", HITS, refused=True)
        self.assertEqual(refused.verification()["claims"], [])


class TestProvenance(unittest.TestCase):
    URL = "http://bdlaws.minlaw.gov.bd/act-1037/section-38212.html"

    def test_fetched_day_wins_and_is_labelled(self):
        m = {"act_id": 1037, "url": self.URL, "fetched": "2026-10-01", "amended": True,
             "footnotes": ["বীমা (সংশোধন) আইন, ২০১৯ দ্বারা প্রতিস্থাপিত"]}
        p = provenance(m, index_built=time.time())
        self.assertEqual((p["as_of"], p["as_of_kind"]), ("2026-10-01", "fetched"))
        self.assertEqual(p["last_amended"], 2019)
        self.assertEqual(p["act_url"], "http://bdlaws.minlaw.gov.bd/act-1037.html")

    def test_falls_back_to_index_day(self):
        p = provenance({"act_id": 1, "url": self.URL}, index_built=0.0 + 86400 * 365)
        self.assertEqual((p["as_of"], p["as_of_kind"]), ("1971-01-01", "index"))
        self.assertIsNone(provenance({"url": "x"})["as_of_kind"])
        self.assertIsNone(act_url({"url": "https://elsewhere.example/page"}))

    def test_source_card_carries_provenance(self):
        card = source_card(1, HITS[0])
        for key in ("publisher", "act_url", "as_of", "last_amended"):
            self.assertIn(key, card)

    def test_acts_table(self):
        rows = acts_table(CORPUS, index_built=86400.0)
        self.assertEqual(len({r["act_id"] for r in rows}), len(rows))
        self.assertTrue(all(r["as_of"] == "1970-01-02" for r in rows))
        self.assertEqual(rows[-1]["repealed"], any(r["repealed"] for r in rows))   # repealed last
        recs = [{"metadata": {"act_id": 5, "act_title": "A", "type": "section", "section_id": 1,
                              "part": 1, "amended": True, "fetched": "2026-09-01", "url": self.URL,
                              "footnotes": ["Amended by Act 3 of 2015", "and by Act 1 of 2021"]}},
                {"metadata": {"act_id": 5, "act_title": "A", "type": "section", "section_id": 1,
                              "part": 2, "fetched": "2026-09-03"}}]
        (a,) = acts_table(recs)
        self.assertEqual((a["sections"], a["amended_sections"], a["last_amended"]), (1, 1, 2021))
        self.assertEqual((a["as_of"], a["as_of_kind"]), ("2026-09-03", "fetched"))

    def test_fetcher_reports_the_cache_day(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fetcher(cache_dir=d, offline=True)
            url = "http://bdlaws.minlaw.gov.bd/act-1.html"
            self.assertIsNone(f.fetched_on(url))
            path = f._cache_path(url)
            gz = path.with_name(path.name + ".gz")
            with gzip.open(gz, "wt", encoding="utf-8") as fh:
                fh.write("<html></html>")
            os.utime(gz, (86400 * 2, 86400 * 2))
            self.assertEqual(f.fetched_on(url), "1970-01-03")


try:
    from starlette.testclient import TestClient

    from service.app import ServiceConfig, create_app
    from test_service import fake_components
    HAVE_STARLETTE = True
except ImportError:  # pragma: no cover
    HAVE_STARLETTE = False


@unittest.skipUnless(HAVE_STARLETTE, "starlette not installed")
class TestService(unittest.TestCase):
    def client(self, llm=None, **cfg_kw):
        pipeline, default_llm, stream = fake_components()
        llm = llm or default_llm
        cfg = ServiceConfig(**{"rate_per_min": 6000, "burst": 100, **cfg_kw})
        app = create_app(cfg, pipeline=pipeline, llm=llm,
                         stream_llm=lambda s, p: iter([llm(s, p)]), records=CORPUS)
        return TestClient(app)

    def test_answer_carries_its_checks(self):
        body = self.client().post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()
        self.assertEqual(body["verdict"], "grounded")
        self.assertEqual(body["claims"][0]["cites"], [1])
        self.assertEqual(body["verification"]["statements"], 1)
        src = body["sources"][0]
        self.assertTrue(src["evidence"])
        self.assertIn(src["evidence"][0], src["text"])
        self.assertIn("Laws of Bangladesh", src["publisher"])
        self.assertEqual(body["searched"], [])

    def test_refusal_shows_what_was_searched(self):
        c = self.client(llm=lambda s, p: "NOT_FOUND: the excerpts do not cover tenancy.",
                        general_fallback=False)
        body = c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()
        self.assertTrue(body["refused"])
        self.assertEqual(body["verdict"], "not_found")
        self.assertEqual(body["sources"], [])
        self.assertTrue(1 <= len(body["searched"]) <= 3)
        self.assertIn("citation", body["searched"][0])

    def test_unchecked_statement_caps_confidence(self):
        c = self.client(llm=lambda s, p: "হত্যার শাস্তি মৃত্যুদণ্ড [1]। The fine is Tk 99,999 [1].")
        body = c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()
        self.assertEqual(body["verdict"], "partly_grounded")
        self.assertNotEqual((body["confidence"] or {}).get("label"), "high")

    def test_stream_final_has_verdict(self):
        r = self.client().post("/ask/stream", json={"question": "হত্যার শাস্তি কী?"})
        self.assertIn('"verdict": "grounded"', r.text)

    def test_acts_and_sources_page(self):
        c = self.client()
        body = c.get("/acts").json()
        self.assertEqual(body["count"], len({r["metadata"]["act_id"] for r in CORPUS}))
        self.assertIn("as_of", body["acts"][0])
        page = c.get("/sources")
        self.assertEqual(page.status_code, 200)
        self.assertIn("/acts", page.text)
        self.assertIn("Allow: /sources", c.get("/robots.txt").text)


if __name__ == "__main__":
    unittest.main()
