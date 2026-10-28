"""Law beyond the Acts (rules, SROs, judgments) and the public coverage page."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from bdrag_tools.gaps import analyse, public_report  # noqa: E402
from ingest.chunk import act_overview_chunk, chunk_section  # noqa: E402
from ingest.judgment import case_info, find_case_number, judgment_chunks  # noqa: E402
from ingest.pdf import PageText, build_act  # noqa: E402
from ingest.sources import (  # noqa: E402
    append_manifest,
    load_manifest,
    official,
    parse_sc_list,
    source_act_id,
    validate,
)
from rag.answer import format_context, source_card  # noqa: E402
from rag.store import Hit  # noqa: E402
from rag.verify import verify_hit  # noqa: E402
from service.coverage import corpus_counts, coverage_data, render  # noqa: E402

JUDGMENT_P1 = """IN THE SUPREME COURT OF BANGLADESH
HIGH COURT DIVISION
(CIVIL APPELLATE JURISDICTION)
Present:
Mr. Justice S M Kuddus Zaman
FIRST APPEAL NO.311 OF 2016
Mohammad Hanif and others
    .... Appellants
  -Versus-
Government of Bangladesh and others
    .... Respondents
Mr. A, Advocate
     …. For the appellants.
Heard on 19.07.2026 and 24.08.2026.
Judgment on 25.08.2026.

S M Kuddus Zaman, J:
 This First Appeal at the instance of the plaintiff is directed against
the judgment and decree dated 17.08.2016 passed by the Joint District Judge.
 2
Facts in short are that the appellants instituted the suit for declaration of title."""

JUDGMENT_P2 = """The trial court dismissed the suit holding that a City Survey Khatian
carries a presumption of correctness under section 103B of the State Acquisition
and Tenancy Act.
 3
 We have considered the submissions. The appeal is allowed."""

SC_ROW = """<tr class="font_e_12" bgcolor="#dadAF1">
 <td align="center"> 1 </td>
 <td><a href="../resources/documents/1_FIRST_APPEAL_311_OF_2016_ALLOWED.pdf">
 First Appeal (TN) 311/2016<br>(First Appeal (TN) 311/2016) </a>
 <a href="https://supremecourt.gov.bd/translation/process.php?file=x.pdf">অনুবাদ (Google)</a>
 Uploaded on : 27-OCT-26 Annex Building Court No. 20</td>
 <td>Mohammad Hanif -Versus- Government of Bangladesh</td>
 <td>The First Appeal is allowed.</td>
