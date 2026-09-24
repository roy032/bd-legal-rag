"""Explicit references: act names (official or colloquial) and section numbers."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.query import SECTION_REF, expand_section_refs  # noqa: E402
from rag.refs import ActResolver, Reference, apply_reference  # noqa: E402
from rag.store import Hit  # noqa: E402


def rec(cid, act_id, title, number, body="text", repealed=False, kind="section"):
    return {"chunk_id": cid, "text": f"{title} > {number}\n\n{body}", "body": body,
            "metadata": {"type": kind, "act_id": act_id, "act_title": title, "repealed": repealed,
                         "section_number": number, "section_number_ascii": number,
                         "language": "en"}}


RECORDS = [
    rec("11-302", 11, "The Penal Code, 1860", "302", "Whoever commits murder"),
    rec("11-304A", 11, "The Penal Code, 1860", "304A", "causes the death by negligence"),
    rec("99-302", 99, "The Penal Code (Amendment) Act, 1985", "302", "amending text"),
    rec("24-101", 24, "The Evidence Act, 1872", "101", "Burden of proof"),
    rec("1037-2", 1037, "বীমা আইন, ২০১০", "2", "সংজ্ঞা"),
    rec("500-1", 500, "অর্থ আইন, ২০১৯", "1", "old finance act"),
    rec("501-1", 501, "অর্থ আইন, ২০২৪", "1", "new finance act"),
    rec("836-1", 836, "পরিবেশ আদালত আইন, ২০০০", "1", "repealed", repealed=True),
    rec("1006-1", 1006, "পরিবেশ আদালত আইন, ২০১০", "1", "in force"),
]


class TestSectionRegex(unittest.TestCase):
    def test_suffix_must_touch_the_number(self):
        self.assertEqual(SECTION_REF.findall("ধারা ৩০২ কী বলে?"), ["৩০২"])
        self.assertEqual(SECTION_REF.findall("section 2 of the Act"), ["2"])
        self.assertEqual(SECTION_REF.findall("section 304A applies"), ["304A"])
        self.assertEqual(SECTION_REF.findall("ধারা ৫ক অনুযায়ী"), ["৫ক"])
        self.assertEqual(SECTION_REF.findall("ধারা ৩০২এ"), ["৩০২"])
        self.assertEqual(SECTION_REF.findall("Article 27 of the Constitution"), ["27"])
        self.assertEqual(SECTION_REF.findall("সংবিধানের অনুচ্ছেদ ৩৯"), ["৩৯"])

    def test_expansion_has_no_junk_tokens(self):
        self.assertEqual(expand_section_refs("ধারা ৩০২ কী বলে?"),
                         "ধারা ৩০২ কী বলে? ধারা 302 section 302 302")


class TestResolver(unittest.TestCase):
    def setUp(self):
        self.r = ActResolver(RECORDS)

    def test_colloquial_bangla_name(self):
        self.assertEqual(self.r.resolve("দণ্ডবিধির ধারা ৩০২ কী বলে?"), Reference([11], ["302"]))

    def test_official_title_and_amending_acts_ignored(self):
        self.assertEqual(self.r.resolve("Penal Code section 304A").act_ids, [11])
        self.assertEqual(self.r.resolve("What does the Evidence Act say?").act_ids, [24])

    def test_bangla_title_with_case_suffix(self):
        self.assertEqual(self.r.resolve("বীমা আইনে সংজ্ঞা কী?").act_ids, [1037])

    def test_shared_stem_prefers_in_force_then_latest(self):
        self.assertEqual(self.r.resolve("অর্থ আইন অনুযায়ী").act_ids, [501])
        self.assertEqual(self.r.resolve("পরিবেশ আদালত আইন").act_ids, [1006])

    def test_no_reference(self):
        self.assertFalse(self.r.resolve("punishment for murder"))

    def test_exact_lookup_goes_first(self):
        hits = [Hit("24-101", 0.9, "", "", RECORDS[3]["metadata"]),
                Hit("99-302", 0.8, "", "", RECORDS[2]["metadata"])]
        out = apply_reference(hits, Reference([11], ["302"]), self.r)
        self.assertEqual(out[0].chunk_id, "11-302")
        self.assertGreaterEqual(out[0].score, out[1].score)

    def test_number_only_promotes_matching_sections(self):
        hits = [Hit("24-101", 0.9, "", "", RECORDS[3]["metadata"]),
                Hit("99-302", 0.8, "", "", RECORDS[2]["metadata"])]
        out = apply_reference(hits, Reference([], ["302"]), self.r)
        self.assertEqual([h.chunk_id for h in out], ["99-302", "24-101"])


if __name__ == "__main__":
    unittest.main()
