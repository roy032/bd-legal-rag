"""PDF / OCR ingest: the text-side logic, which needs neither PyMuPDF nor Tesseract."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.chunk import chunk_section  # noqa: E402
from ingest.pdf import (  # noqa: E402
    PageText,
    build_act,
    clean_page,
    split_sections,
    strip_running_lines,
)

BN_PAGE_1 = """10/17/26, 10:11 AM
ভোক্তা-অধিকার সংরক্ষণ আইন, ২০০৯
১। সংক্ষিপ্ত শিরোনাম ও প্রবর্তন।—(১) এই আইন ভোক্তা-অধিকার সংরক্ষণ আইন, ২০০৯ নামে অভিহিত হইবে।
২। সংজ্ঞা।—এই আইনে,—
১. "ভোক্তা" অর্থ এমন কোন ব্যক্তি যিনি পণ্য ক্রয় করেন
1/2"""

BN_PAGE_2 = """10/17/26, 10:12 AM
৪৫। প্রতিশ্রুত পণ্য বা সেবা যথাযথভাবে বিক্রয় বা সরবরাহ না
করিবার দণ্ড।—কোন ব্যক্তি প্রতিশ্রুত পণ্য সরবরাহ না করিলে তিনি অনূর্ধ্ব এক বৎসর কারাদণ্ডে দণ্ডিত হইবেন।
2/2"""

EN_PAGES = ["""THE PENAL CODE, 1860
299. Culpable homicide.—Whoever causes death by doing an act with the intention of causing death,
commits the offence of culpable homicide.
300. Murder.—Except in the cases hereinafter excepted, culpable homicide is murder.""",
            """301. Culpable homicide by causing death of person other than person whose death was intended.—If a
person causes death ...
302. Punishment for murder.—Whoever commits murder shall be punished with death, or imprisonment
for life, and shall also be liable to fine."""]


def pages(*texts, ocr=False):
    return [PageText(i, clean_page(t), ocr) for i, t in enumerate(texts, start=1)]


class TestCleaning(unittest.TestCase):
    def test_doubled_vowel_signs_and_ocr_dashes(self):
        self.assertEqual(clean_page("ভোক্তাা"), "ভোক্তা")
        self.assertIn("প্রবর্তন।—(১)", clean_page("প্রবর্তন।-_(১)"))
        self.assertIn("দণ্ড।—কোন", clean_page("দণ্ড।___কোন"))

    def test_pipe_read_for_dari_after_a_section_number(self):
        self.assertTrue(clean_page("৪৫ | প্রতিশ্রুত পণ্য").startswith("৪৫। প্রতিশ্রুত"))

    def test_running_headers_page_counters_and_urls_are_dropped(self):
        ps = strip_running_lines(pages(BN_PAGE_1 + "\nfile:///tmp/act.html", BN_PAGE_2))
        text = "\n".join(p.text for p in ps)
        self.assertNotIn("AM", text)
        self.assertNotIn("1/2", text)
        self.assertNotIn("file://", text)
        self.assertIn("সংজ্ঞা", text)

    def test_short_documents_keep_repeated_sentences(self):
        same = "তিনি অনূর্ধ্ব এক বৎসর কারাদণ্ডে দণ্ডিত হইবেন।"
        ps = strip_running_lines(pages(same, same))
        self.assertEqual(ps[0].text, same)


class TestSections(unittest.TestCase):
    def test_bangla_headings_including_a_wrapped_one(self):
        drafts = split_sections(strip_running_lines(pages(BN_PAGE_1, BN_PAGE_2)))
        self.assertEqual([d.number for d in drafts], ["", "১", "২", "৪৫"])
        self.assertEqual(drafts[3].title, "প্রতিশ্রুত পণ্য বা সেবা যথাযথভাবে বিক্রয় বা সরবরাহ না করিবার দণ্ড")
        self.assertEqual(drafts[3].page, 2)

    def test_numbered_clauses_stay_inside_their_section(self):
        drafts = split_sections(pages(BN_PAGE_1))
        definition = next(d for d in drafts if d.number == "২")
        self.assertIn("ভোক্তা", "\n".join(definition.lines))

    def test_english_headings(self):
        drafts = split_sections(pages(*EN_PAGES))
        self.assertEqual([d.number for d in drafts], ["", "299", "300", "301", "302"])
        self.assertEqual(drafts[-1].title, "Punishment for murder")

    def test_numbers_only_move_forward(self):
        text = "5. Powers.—The Board may—\n1. Members. The Board has five members.\n6. Fees.—A fee is payable."
        self.assertEqual([d.number for d in split_sections(pages(text))], ["5", "6"])


class TestBuildAct(unittest.TestCase):
    def test_chunks_carry_page_ocr_and_section(self):
        act, secs, extras = build_act(pages(BN_PAGE_1, BN_PAGE_2, ocr=True), 900001,
                                      "ভোক্তা-অধিকার সংরক্ষণ আইন, ২০০৯", source="consumer.pdf")
        self.assertEqual((act.language, act.year), ("bn", 2009))
        s45 = next(s for s in secs if s.number == "৪৫")
        self.assertTrue(s45.text.startswith("কোন ব্যক্তি"))
        self.assertEqual(s45.url, "consumer.pdf#page=2")
        self.assertEqual(extras[s45.section_id], {"source": "pdf", "page": 2, "ocr": True})
        chunk = chunk_section(act, s45)[0]
        self.assertIn("ধারা ৪৫", chunk.text)
        self.assertEqual(chunk.metadata["section_number_ascii"], "45")

    def test_falls_back_to_one_section_per_page(self):
        act, secs, _ = build_act(pages("Schedule of fees payable under the Act", "Form A — application"),
                                 900002, "Some Rules, 2001")
        self.assertEqual([s.title for s in secs], ["Page 1", "Page 2"])


if __name__ == "__main__":
    unittest.main()
