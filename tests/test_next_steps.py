"""What to do next, plain language and legal-aid contacts: the checklist read out of an
answer, the hotlines that fit a situation, the plain prompt, and the service fields."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from rag.answer import PLAIN_SYSTEM, SYSTEM, answer_question  # noqa: E402
from rag.glossary import terms_in  # noqa: E402
from rag.guardrails import GuardConfig  # noqa: E402
from rag.legalaid import CONTACTS, DISTRICTS, contacts_for, directory  # noqa: E402
from rag.nextsteps import GENERAL_TIPS, checklist, split_answer  # noqa: E402
from rag.prompts import REGISTRY  # noqa: E402
from rag.scope import apply_notices  # noqa: E402

try:
    from starlette.testclient import TestClient

    from service.app import ServiceConfig, create_app
    from test_service import CORPUS, fake_components
    HAVE_STARLETTE = True
except ImportError:                       # pragma: no cover
    HAVE_STARLETTE = False

WAGES_Q = "My employer has not paid my wages for two months. What can I do?"
WAGES_A = """Your employer must pay wages within seven working days [1].

**What you can do:**
1. Send a written demand to your employer [1].
2. File a claim in the Labour Court
   within 12 months [2].

**Practical tips:**
- Keep your pay slips.
- Write down the dates you worked.
"""
DOWRY_Q = "আমার স্বামী যৌতুকের জন্য মারধর করে, আমি কী করব?"
DOWRY_A = """যৌতুকের জন্য মারধর শাস্তিযোগ্য অপরাধ [1]।

### আপনি যা করতে পারেন
১. থানায় এজাহার দায়ের করুন [1]।

২. নারী ও শিশু নির্যাতন দমন ট্রাইব্যুনালে অভিযোগ করুন [2]।

