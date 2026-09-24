"""Phase 5 tests: the checks that stand between retrieval and the user."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from evalkit.dataset import EvalItem  # noqa: E402
from evalkit.judge import deterministic_scores  # noqa: E402
from rag.answer import answer_question  # noqa: E402
from rag.chat import ChatSession, condense, looks_like_follow_up  # noqa: E402
from rag.embed import HashingEmbedder  # noqa: E402
from rag.guardrails import (  # noqa: E402
    GuardConfig,
    citation_coverage,
    factual_sentences,
    language_match,
    quote_fidelity,
    repair_instruction,
    run_checks,
    support_gate,
)
from rag.retrieve import Retriever  # noqa: E402
from rag.store import Hit, NumpyStore  # noqa: E402
from test_rag import CORPUS  # noqa: E402

MURDER = "যে ব্যক্তি হত্যা করিবে সে মৃত্যুদণ্ডে বা যাবজ্জীবন কারাদণ্ডে দণ্ডিত হইবে।"
HITS = [Hit("a", 0.61, "ctx", MURDER, {"act_id": 1, "section_id": 302, "act_title": "দণ্ডবিধি",
                                       "language": "bn", "section_number": "৩০২"}),
        Hit("b", 0.22, "ctx", "বীমা পলিসির সংজ্ঞা।", {"act_id": 2, "section_id": 2,
                                                      "act_title": "বীমা আইন", "language": "bn"})]


class TestSupportGate(unittest.TestCase):
    def test_off_by_default(self):
        self.assertEqual(support_gate(HITS, GuardConfig()), (True, ""))

    def test_empty_retrieval_always_blocked(self):
        ok, why = support_gate([], GuardConfig())
        self.assertFalse(ok)
        self.assertIn("nothing retrieved", why)

    def test_threshold_and_min_hits(self):
        self.assertTrue(support_gate(HITS, GuardConfig(min_score=0.5))[0])
        ok, why = support_gate(HITS, GuardConfig(min_score=0.9))
        self.assertFalse(ok)
        self.assertIn("0.61", why)                       # names the actual top score
        self.assertFalse(support_gate(HITS, GuardConfig(min_score=0.5, min_hits=2))[0])


class TestCitationCoverage(unittest.TestCase):
    def test_bangla_and_english_sentences_are_split(self):
        text = "প্রথম বাক্য এখানে শেষ [1]। দ্বিতীয় বাক্য কোন উদ্ধৃতি ছাড়া চলে।"
        cov = citation_coverage(text, 2)
        self.assertEqual(cov["n_sentences"], 2)
        self.assertEqual(len(cov["uncited"]), 1)
        self.assertAlmostEqual(cov["uncited_ratio"], 0.5)

    def test_headings_and_source_lines_are_not_claims(self):
        text = "## Summary\nThe punishment is death [1].\nSources:\n- [1] Penal Code"
        self.assertEqual(len(factual_sentences(text)), 2)   # the claim + the source bullet line

    def test_invalid_numbers_reported(self):
        cov = citation_coverage("Claim one [1]. Claim two [7].", 3)
        self.assertEqual(cov["cited"], [1])
        self.assertEqual(cov["invalid"], [7])

    def test_empty_answer_is_not_a_division_by_zero(self):
        self.assertEqual(citation_coverage("", 2)["uncited_ratio"], 0.0)


class TestQuoteFidelity(unittest.TestCase):
    def test_real_quote_passes_even_with_odd_spacing(self):
        text = 'আইনে বলা হইয়াছে “যে ব্যক্তি   হত্যা করিবে” [1]।'
        self.assertEqual(quote_fidelity(text, HITS, cited=[1])["fidelity"], 1.0)

    def test_fabricated_quote_is_caught(self):
        text = 'আইনে বলা হইয়াছে “এই কথাটি কোথাও নাই কিন্তু দেখিতে আসল” [1]।'
        res = quote_fidelity(text, HITS, cited=[1])
        self.assertEqual(res["fidelity"], 0.0)
        self.assertEqual(len(res["fabricated"]), 1)

    def test_quote_from_an_uncited_excerpt_is_a_miscitation(self):
        text = 'ধারা ৩০২ বলে “বীমা পলিসির সংজ্ঞা” [1]।'   # that text is in hit 2, cited 1
        self.assertEqual(quote_fidelity(text, HITS, cited=[1])["fidelity"], 0.0)

    def test_no_quotes_scores_perfect(self):
        self.assertEqual(quote_fidelity("কোন উদ্ধৃতি নাই [1]।", HITS, cited=[1])["n_quotes"], 0)


class TestLanguageAndChecks(unittest.TestCase):
    def test_language_match(self):
        self.assertTrue(language_match("হত্যার শাস্তি কী?", "মৃত্যুদণ্ড [1]।"))
        self.assertFalse(language_match("হত্যার শাস্তি কী?", "The punishment is death [1]."))

    def test_run_checks_collects_every_failure(self):
        bad = 'The Act says “invented wording here” and more claims without citation.'
        checks = run_checks("হত্যার শাস্তি কী?", bad, HITS, GuardConfig())
        self.assertIn("uncited_sentences", checks["failures"])
        self.assertIn("fabricated_quotes", checks["failures"])
        self.assertIn("language_mismatch", checks["failures"])

    def test_clean_answer_has_no_failures(self):
        good = "হত্যার শাস্তি মৃত্যুদণ্ড বা যাবজ্জীবন কারাদণ্ড [1]।"
        self.assertEqual(run_checks("হত্যার শাস্তি কী?", good, HITS, GuardConfig())["failures"], [])

    def test_repair_instruction_names_the_problems(self):
        checks = run_checks("হত্যার শাস্তি কী?", 'It says “not real” with no citation [9].',
                            HITS, GuardConfig())
        msg = repair_instruction(checks)
        self.assertIn("NOT_FOUND", msg)
        self.assertIn("do not exist", msg)
        self.assertIn("not appear in the excerpts", msg)


class TestAnswerWithGuards(unittest.TestCase):
    def setUp(self):
        emb = HashingEmbedder(dim=256)
        store = NumpyStore(emb.dim, emb.name)
        store.add(emb.encode_passages([c["text"] for c in CORPUS]), CORPUS)
        self.r = Retriever(emb, store)

    def test_abstains_before_calling_the_model(self):
        def boom(system, prompt):
            raise AssertionError("the model must not be called when support is weak")

        ans = answer_question("হত্যার শাস্তি কী?", self.r, boom, k=3,
                              guard=GuardConfig(min_score=0.99))
        self.assertTrue(ans.refused and ans.abstained)
        self.assertEqual(ans.llm_calls, 0)

    def test_repair_runs_once_and_keeps_the_better_answer(self):
        calls = []

        def llm(system, prompt):
            calls.append(prompt)
            return ("হত্যার শাস্তি মৃত্যুদণ্ড এবং আরও অনেক কিছু বলা হইয়াছে এখানে।"
                    if len(calls) == 1 else "হত্যার শাস্তি মৃত্যুদণ্ড [1]।")

        ans = answer_question("হত্যার শাস্তি কী?", self.r, llm, k=3)
        self.assertEqual(len(calls), 2)
        self.assertTrue(ans.repaired)
        self.assertEqual(ans.failures, [])
        self.assertIn("previous answer", calls[1])
        self.assertEqual(ans.cited, [1])

    def test_failed_repair_keeps_the_original_and_reports(self):
        ans = answer_question("হত্যার শাস্তি কী?", self.r,
                              lambda s, p: "No citation anywhere in this English answer.", k=3)
        self.assertTrue(ans.repaired)
        self.assertIn("uncited_sentences", ans.failures)   # reported, never hidden

    def test_repair_can_be_switched_off(self):
        calls = []

        def llm(system, prompt):
            calls.append(prompt)
            return "No citation at all here."

        answer_question("হত্যার শাস্তি কী?", self.r, llm, k=3, guard=GuardConfig(repair=False))
        self.assertEqual(len(calls), 1)

    def test_refusal_skips_checks(self):
        ans = answer_question("VAT?", self.r, lambda s, p: "NOT_FOUND: nothing on VAT", k=3)
        self.assertTrue(ans.refused)
        self.assertFalse(ans.repaired)
        self.assertIsNone(ans.checks.get("coverage"))     # no guardrail work on a refusal
        self.assertIsNone(ans.checks.get("confidence"))   # and no confidence number either

    def test_guard_metrics_reach_the_evaluator(self):
        item = EvalItem("q1", "হত্যার শাস্তি কী?", "bn", "single", ["1:302"], "মৃত্যুদণ্ড")
        ans = answer_question("হত্যার শাস্তি কী?", self.r,
                              lambda s, p: "হত্যার শাস্তি মৃত্যুদণ্ড [1]।", k=3)
        scores = deterministic_scores(item, ans)
        self.assertEqual(scores["citation_coverage"], 1.0)
        self.assertEqual(scores["quote_fidelity"], 1.0)
        self.assertEqual(scores["language_match"], 1.0)
        self.assertEqual(scores["clean_first_pass"], 1.0)


class TestChat(unittest.TestCase):
    def setUp(self):
        emb = HashingEmbedder(dim=256)
        store = NumpyStore(emb.dim, emb.name)
        store.add(emb.encode_passages([c["text"] for c in CORPUS]), CORPUS)
        self.r = Retriever(emb, store)

    def test_follow_up_detection(self):
        self.assertTrue(looks_like_follow_up("আর শাস্তি?"))
        self.assertTrue(looks_like_follow_up("and the fine?"))
        self.assertFalse(looks_like_follow_up(
            "What is the punishment for murder under the Penal Code of 1860?"))

    def test_condense_only_fires_with_history(self):
        llm = lambda s, p: "ধারা ৩০২ অনুযায়ী শাস্তি কী?"  # noqa: E731
        self.assertEqual(condense([], "আর শাস্তি?", llm), "আর শাস্তি?")
        self.assertEqual(condense([("ধারা ৩০২ কী?", "হত্যা")], "আর শাস্তি?", llm),
                         "ধারা ৩০২ অনুযায়ী শাস্তি কী?")

    def test_condense_rejects_a_degenerate_rewrite(self):
        self.assertEqual(condense([("ক", "খ")], "আর শাস্তি?", lambda s, p: ""), "আর শাস্তি?")
        self.assertEqual(condense([("ক", "খ")], "আর শাস্তি?", lambda s, p: "x" * 500), "আর শাস্তি?")

    def test_session_rewrites_for_retrieval_but_reports_the_real_question(self):
        seen = []

        def llm(system, prompt):
            seen.append(prompt)
            return ("হত্যার শাস্তি কী?" if "Follow-up" in prompt
                    else "হত্যার শাস্তি মৃত্যুদণ্ড [1]।")

        session = ChatSession(self.r, llm, k=3)
        session.ask("দণ্ডবিধি কী?")
        ans = session.ask("আর শাস্তি?")
        self.assertEqual(ans.question, "আর শাস্তি?")
        self.assertEqual(ans.checks.get("rewritten_query"), "হত্যার শাস্তি কী?")
        self.assertEqual(len(session.history), 2)


if __name__ == "__main__":
    unittest.main()