</tr>"""

RULES_PAGE = """ভোক্তা-অধিকার সংরক্ষণ বিধিমালা, ২০২১
১। সংক্ষিপ্ত শিরোনাম।—এই বিধিমালা ভোক্তা-অধিকার সংরক্ষণ বিধিমালা, ২০২১ নামে অভিহিত হইবে।
২। অভিযোগ দায়েরের পদ্ধতি।—অভিযোগ ফরম 'ক' অনুযায়ী লিখিতভাবে দায়ের করিতে হইবে।"""


class TestManifest(unittest.TestCase):
    def test_only_government_hosts_are_accepted(self):
        self.assertTrue(official("https://supremecourt.gov.bd/resources/documents/a.pdf"))
        self.assertTrue(official("http://bdlaws.minlaw.gov.bd/act-367.html"))
        self.assertTrue(official("https://dncrp.portal.gov.bd/sites/default/files/rules.pdf"))
        self.assertFalse(official("https://www.scribd.com/document/1/rules.pdf"))
        self.assertFalse(official("https://gov.bd.example.com/a.pdf"))
        self.assertFalse(official("ftp://supremecourt.gov.bd/a.pdf"))

    def test_validate_names_each_problem(self):
        ok = {"id": "consumer-rules-2021", "kind": "rule", "title": "x",
              "url": "https://www.dpp.gov.bd/a.pdf"}
        self.assertEqual(validate(ok), [])
        errs = validate({"id": "X Bad", "kind": "blog", "url": "https://scribd.com/a.pdf"})
        self.assertEqual(len(errs), 4)

    def test_manifest_rejects_repeated_ids_and_append_skips_known_urls(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "m.jsonl")
            e = {"id": "a-1", "kind": "judgment", "title": "t", "url": "https://supremecourt.gov.bd/a.pdf"}
            self.assertEqual(append_manifest(p, [e]), 1)
            self.assertEqual(append_manifest(p, [e, {**e, "id": "a-2", "url": e["url"] + "x"}]), 1)
            self.assertEqual([r["id"] for r in load_manifest(p)], ["a-1", "a-2"])
            p.write_text(p.read_text() + json.dumps(e) + "\n")
            with self.assertRaises(ValueError):
                load_manifest(p)

    def test_committed_manifest_is_valid(self):
        rows = load_manifest(ROOT / "data/sources/manifest.jsonl")
        self.assertTrue(rows)
        for r in rows:
            self.assertEqual(validate(r), [], r["id"])

    def test_supreme_court_list_row_becomes_an_entry(self):
        [e] = parse_sc_list(SC_ROW, "HCD")
        self.assertEqual(e["url"], "https://supremecourt.gov.bd/resources/documents/"
                                   "1_FIRST_APPEAL_311_OF_2016_ALLOWED.pdf")
        self.assertEqual(e["listed_as"], "First Appeal (TN) 311/2016")
        self.assertEqual(e["kind"], "judgment")
        self.assertEqual(e["uploaded"], "2026-10-27")
        self.assertEqual(validate(e), [])

    def test_source_ids_do_not_collide_with_pdf_acts(self):
        self.assertGreaterEqual(source_act_id("x"), 950_000)


class TestJudgments(unittest.TestCase):
    def setUp(self):
        self.pages = [PageText(1, JUDGMENT_P1, False), PageText(2, JUDGMENT_P2, False)]
        self.meta = {"id": "hcd-fa-311", "title": "First Appeal (TN) 311/20116 (HCD)",
                     "url": "https://supremecourt.gov.bd/resources/documents/fa.pdf",
                     "listed_as": "First Appeal (TN) 311/20116", "division": "HCD",
                     "parties": "Mohammad Hanif -Versus- Government of Bangladesh"}

    def test_case_number_prefers_a_well_formed_list_entry_else_the_cause_title(self):
        self.assertEqual(find_case_number("", "First Appeal 37/2022"), "First Appeal No. 37 of 2022")
        # The list's typo (a five-digit year) falls back to the PDF.
        self.assertEqual(find_case_number(JUDGMENT_P1, "First Appeal (TN) 311/20116"),
                         "First Appeal No. 311 of 2016")
        self.assertEqual(find_case_number("Farah Mahbub. CIVIL APPEAL NO.73 OF 2023. WITH CIVIL "
                                          "PETITION FOR LEAVE TO APPEAL NOS.1271"),
                         "Civil Appeal No. 73 of 2023")

    def test_case_info_reads_court_and_date_not_the_decision_appealed_from(self):
        info = case_info(JUDGMENT_P1, {})
        self.assertEqual(info.division, "HCD")
        self.assertEqual(info.decided, "2026-08-25")
        self.assertIn("High Court Division", info.court)
        self.assertIsNone(case_info("judgment and order dated 11.03.2019 passed by").decided)

    def test_chunks_cite_the_case_and_the_page(self):
        chunks = judgment_chunks(self.pages, 960_001, self.meta, max_chars=200)
        over, body = chunks[0], chunks[1:]
        self.assertEqual(over.metadata["part_of"], "overview")
        self.assertIn("FIRST APPEAL NO.311 OF 2016", over.body)
        self.assertTrue(body)
        # The cause title (counsel, judges) is not repeated in the body chunks.
        self.assertTrue(body[0].body.startswith("This First Appeal"))
        self.assertNotIn("For the appellants", " ".join(c.body for c in body))
        last = body[-1]
        self.assertEqual(last.metadata["page"], 2)
        self.assertTrue(last.metadata["url"].endswith("fa.pdf#page=2"))
        hit = Hit(last.chunk_id, 1.0, last.text, last.body, last.metadata)
        self.assertEqual(hit.citation, "First Appeal No. 311 of 2016 (HCD), p. 2")
        self.assertEqual(Hit("o", 1.0, "", "", over.metadata).citation,
                         "First Appeal No. 311 of 2016 (HCD)")
        self.assertIn("[COURT JUDGMENT, 2026-08-25]", format_context([hit]))
        card = source_card(1, hit)
        self.assertEqual((card["doc_type"], card["decided"]), ("judgment", "2026-08-25"))

    def test_judgments_are_never_live_verified_against_bdlaws(self):
        c = judgment_chunks(self.pages, 960_001, self.meta)[1]
        hit = Hit(c.chunk_id, 1.0, c.text, c.body, c.metadata)
        self.assertEqual(verify_hit(hit, fetcher=None), "unavailable")


class TestRules(unittest.TestCase):
    def test_rules_are_cited_as_rules_not_sections(self):
        act, sections, extras = build_act([PageText(1, RULES_PAGE, False)], 951_000,
                                          "ভোক্তা-অধিকার সংরক্ষণ বিধিমালা, ২০২১",
                                          source="https://www.dpp.gov.bd/r.pdf")
        act.doc_type = "rule"
        chunks = [c for s in sections for c in chunk_section(act, s)]
        self.assertTrue(chunks)
        self.assertIn("বিধি ২:", chunks[-1].text)
        self.assertNotIn("ধারা", chunks[-1].text.split("\n")[0])
        self.assertEqual(chunks[-1].metadata["doc_type"], "rule")
        hit = Hit(chunks[-1].chunk_id, 1.0, chunks[-1].text, chunks[-1].body, chunks[-1].metadata)
        self.assertEqual(hit.citation, "ভোক্তা-অধিকার সংরক্ষণ বিধিমালা, ২০২১, বিধি ২")
        self.assertEqual(act_overview_chunk(act).metadata["doc_type"], "rule")
        hit.metadata["parent_act"] = "ভোক্তা-অধিকার সংরক্ষণ আইন, ২০০৯"
        self.assertIn("[RULE under ভোক্তা-অধিকার সংরক্ষণ আইন, ২০০৯]", format_context([hit]))

    def test_acts_keep_their_citation(self):
        m = {"type": "section", "act_title": "The Penal Code, 1860", "language": "en",
             "section_number": "302"}
        self.assertEqual(Hit("x", 1.0, "", "", m).citation, "The Penal Code, 1860, section 302")


class TestPublicGaps(unittest.TestCase):
    def rows(self):
        q = "What is the court fee for a title suit? call 01712345678"
        rows = [{"ts": 1, "question": q, "refused": True, "client": f"c{i}"} for i in range(3)]
        rows += [{"ts": 1, "question": "my neighbour Rahim's land in Mirpur", "general": True,
                  "client": "c9"}]
        return rows

    def test_only_questions_several_visitors_asked_are_published_and_redacted(self):
        pub = public_report(analyse(self.rows(), []), min_visitors=3)
        self.assertEqual(len(pub["questions"]), 1)
        q = pub["questions"][0]
        self.assertNotIn("01712345678", q["question"])
        self.assertEqual(q["why"], "unanswered")
        self.assertEqual(q["visitors"], 3)
        self.assertNotIn("comments", q)
        self.assertNotIn("Rahim", json.dumps(pub))


class TestCoveragePage(unittest.TestCase):
    RECORDS = [
        {"metadata": {"act_id": 1, "type": "section"}},
        {"metadata": {"act_id": 1, "type": "section"}},
        {"metadata": {"act_id": 2, "type": "section", "doc_type": "act"}},
        {"metadata": {"act_id": 951_000, "type": "section", "doc_type": "rule"}},
        {"metadata": {"act_id": 960_001, "type": "judgment", "doc_type": "judgment"}},
    ]

    def test_counts_by_kind(self):
        self.assertEqual(corpus_counts(self.RECORDS), {
            "act": {"documents": 2, "chunks": 3}, "rule": {"documents": 1, "chunks": 1},
            "judgment": {"documents": 1, "chunks": 1}})

    def test_page_escapes_published_questions(self):
        with tempfile.TemporaryDirectory() as d:
            pub = Path(d, "p.json")
            pub.write_text(json.dumps({"generated": "2026-10-28", "min_visitors": 3, "questions": [
                {"question": "<script>alert(1)</script> court fee?", "language": "en",
                 "why": "unanswered"}]}))
            data = coverage_data(self.RECORDS, 1_761_609_600, str(ROOT / "data/coverage/known_gaps.json"),
                                 str(pub))
            page = render(data)
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("Known gaps", page)
        self.assertIn("জানা ঘাটতি", page)
        self.assertIn("Judgment", page)
        self.assertIn("2025-10-28", page)

    def test_page_says_so_when_nothing_is_published(self):
        page = render(coverage_data([], None, "missing.json", "missing.json"))
        self.assertIn("No list has been published yet.", page)


try:
    from starlette.testclient import TestClient

    from service.app import ServiceConfig, create_app
    from test_service import fake_components
    HAVE_STARLETTE = True
except ImportError:                       # pragma: no cover
    HAVE_STARLETTE = False


@unittest.skipUnless(HAVE_STARLETTE, "starlette not installed")
class TestCoverageRoute(unittest.TestCase):
    def test_served_as_html_and_json_and_linked(self):
        pipeline, llm, stream = fake_components()
        c = TestClient(create_app(ServiceConfig(rate_per_min=6000, burst=100),
                                  pipeline=pipeline, llm=llm, stream_llm=stream))
        r = c.get("/coverage")
        self.assertEqual(r.status_code, 200)
        self.assertIn("What we can and can't answer", r.text)
        j = c.get("/coverage", headers={"accept": "application/json"}).json()
        self.assertIn("known_gaps", j)
        self.assertIn('href="/coverage"', c.get("/").text)
        self.assertIn('href="/coverage"', c.get("/privacy").text)
        self.assertIn("Allow: /coverage", c.get("/robots.txt").text)


if __name__ == "__main__":
    unittest.main()