ব্যবহারিক পরামর্শ:
- চিকিৎসার কাগজ রাখুন।"""


class TestChecklist(unittest.TestCase):
    def test_steps_keep_their_citations_and_leave_the_answer(self):
        text = apply_notices(WAGES_Q, WAGES_A)
        body, steps, tips = split_answer(text)
        self.assertEqual([s["text"] for s in steps],
                         ["Send a written demand to your employer [1].",
                          "File a claim in the Labour Court within 12 months [2]."])
        self.assertEqual([s["cites"] for s in steps], [[1], [2]])
        self.assertEqual(tips, ["Keep your pay slips.", "Write down the dates you worked."])
        # The lists move to the checklist; the grounded text and the notice stay.
        self.assertIn("seven working days [1]", body)
        self.assertIn("16430", body)
        self.assertNotIn("written demand", body)
        self.assertNotIn("pay slips", body)

    def test_bangla_steps_with_blank_lines_between_them(self):
        c = checklist(DOWRY_Q, apply_notices(DOWRY_Q, DOWRY_A))
        self.assertEqual(c["lang"], "bn")
        self.assertEqual(len(c["steps"]), 2)
        self.assertEqual(c["tips"], ["চিকিৎসার কাগজ রাখুন।"])
        self.assertFalse(c["generic_tips"])
        self.assertNotIn("১৬৪৩০", " ".join(c["tips"]))      # the notice is not a tip
        self.assertEqual([h["phone"] for h in c["help"]], ["16430", "109", "999"])

    def test_situation_without_steps_gets_general_tips_and_help(self):
        c = checklist(WAGES_Q, "Wages are due within seven working days [1].")
        self.assertEqual(c["steps"], [])
        self.assertTrue(c["generic_tips"])
        self.assertEqual(c["tips"], list(GENERAL_TIPS["en"]))
        self.assertIsNone(c["body"])                       # nothing moved out of the answer
        self.assertIn("16357", [h["phone"] for h in c["help"]])

    def test_no_checklist_for_a_lookup_or_a_refusal(self):
        self.assertIsNone(checklist("What does section 302 of the Penal Code say?",
                                    "Whoever commits murder shall be punished with death [1]."))
        self.assertIsNone(checklist(WAGES_Q, "NOT_FOUND: nothing on wages", refused=True))

    def test_general_guidance_is_not_mined_for_steps(self):
        c = checklist(WAGES_Q, "General guidance...\n\nWhat you can do:\n1. Go to court.",
                      general=True)
        self.assertEqual(c["steps"], [])
        self.assertTrue(c["generic_tips"])

    def test_a_paragraph_after_the_list_ends_it(self):
        text = "Law [1].\n\nWhat you can do:\n1. Complain [1].\nwithin a week [1].\n\nThis is not advice."
        body, steps, _ = split_answer(text)
        self.assertEqual(steps[0]["text"], "Complain [1]. within a week [1].")
        self.assertIn("This is not advice.", body)


class TestLegalAid(unittest.TestCase):
    def test_legal_aid_hotline_always_comes_with_the_situation_lines(self):
        self.assertEqual([c["id"] for c in contacts_for("What does section 10 say?")], ["legal_aid"])
        self.assertEqual([c["id"] for c in contacts_for("The shop sold me a faulty fridge")],
                         ["legal_aid", "consumer"])

    def test_danger_puts_999_first(self):
        self.assertEqual(contacts_for("I was raped, what can I do?")[0]["phone"], "999")

    def test_bangla_question_gets_bangla_names(self):
        c = contacts_for("বাল্যবিবাহ ঠেকাতে কী করব?")
        self.assertEqual(c[0]["name"], CONTACTS["legal_aid"].name_bn)
        self.assertIn("109", [x["phone"] for x in c])

    def test_all_64_districts_once_each(self):
        self.assertEqual(len(DISTRICTS), 64)
        self.assertEqual(len({en for _, en, _ in DISTRICTS}), 64)
        self.assertEqual(len({div for div, _, _ in DISTRICTS}), 8)
        d = directory()
        self.assertEqual(len(d["districts"]), 64)
        self.assertIn("{district}", d["office"]["bn"])


class TestPlainLanguage(unittest.TestCase):
    def test_plain_prompt_is_the_v6_contract_plus_one_rule(self):
        self.assertTrue(PLAIN_SYSTEM.startswith(SYSTEM))
        self.assertIn("PLAIN LANGUAGE", PLAIN_SYSTEM)
        self.assertIn("answer-system/v6-plain", REGISTRY)
        self.assertIn("general-guidance/v1-plain", REGISTRY)

    def test_answer_question_uses_the_plain_prompt_when_asked(self):
        if not HAVE_STARLETTE:
            self.skipTest("needs the test corpus")
        pipeline, _, _ = fake_components()
        seen = []

        def llm(system, prompt):
            seen.append(system)
            return "হত্যার শাস্তি মৃত্যুদণ্ড [1]।"

        a = answer_question("হত্যার শাস্তি কী?", pipeline, llm, k=2, guard=GuardConfig(), plain=True)
        self.assertEqual(seen[0], PLAIN_SYSTEM)
        self.assertEqual(a.checks["prompt_id"], "answer-system/v6-plain")
        answer_question("হত্যার শাস্তি কী?", pipeline, llm, k=2, guard=GuardConfig())
        self.assertEqual(seen[-1], SYSTEM)

    def test_glossary_finds_words_in_order_and_whole_english_words(self):
        terms = terms_in("You can apply for bail [1]. A suitable court is the magistrate.", "en")
        self.assertEqual([t["term"] for t in terms], ["bail", "magistrate"])
        bn = terms_in("থানায় এজাহার দিন, পরে জামিনের আবেদন করুন [1]।", "bn")
        self.assertEqual([t["term"] for t in bn], ["এজাহার", "জামিন"])


@unittest.skipUnless(HAVE_STARLETTE, "starlette not installed")
class TestServiceFields(unittest.TestCase):
    ANSWER = ("হত্যার শাস্তি মৃত্যুদণ্ড [1]।\n\nআপনি যা করতে পারেন:\n"
              "১. থানায় এজাহার দায়ের করুন [1]।")

    def client(self):
        pipeline, _, _ = fake_components()
        self.systems: list[str] = []

        def llm(system, prompt):
            self.systems.append(system)
            return self.ANSWER

        def stream(system, prompt):
            self.systems.append(system)
            return iter([self.ANSWER])

        app = create_app(ServiceConfig(rate_per_min=6000, burst=100, agent_enabled=False),
                         pipeline=pipeline, llm=llm, stream_llm=stream, records=CORPUS)
        return TestClient(app)

    def test_ask_carries_the_checklist_and_plain_is_cached_apart(self):
        c = self.client()
        q = "কেউ আমার ভাইকে খুন করেছে, আমি কী করব?"
        r = c.post("/ask", json={"question": q}).json()
        self.assertFalse(r["plain"])
        self.assertEqual(r["glossary"], [])
        self.assertEqual(r["next_steps"]["steps"][0]["cites"], [1])
        self.assertEqual(r["next_steps"]["help"][0]["phone"], "999")
        self.assertNotIn("থানায়", r["next_steps"]["body"])
        p = c.post("/ask", json={"question": q, "plain": True}).json()
        self.assertTrue(p["plain"])
        self.assertFalse(p["cached"])                    # not the non-plain answer
        self.assertEqual(self.systems[-1], PLAIN_SYSTEM)
        self.assertIn("এজাহার", [g["term"] for g in p["glossary"]])
        # The permalink keeps the checklist.
        stored = c.get(f"/a/{p['id']}?format=json").json()
        self.assertEqual(stored["next_steps"]["steps"], p["next_steps"]["steps"])

    def test_stream_plain(self):
        c = self.client()
        body = c.post("/ask/stream", json={"question": "হত্যার শাস্তি কী?", "plain": True}).text
        final = [json.loads(line[6:]) for line in body.splitlines()
                 if line.startswith("data: ") and '"next_steps"' in line][-1]
        self.assertTrue(final["plain"])
        self.assertEqual(self.systems[-1], PLAIN_SYSTEM)

    def test_legal_aid_directory_endpoint(self):
        r = self.client().get("/legal-aid")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["districts"]), 64)
        self.assertIn("16430", [x["phone"] for x in r.json()["contacts"]])
