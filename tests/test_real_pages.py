"""Parser tests against pages saved verbatim from bdlaws.minlaw.gov.bd.

The synthetic fixtures in tests/fixtures/ describe the site's structure; these
are the site itself. The first version of the parser passed every synthetic test
and still put the copyright footer into 95% of sections — these tests exist so
that cannot happen again.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.chunk import act_overview_chunk, chunk_section  # noqa: E402
from ingest.models import Act, SectionRef  # noqa: E402
from ingest.parse import parse_act, parse_section  # noqa: E402
from ingest.textutils import fix_legacy_bangla, normalize  # noqa: E402

REAL = ROOT / "tests" / "fixtures" / "real"
BOILERPLATE = ("Copyright", "Legislative and Parliamentary Affairs Division", "Chronological Index",
               "Related Links", "সূচি", "ধারাসমূহ")


def read(name: str) -> str:
    return (REAL / name).read_text(encoding="utf-8")


def ref_of(act: Act, section_id: int) -> SectionRef:
    return next(r for r in act.sections if r.section_id == section_id)


class TestRealActPages(unittest.TestCase):
    def test_bangla_act_header(self):
        act = parse_act(read("act-1037.html"), 1037)
        self.assertEqual(act.title, "বীমা আইন, ২০১০")
        self.assertEqual(act.act_number, "২০১০ সনের ১৩ নং আইন")
        self.assertEqual(act.date, "মার্চ ১৮, ২০১০")
        self.assertEqual((act.year, act.language, act.repealed), (2010, "bn", False))
        self.assertTrue(act.preamble.startswith("Insurance Act, 1938 রহিতপূর্বক"))
        self.assertEqual(len(act.sections), 160)

    def test_bangla_chapters_keep_their_names(self):
        act = parse_act(read("act-1037.html"), 1037)
        self.assertEqual(act.sections[0].chapter, "প্রথম অধ্যায় - প্রারম্ভিক")
        self.assertEqual(act.sections[2].chapter, "দ্বিতীয় অধ্যায় - বীমাকারীর জন্য প্রযোজ্য বিধানাবলী")
        eight = next(s for s in act.sections if s.number_ascii == "8")
        self.assertEqual(eight.heading, "বীমাকারীর নিবন্ধন")

    def test_english_act_parts_chapters_and_split_sections(self):
        act = parse_act(read("act-24.html"), 24)
        self.assertEqual(act.title, "The Evidence Act, 1872")     # no footnote digit glued on
        self.assertEqual(act.act_number, "ACT NO. I OF 1872")
        self.assertEqual(act.date, "15th March, 1872")
        self.assertTrue(act.preamble.startswith("WHEREAS it is expedient"))  # no ♣, no footnote digit
        first = act.sections[0]
        self.assertEqual(first.part, "Part I - RELEVANCY OF FACTS")
        self.assertEqual(first.chapter, "Chapter I - PRELIMINARY")
        # "Extent" and "Commencement of Act" are pages of section 1 with no printed number.
        self.assertEqual([(s.number, s.inherited_number) for s in act.sections[:3]],
                         [("1", False), ("1", True), ("1", True)])

    def test_repealed_act_is_flagged_with_the_sites_notice(self):
        act = parse_act(read("act-836.html"), 836)
        self.assertTrue(act.repealed)
        self.assertIn("পরিবেশ আদালত আইন, ২০১০", act.repeal_note)
        self.assertIn("৫গ", [s.number for s in act.sections])

    def test_overview_chunk_is_bounded(self):
        act = parse_act(read("act-24.html"), 24)
        chunk = act_overview_chunk(act, max_chars=1500)
        self.assertLessEqual(len(chunk.body), 1510)
        self.assertIn("Chapter I - PRELIMINARY", chunk.body)


class TestRealSectionPages(unittest.TestCase):
    def setUp(self):
        self.penal = Act(act_id=11, title="The Penal Code, 1860", act_number="ACT NO. XLV OF 1860",
                         date=None, preamble=None, year=1860, language="en", repealed=False,
                         url="http://bdlaws.minlaw.gov.bd/act-11.html")

    def _penal(self, sid, number, title):
        return SectionRef(sid, number, number, title, None,
                          f"http://bdlaws.minlaw.gov.bd/act-11/section-{sid}.html")

    def test_body_has_no_page_furniture(self):
        sec = parse_section(read("act-11-section-3131.html"), self._penal(3131, "302", "Punishment for murder"),
                            self.penal)
        self.assertEqual(sec.text, "302. Whoever commits murder shall be punished with death, or "
                                   "[imprisonment] for life, and shall also be liable to fine.")
        for junk in BOILERPLATE + ("The Penal Code, 1860", "6th October"):
            self.assertNotIn(junk, sec.text)
        self.assertEqual(sec.chapter, "Chapter XVI - OF OFFENCES AFFECTING THE HUMAN BODY")

    def test_only_this_sections_footnotes_are_kept(self):
        sec = parse_section(read("act-11-section-3131.html"), self._penal(3131, "302", "Punishment for murder"),
                            self.penal)
        # Note 1 belongs to the act title ("Throughout this Act ...") and is on every page.
        self.assertEqual(len(sec.footnotes), 1)
        self.assertIn("“imprisonment” was substituted", sec.footnotes[0])
        sec = parse_section(read("act-11-section-3134.html"),
                            self._penal(3134, "304A", "Causing death by negligence"), self.penal)
        self.assertEqual(len(sec.footnotes), 2)
        self.assertIn("inserted", sec.footnotes[0])

    def test_bangla_subsections_are_separate_lines(self):
        act = parse_act(read("act-1037.html"), 1037)
        sec = parse_section(read("act-1037-section-38229.html"), ref_of(act, 38229), act)
        lines = [ln for ln in sec.text.splitlines() if ln.strip()]
        self.assertTrue(lines[0].startswith("১৮। (১)"))
        self.assertTrue(any(ln.startswith("(২)") for ln in lines))
        self.assertIn("বলবৎ", sec.text)          # legacy 'বলবত্‍' folded
        for junk in BOILERPLATE:
            self.assertNotIn(junk, sec.text)

    def test_bangla_amendments_and_cross_act_links(self):
        act = parse_act(read("act-835.html"), 835)
        sec = parse_section(read("act-835-section-32516.html"), ref_of(act, 32516), act)
        self.assertEqual(sec.number, "২")
        self.assertTrue(sec.footnotes)
        self.assertTrue(all("সংশোধন" in f for f in sec.footnotes))
        self.assertIn(11, [r["act_id"] for r in sec.act_refs])   # links to the Penal Code

    def test_inherited_number_section(self):
        act = parse_act(read("act-24.html"), 24)
        sec = parse_section(read("act-24-section-4656.html"), ref_of(act, 4656), act)
        self.assertEqual((sec.number, sec.title), ("4", "“Conclusive proof”"))
        self.assertTrue(sec.text.startswith("When one fact"))

    def test_chunks_carry_context_and_notes(self):
        act = parse_act(read("act-835.html"), 835)
        sec = parse_section(read("act-835-section-32516.html"), ref_of(act, 32516), act)
        chunks = chunk_section(act, sec, max_chars=1200)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c.body) <= 1200 for c in chunks))
        self.assertTrue(chunks[0].text.startswith("নারী ও শিশু নির্যাতন দমন আইন, ২০০০ > ধারা ২: সংজ্ঞা"))
        self.assertIn("সংশোধনী:", chunks[0].text)
        self.assertNotIn("সংশোধনী:", chunks[0].body)

    def test_repealed_act_sections_inherit_flag(self):
        act = parse_act(read("act-836.html"), 836)
        sec = parse_section(read("act-836-section-32558.html"), ref_of(act, 32558), act)
        chunk = chunk_section(act, sec)[0]
        self.assertTrue(chunk.metadata["repealed"])
        self.assertIn("২০১০", chunk.metadata["repeal_note"])


class TestLegacyBangla(unittest.TestCase):
    def test_known_artefacts(self):
        cases = {
            "অাইনের": "আইনের", "স্থানান্ত্মর": "স্থানান্তর", "কতর্ৃক": "কর্তৃক",
            "কর্তৃপতেগর": "কর্তৃপক্ষের", "তগতিপূরণ": "ক্ষতিপূরণ", "পরিপ্রেতিগতে": "পরিপ্রেক্ষিতে",
            "বত্সর": "বৎসর", "উলি­খিত": "উল্লিখিত",
            "ত্মেগত্রে": "ক্ষেত্রে", "তেগত্রে": "ক্ষেত্রে", "ত্মগমতা": "ক্ষমতা", "কতৃর্ক": "কর্তৃক",
            "হস্ত্মান্তর": "হস্তান্তর", "সাতগ্য": "সাক্ষ্য", "পরীতগা": "পরীক্ষা",
            "লত্মেগ্য": "লক্ষ্যে", "তত্ত্মগণাত্": "তৎক্ষণাৎ",
        }
        for broken, fixed in cases.items():
            self.assertEqual(fix_legacy_bangla(broken), fixed, broken)

    def test_correct_words_untouched(self):
        for word in ("ব্যক্তিগত", "ক্ষতিগ্রস্ত", "আত্মসাৎ", "উত্তরাধিকার", "বস্তুগত", "যতগুলি",
                     "হস্তগত", "আত্মগোপন", "মারাত্মক", "তত্ত্ব", "সত্য", "প্রযুক্তিগত"):
            self.assertEqual(fix_legacy_bangla(word), word)

    def test_khanda_ta_folded_in_normalize(self):
        self.assertEqual(normalize("বলবত্‍"), "বলবৎ")


if __name__ == "__main__":
    unittest.main()
