"""Run with:  python -m unittest discover -s tests -v"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.chunk import act_overview_chunk, chunk_section  # noqa: E402
from ingest.parse import parse_act, parse_index, parse_section  # noqa: E402
from ingest.textutils import (  # noqa: E402
    bn_to_ascii_digits,
    detect_lang,
    extract_section_refs,
    extract_year,
)

FX = ROOT / "tests" / "fixtures"


def read(name):
    return (FX / name).read_text(encoding="utf-8")


class TestTextUtils(unittest.TestCase):
    def test_digits_year_lang(self):
        self.assertEqual(bn_to_ascii_digits("ধারা ২৫"), "ধারা 25")
        self.assertEqual(extract_year("বীমা আইন, ২০১০"), 2010)
        self.assertEqual(extract_year("The Penal Code, 1860"), 1860)
        self.assertEqual(detect_lang("এই আইন বীমা আইন নামে অভিহিত হইবে"), "bn")
        self.assertEqual(detect_lang("Punishment for murder"), "en")

    def test_refs(self):
        self.assertEqual(extract_section_refs("ধারা ১২ এবং section 304A এবং ধারা ৭"), ["7", "12", "304A"])


class TestParse(unittest.TestCase):
    def test_index(self):
        refs = parse_index(read("index.html"))
        self.assertEqual([r.act_id for r in refs], [11, 1037])  # act-details link ignored

    def test_bangla_act(self):
        act = parse_act(read("act-1037.html"), 1037)
        self.assertEqual(act.title, "বীমা আইন, ২০১০")
        self.assertEqual(act.act_number, "২০১০ সনের ১৩ নং আইন")
        self.assertEqual(act.date, "মার্চ ১৮, ২০১০")
        self.assertEqual(act.year, 2010)
        self.assertEqual(act.language, "bn")
        self.assertFalse(act.repealed)  # 'রহিতপূর্বক' (repealing another act) must not trip this
        self.assertIn("পুনঃপ্রণয়ন", act.preamble)
        self.assertEqual([s.number_ascii for s in act.sections], ["1", "2", "3"])
        self.assertEqual(act.sections[1].title, "সংজ্ঞা")
        self.assertTrue(act.sections[0].chapter.startswith("প্রথম অধ্যায়"))
        self.assertTrue(act.sections[2].chapter.startswith("দ্বিতীয় অধ্যায়"))

    def test_english_act(self):
        act = parse_act(read("act-11-en.html"), 11)
        self.assertEqual(act.title, "The Penal Code, 1860")
        self.assertEqual(act.act_number, "ACT NO. XLV OF 1860")
        self.assertEqual(act.language, "en")
        self.assertEqual([s.number for s in act.sections], ["1", "302", "304A"])
        self.assertEqual(act.sections[2].title, "Causing death by negligence")
        self.assertEqual(act.sections[1].chapter, "CHAPTER XVI - OF OFFENCES AFFECTING THE HUMAN BODY")

    def test_section_body_is_clean(self):
        act = parse_act(read("act-1037.html"), 1037)
        sec = parse_section(read("section-38212.html"), act.sections[0], act)
        self.assertTrue(sec.text.startswith("(১) এই আইন"), sec.text)
        for junk in ("হোম", "English", "সর্বস্বত্ব", "[বীমা আইন, ২০১০]", "সংক্ষিপ্ত শিরোনাম"):
            self.assertNotIn(junk, sec.text)

    def test_footnotes_split_off(self):
        act = parse_act(read("act-1037.html"), 1037)
        sec = parse_section(read("section-40548.html"), act.sections[1], act)
        self.assertEqual(len(sec.footnotes), 1)
        self.assertIn("প্রতিস্থাপিত", sec.footnotes[0])
        self.assertNotIn("প্রতিস্থাপিত", sec.text)
        self.assertNotIn("প্রিন্টেবল", sec.text)


class TestChunk(unittest.TestCase):
    def setUp(self):
        self.act = parse_act(read("act-1037.html"), 1037)

    def test_short_section_single_chunk(self):
        sec = parse_section(read("section-38214.html"), self.act.sections[2], self.act)
        chunks = chunk_section(self.act, sec)
        self.assertEqual(len(chunks), 1)
        c = chunks[0]
        self.assertTrue(c.text.startswith("বীমা আইন, ২০১০ > দ্বিতীয় অধ্যায়"))
        self.assertIn("ধারা ৩:", c.text)
        self.assertEqual(c.metadata["refs"], ["7"])

    def test_long_section_split_on_clauses_with_lead_in(self):
        sec = parse_section(read("section-40548.html"), self.act.sections[1], self.act)
        chunks = chunk_section(self.act, sec, max_chars=800)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c.body), 800)
            self.assertEqual(c.metadata["n_parts"], len(chunks))
        # every later part starts at a clause boundary and repeats the lead-in
        for c in chunks[1:]:
            self.assertTrue(c.body.startswith("("), c.body[:40])
            self.assertIn("এই আইনে-", c.text)
        # no clause lost or duplicated
        joined = "\n".join(c.body for c in chunks)
        self.assertEqual(joined.count("“শব্দ"), 20)
        self.assertTrue(chunks[0].metadata["amended"])

    def test_overview(self):
        c = act_overview_chunk(self.act)
        self.assertIn("২০১০ সনের ১৩ নং আইন", c.text)
        self.assertIn("২. সংজ্ঞা", c.text)
        self.assertEqual(c.metadata["n_sections"], 3)


if __name__ == "__main__":
    unittest.main()
