"""Topic table, practical tips and the general-guidance fallback."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.answer import answer_question, answer_question_stream  # noqa: E402
from rag.embed import HashingEmbedder  # noqa: E402
from rag.guardrails import (  # noqa: E402
    GuardConfig,
    citation_coverage,
    law_in_tips,
    run_checks,
    split_tips,
)
from rag.llm import LLMError  # noqa: E402
from rag.pipeline import RetrievalConfig, SearchPipeline  # noqa: E402
from rag.refs import ActResolver  # noqa: E402
from rag.retrieve import Retriever  # noqa: E402
from rag.store import Hit, NumpyStore  # noqa: E402
from rag.topics import TopicIndex, match_topics, pin_topic_sections  # noqa: E402


def rec(cid, act_id, title, number, body, lang="bn", section_title=""):
    return {"chunk_id": cid, "text": f"{title} > {number}\n\n{body}", "body": body,
            "metadata": {"type": "section", "act_id": act_id, "act_title": title,
                         "repealed": False, "section_number": number,
                         "section_number_ascii": number, "section_title": section_title,
                         "language": lang}}


RECORDS = [
    rec("1014:45", 1014, "ভোক্তা-অধিকার সংরক্ষণ আইন, ২০০৯", "45",
        "প্রতিশ্রুত পণ্য বা সেবা যথাযথভাবে বিক্রয় বা সরবরাহ না করিবার দণ্ড", section_title="প্রতিশ্রুত পণ্য"),
    rec("1014:60", 1014, "ভোক্তা-অধিকার সংরক্ষণ আইন, ২০০৯", "60",
        "কারণ উদ্ভব হইবার ৩০ দিনের মধ্যে অভিযোগ দায়ের", section_title="অভিযোগ দায়ের"),
    rec("1014:2", 1014, "ভোক্তা-অধিকার সংরক্ষণ আইন, ২০০৯", "2", "সংজ্ঞা ভোক্তা অর্থ"),
    rec("11:499", 11, "The Penal Code, 1860", "499",
        "Whoever by words makes any imputation intending to harm reputation", "en", "Defamation"),
    rec("11:500", 11, "The Penal Code, 1860", "500",
        "Whoever defames another shall be punished with simple imprisonment", "en",
        "Punishment for defamation"),
    rec("11:302", 11, "The Penal Code, 1860", "302", "Whoever commits murder shall be punished",
        "en", "Punishment for murder"),
    rec("952:123", 952, "বাংলাদেশ শ্রম আইন, ২০০৬", "123", "মজুরি পরিশোধের সময়", section_title="মজুরি পরিশোধের সময়"),
    rec("952:132", 952, "বাংলাদেশ শ্রম আইন, ২০০৬", "132", "মজুরি হইতে কর্তন বা মজুরি পরিশোধে বিলম্ব"),
    rec("952:2", 952, "বাংলাদেশ শ্রম আইন, ২০০৬", "2", "সংজ্ঞা শ্রমিক অর্থ"),
    # Same title phrase under a different id: the hint must still resolve by title.
    rec("77:7", 77, "বাড়ি ভাড়া নিয়ন্ত্রণ আইন, ১৯৯১", "7", "মানসম্মত ভাড়ার অধিক ভাড়া আদায়যোগ্য নহে"),
    rec("1037:2", 1037, "বীমা আইন, ২০১০", "2", "বীমা সংজ্ঞা বীমাকারী অর্থ"),
]


class TestMatching(unittest.TestCase):
    def test_scenarios_reach_their_topics(self):
        cases = {
            "I bought a phone that was defective and the shop refuses to replace it": "defective goods",
            "Someone posted false and defamatory things about me on Facebook": "defamation",
            "আমার বস তিন মাস ধরে বেতন দিচ্ছেন না": "wages",
            "My employer dismissed me without notice": "dismissal",
            "যৌতুকের জন্য আমার স্বামী আমাকে মারধর করে": "dowry",
            "চেক ডিজঅনার হয়েছে": "cheque",
            "আমার বাড়িওয়ালা হঠাৎ ভাড়া দ্বিগুণ করেছেন": "rent",
        }
        for question, topic in cases.items():
            self.assertIn(topic, [t.name for t in match_topics(question)], question)

    def test_paraphrased_gaps_reach_their_topics(self):
        import json
        want = {"1014": "consumer", "11": "defamation", "952": "wages"}
        for line in (ROOT / "data" / "eval" / "eval_gaps.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            topic = want[row["gold"][0].split(":")[0]]
            self.assertIn(topic, [t.name for t in match_topics(row["question"])], row["question"])

    def test_paraphrase_entries_need_their_context_word(self):
        for question in ("Do I have to pay tax on my earnings from abroad?",
                         "Is it false that a will must be registered?",
                         "Can I buy land that is under a mortgage?",
                         "আমি দোকান ভাড়া নিতে চাই, চুক্তিতে কী লিখব?"):
            names = [t.name for t in match_topics(question)]
            for topic in ("wages", "defamation", "consumer"):
                self.assertNotIn(topic, names, question)

    def test_same_name_entries_name_the_same_acts(self):
        from rag.topics import TOPICS
        by_name = {}
        for t in TOPICS:
            by_name.setdefault(t.name, set()).add(t.acts)
        self.assertEqual({n: a for n, a in by_name.items() if len(a) > 1}, {})
        self.assertEqual([t.name for t in match_topics("my reputation is ruined by false posts online")],
                         ["defamation"])

    def test_two_part_topics_need_both_words(self):
        names = lambda q: [t.name for t in match_topics(q)]  # noqa: E731
        self.assertIn("contract fraud", names("প্রতারণা করে সম্মতি আদায় করা হলে চুক্তির কী হয়?"))
        self.assertNotIn("contract fraud", names("Can a minor sign a contract?"))
        self.assertEqual(names("সন্তান কি বাবা-মায়ের ভরণপোষণ দিতে বাধ্য?")[0], "parent maintenance")
        self.assertEqual(names("আমার স্বামী ভরণপোষণ দেয় না"), ["maintenance"])

    def test_no_false_positives_from_substrings(self):
        for question in ("what is the first step", "a firm's duty", "আত্মহত্যার প্ররোচনা",
                         "the current insurance law", "বীমা আইনের সংজ্ঞা"):
            self.assertEqual(match_topics(question), [], question)


class TestTopicIndex(unittest.TestCase):
    def setUp(self):
        self.index = TopicIndex(ActResolver(RECORDS))

    def test_english_question_reaches_the_bangla_act(self):
        hits, acts = self.index.resolve("The shop sold me a faulty fridge, what can I do?")
        self.assertEqual([h.chunk_id for h in hits], ["1014:45", "1014:60"])   # 66 not indexed
        self.assertIn(1014, acts)
        self.assertTrue(all(h.metadata["topic"] for h in hits))

    def test_paraphrases_pin_the_same_sections(self):
        pinned = lambda q: [h.chunk_id for h in self.index.resolve(q)[0]]  # noqa: E731
        self.assertEqual(pinned("My boss hasn't paid me for two months"), ["952:123", "952:132"])
        self.assertEqual(pinned("The seller won't take back the washing machine I bought"),
                         ["1014:45", "1014:60"])
        self.assertEqual(pinned("A neighbour is telling everyone I am a thief, which is untrue"),
                         ["11:499", "11:500"])

    def test_hint_with_the_wrong_id_falls_back_to_the_title(self):
        hits, _ = self.index.resolve("my landlord doubled the rent")
        self.assertEqual([h.chunk_id for h in hits], ["77:7"])

    def test_missing_act_adds_nothing(self):
        self.assertEqual(self.index.resolve("my husband gave me talaq"), ([], []))


class TestPinning(unittest.TestCase):
    def hit(self, cid, score, **meta):
        return Hit(cid, score, cid, cid, meta)

    def test_reserved_places_leave_two_for_the_search(self):
        found = [self.hit(f"s{i}", 1 - i / 10) for i in range(5)]
        pins = [self.hit(f"p{i}", 0.0, topic="t") for i in range(4)]
        out = pin_topic_sections(found, pins, k=5, slots=3)
        self.assertEqual([h.chunk_id for h in out], ["s0", "s1", "p0", "p1", "p2"])
        out = pin_topic_sections(found, pins, k=3, slots=3)
        self.assertEqual([h.chunk_id for h in out], ["s0", "s1", "p0"])
        self.assertEqual([round(h.score, 2) for h in out], [1.0, 0.9, 0.9])   # stays monotone

    def test_requested_section_stays_first_and_found_pins_keep_their_score(self):
        found = [self.hit("req", 2.0, requested=True), self.hit("s0", 0.9), self.hit("p0", 0.4),
                 self.hit("s1", 0.3)]
        out = pin_topic_sections(found, [self.hit("p0", 0.0, topic="t"), self.hit("p1", 0.0, topic="t")],
                                 k=4, slots=3)
        self.assertEqual([h.chunk_id for h in out], ["req", "s0", "p0", "p1"])
        self.assertEqual(out[2].score, 0.4)                # found by the search: keeps its place
        self.assertEqual(out[2].metadata["topic"], "t")


class TestPipeline(unittest.TestCase):
    def setUp(self):
        emb = HashingEmbedder(dim=256)
        store = NumpyStore(emb.dim, emb.name)
        store.add(emb.encode_passages([r["text"] for r in RECORDS]), RECORDS)
        self.dense = Retriever(emb, store)

    def pipeline(self, **cfg):
        return SearchPipeline(RetrievalConfig(**cfg), dense=self.dense)

    def test_governing_sections_are_in_the_results(self):
        q = "কেউ আমার নামে বদনাম ছড়াচ্ছে, আমি কী করব?"     # Bangla question, English act
        off = [h.chunk_id for h in self.pipeline().search(q, k=4)]
        on = [h.chunk_id for h in self.pipeline(topics=True).search(q, k=4)]
        self.assertIn("11:499", on)
        self.assertIn("11:500", on)
        self.assertNotIn("11:500", off)

    def test_named_section_switches_topics_off(self):
        p = self.pipeline(topics=True, resolve_refs=True)
        hits = p.search("Penal Code section 302: is defamation like murder?", k=3)
        self.assertEqual(hits[0].chunk_id, "11:302")
        self.assertNotIn("topic", hits[0].metadata)


class TestPracticalTips(unittest.TestCase):
    ANSWER = ("You can complain to the Directorate within 30 days [1].\n\n"
              "Practical tips:\n- Keep the receipt and the warranty card.\n"
              "- Write down when you reported the fault and to whom.")

    def test_tips_are_outside_the_citation_checks(self):
        grounded, tips = split_tips(self.ANSWER)
        self.assertTrue(tips.startswith("Practical tips"))
        self.assertNotIn("receipt", grounded)
        self.assertEqual(citation_coverage(self.ANSWER, 3)["uncited_ratio"], 0.0)

    def test_law_in_tips_is_a_failure(self):
        bad = self.ANSWER + "\n- The seller faces imprisonment under section 45."
        self.assertTrue(law_in_tips(bad))
        hits = [Hit("a", 1.0, "t", "complain within 30 days", {})]
        self.assertIn("law_in_tips", run_checks("faulty phone?", bad, hits, GuardConfig())["failures"])
        self.assertFalse(law_in_tips(self.ANSWER))
        bn = "অভিযোগ করুন [1]।\n\n**ব্যবহারিক পরামর্শ:**\n- রসিদ ও টাকার প্রমাণ রাখুন।"
        self.assertFalse(law_in_tips(bn))
        self.assertEqual(split_tips(bn)[0], "অভিযোগ করুন [1]।")


class TestGeneralGuidance(unittest.TestCase):
    def setUp(self):
        emb = HashingEmbedder(dim=256)
        store = NumpyStore(emb.dim, emb.name)
        store.add(emb.encode_passages([r["text"] for r in RECORDS]), RECORDS)
        self.r = Retriever(emb, store)

    @staticmethod
    def llm(system, prompt):
        if system.startswith("You help people"):
            return "This is a family law matter [2]. Go to the Family Court."
        return "NOT_FOUND: nothing on inheritance shares"

    def test_off_by_default(self):
        ans = answer_question("How is my father's land divided?", self.r, self.llm, k=3)
        self.assertTrue(ans.refused)
        self.assertFalse(ans.general)

    def test_refusal_becomes_labelled_guidance(self):
        ans = answer_question("How is my father's land divided?", self.r, self.llm, k=3,
                              guard=GuardConfig(general_fallback=True))
        self.assertFalse(ans.refused)
        self.assertTrue(ans.general)
        self.assertTrue(ans.text.startswith("General guidance, not from the indexed laws"))
        self.assertIn("16430", ans.text)
        self.assertNotIn("[2]", ans.text)              # no excerpts, so no citations
        self.assertEqual(ans.cited, [])
        self.assertEqual(ans.llm_calls, 2)
        self.assertTrue(ans.checks["grounded_reply"].startswith("NOT_FOUND"))

    def test_bangla_label_and_weak_retrieval(self):
        ans = answer_question("উত্তরাধিকার সূত্রে জমি কীভাবে ভাগ হয়?", self.r,
                              lambda s, p: "এটি পারিবারিক আইনের বিষয়।", k=3,
                              guard=GuardConfig(min_score=0.99, general_fallback=True))
        self.assertTrue(ans.general and ans.abstained)
        self.assertTrue(ans.text.startswith("সাধারণ নির্দেশনা"))
        self.assertIn("১৬৪৩০", ans.text)

    def test_model_failure_keeps_the_refusal(self):
        def llm(system, prompt):
            if system.startswith("You help people"):
                raise LLMError("down")
            return "NOT_FOUND: nothing"

        ans = answer_question("inheritance?", self.r, llm, k=3, guard=GuardConfig(general_fallback=True))
        self.assertTrue(ans.refused)
        self.assertFalse(ans.general)

    def test_off_topic_is_still_refused(self):
        ans = answer_question("what is the weather in Dhaka", self.r, self.llm, k=3,
                              guard=GuardConfig(general_fallback=True))
        self.assertTrue(ans.refused)

    def test_stream_announces_the_replacement(self):
        def stream(system, prompt):
            yield "NOT_FOUND: nothing"

        events = list(answer_question_stream("inheritance?", self.r, stream, k=3,
                                             guard=GuardConfig(general_fallback=True),
                                             repair_llm=self.llm))
        self.assertIn({"type": "status", "stage": "general_guidance"}, events)
        self.assertTrue(events[-1]["answer"].general)


if __name__ == "__main__":
    unittest.main()
