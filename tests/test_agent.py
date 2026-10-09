"""Phase 6 tests: tools, evidence numbering, and every way the loop can go wrong.

The LLM is scripted, so these test the control flow — which is the part that
decides whether an agent is shippable.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from rag.agent import AgentConfig, LegalAgent, _parse_action  # noqa: E402
from rag.embed import HashingEmbedder  # noqa: E402
from rag.pipeline import RetrievalConfig, SearchPipeline  # noqa: E402
from rag.retrieve import Retriever  # noqa: E402
from rag.store import NumpyStore  # noqa: E402
from rag.tools import EvidenceBook, SectionLookup, ToolBox  # noqa: E402
from test_rag import CORPUS, chunk  # noqa: E402

# Section 3 points at section 7, which exists — a two-hop question.
REFS = [
    chunk("s3", "বীমা আইন > ধারা ৩: প্রযোজ্যতা\n\nধারা ৭ এর বিধান সাপেক্ষে ইহা প্রযোজ্য হইবে।",
          act_id=1, section_id=3, section_number="৩", section_number_ascii="3",
          section_title="প্রযোজ্যতা", refs=["7"]),
    chunk("s7", "বীমা আইন > ধারা ৭: শর্তাবলি\n\nনিবন্ধনের শর্তাবলি এই ধারায় বর্ণিত হইল।",
          act_id=1, section_id=7, section_number="৭", section_number_ascii="7",
          section_title="শর্তাবলি"),
]
DOCS = CORPUS + REFS


def build():
    emb = HashingEmbedder(dim=256)
    store = NumpyStore(emb.dim, emb.name)
    store.add(emb.encode_passages([c["text"] for c in DOCS]), DOCS)
    pipeline = SearchPipeline(RetrievalConfig(mode="dense"), dense=Retriever(emb, store))
    return pipeline, DOCS


class ScriptedLLM:
    """Replies in order; extra calls repeat the last reply. Records every prompt."""

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def __call__(self, system, prompt):
        self.prompts.append(prompt)
        i = min(len(self.prompts) - 1, len(self.replies) - 1)
        return self.replies[i]


class TestEvidenceBook(unittest.TestCase):
    def test_numbers_are_stable_and_never_reused(self):
        book = EvidenceBook()
        pipeline, _ = build()
        first = pipeline.search("হত্যার শাস্তি", k=2)
        n1 = book.add(first)
        n2 = book.add(first)                       # same chunks, second tool call
        self.assertEqual(n1, n2)                   # [1] still means what it meant
        self.assertEqual(len(book), len(first))

    def test_render_shows_citation_head_and_refs(self):
        book = EvidenceBook()
        book.add([__import__("rag.store", fromlist=["Hit"]).Hit(
            "x", 1.0, "t", "body text", {"act_id": 1, "act_title": "বীমা আইন", "language": "bn",
                                         "section_number": "৩", "section_title": "প্রযোজ্যতা",
                                         "refs": ["7"]})])
        out = book.render()
        self.assertIn("[1] বীমা আইন, ধারা ৩", out)
        self.assertIn("refers to sections: 7", out)


class TestTools(unittest.TestCase):
    def setUp(self):
        self.pipeline, records = build()
        self.book = EvidenceBook()
        self.tools = ToolBox(self.pipeline, SectionLookup(records), self.book)

    def test_search_adds_evidence(self):
        out = self.tools.search("হত্যার শাস্তি", k=2)
        self.assertIn("[1]", out)
        self.assertGreater(len(self.book), 0)

    def test_get_section_by_number(self):
        self.assertIn("শর্তাবলি", self.tools.get_section(1, "7"))
        self.assertIn("No section", self.tools.get_section(1, "999"))

    def test_follow_refs_resolves_a_cross_reference(self):
        self.tools.search("প্রযোজ্যতা ধারা ৩", k=3)
        n = next(i + 1 for i, h in enumerate(self.book.hits) if h.chunk_id == "s3")
        out = self.tools.follow_refs(n)
        self.assertIn("শর্তাবলি", out)                 # section 7 was fetched

    def test_follow_refs_handles_missing_and_empty(self):
        self.assertIn("No excerpt", self.tools.follow_refs(99))
        self.tools.search("হত্যার শাস্তি", k=1)
        self.assertIn("refers to no other provision", self.tools.follow_refs(1))

    def test_dispatch_rejects_unknown_tools_and_bad_args(self):
        self.assertIn("Unknown tool", self.tools.run("delete_everything", {}))
        self.assertIn("Bad arguments", self.tools.run("get_section", {}))
        self.assertIn("[1]", self.tools.run("search", {"query": "হত্যা", "nonsense": 1}))

    def test_tool_errors_do_not_raise(self):
        self.assertIn("failed", self.tools.run("get_section", {"act_id": "abc", "section": "1"}))


class TestActionParsing(unittest.TestCase):
    def test_parses_json_with_surrounding_noise(self):
        tool, args = _parse_action('THINK: need it\nACTION: {"tool": "search", '
                                   '"args": {"query": "হত্যা"}}\nextra prose')
        self.assertEqual(tool, "search")
        self.assertEqual(args["query"], "হত্যা")

    def test_rejects_broken_json(self):
        self.assertEqual(_parse_action('ACTION: {"tool": "search",'), (None, {}))
        self.assertEqual(_parse_action("no action here"), (None, {}))


class TestAgentLoop(unittest.TestCase):
    def setUp(self):
        self.pipeline, self.records = build()

    def agent(self, llm, **cfg):
        return LegalAgent(self.pipeline, self.records, llm, AgentConfig(**cfg))

    def test_multi_hop_search_then_follow_refs_then_answer(self):
        llm = ScriptedLLM(
            'THINK: find the section\nACTION: {"tool": "search", "args": {"query": "প্রযোজ্যতা", "k": 3}}',
            'THINK: it points at another section\nACTION: {"tool": "follow_refs", "args": {"excerpt": 1}}',
            "ANSWER: ধারা ৩ ধারা ৭ সাপেক্ষে প্রযোজ্য [1]। শর্তাবলি ধারা ৭ এ আছে [2]।",
        )
        ans = self.agent(llm).run("ধারা ৩ কীসের উপর নির্ভরশীল?")
        self.assertEqual(ans.checks["stop_reason"], "answered")
        self.assertEqual(ans.checks["steps"], 2)
        self.assertEqual([t["tool"] for t in ans.checks["trace"] if t["type"] == "tool"],
                         ["search", "follow_refs"])
        self.assertEqual(ans.cited, [1, 2])
        self.assertFalse(ans.refused)

    def test_evidence_from_every_step_is_citable(self):
        llm = ScriptedLLM(
            'ACTION: {"tool": "search", "args": {"query": "হত্যার শাস্তি", "k": 1}}',
            'ACTION: {"tool": "get_section", "args": {"act_id": 1, "section": "7"}}',
            "ANSWER: প্রথম [1]। দ্বিতীয় [2]।",
        )
        ans = self.agent(llm).run("দুইটি ধারা")
        self.assertEqual(len(ans.hits), 2)
        self.assertEqual(ans.invalid_citations, [])

    def test_repeated_action_stops_the_loop(self):
        same = 'ACTION: {"tool": "search", "args": {"query": "হত্যা"}}'
        llm = ScriptedLLM(same, same, same, "ANSWER: কিছু [1]।")
        ans = self.agent(llm, max_steps=4).run("হত্যা?")
        self.assertEqual(ans.checks["stop_reason"], "repeated_action")
        self.assertTrue(ans.text)                   # still answers from what it had

    def test_step_cap_forces_a_final_answer(self):
        llm = ScriptedLLM(
            'ACTION: {"tool": "search", "args": {"query": "হত্যা"}}',
            'ACTION: {"tool": "search", "args": {"query": "শাস্তি"}}',
            "ANSWER: শেষ উত্তর [1]।",
        )
        ans = self.agent(llm, max_steps=2).run("হত্যার শাস্তি?")
        self.assertEqual(ans.checks["stop_reason"], "max_steps")
        self.assertIn("শেষ উত্তর", ans.text)
        self.assertGreaterEqual(ans.llm_calls, 3)   # 2 steps + the forced answer

    def test_two_malformed_replies_stop_the_loop(self):
        llm = ScriptedLLM("I will now think about it.", "Still thinking.", "ANSWER: hmm")
        ans = self.agent(llm, max_steps=5).run("প্রশ্ন")
        self.assertEqual(ans.checks["stop_reason"], "malformed_twice")
        self.assertTrue(ans.refused)                # nothing retrieved -> refuses

    def test_seed_gives_real_act_ids_and_list_acts_is_not_a_stall(self):
        """A wrong act_id guess plus an act lookup used to end the run with nothing."""
        llm = ScriptedLLM(
            'ACTION: {"tool": "get_section", "args": {"act_id": 999, "section": "302"}}',
            'ACTION: {"tool": "list_acts", "args": {"query": "দণ্ডবিধি"}}',
            "ANSWER: হত্যার শাস্তি মৃত্যুদণ্ড [1]।",
        )
        ans = self.agent(llm, seed=True).run("হত্যার শাস্তি কী?")
        self.assertEqual(ans.checks["stop_reason"], "answered")
        self.assertEqual(ans.checks["trace"][0]["type"], "seed")
        self.assertTrue(ans.hits)
        self.assertFalse(ans.refused)

    def test_stalling_tools_stop_the_loop(self):
        llm = ScriptedLLM(
            'ACTION: {"tool": "get_section", "args": {"act_id": 1, "section": "999"}}',
            'ACTION: {"tool": "get_section", "args": {"act_id": 1, "section": "998"}}',
            'ACTION: {"tool": "get_section", "args": {"act_id": 1, "section": "997"}}',
            "ANSWER: NOT_FOUND: nothing found",
        )
        ans = self.agent(llm, max_steps=5).run("প্রশ্ন")
        self.assertEqual(ans.checks["stop_reason"], "no_new_evidence")

    def test_guardrails_apply_to_the_agent_answer(self):
        llm = ScriptedLLM(
            'ACTION: {"tool": "search", "args": {"query": "হত্যার শাস্তি", "k": 1}}',
            'ANSWER: আইন বলে “এই বাক্যটি কোথাও নাই” [1]।',
            "ANSWER: হত্যার শাস্তি মৃত্যুদণ্ড [1]।",
        )
        ans = self.agent(llm).run("হত্যার শাস্তি কী?")
        self.assertTrue(ans.repaired)
        self.assertEqual(ans.failures, [])          # the repair fixed the fabricated quote

    def test_refusal_is_preserved(self):
        llm = ScriptedLLM(
            'ACTION: {"tool": "search", "args": {"query": "vat"}}',
            "ANSWER: NOT_FOUND: no VAT provision in these acts",
        )
        ans = self.agent(llm).run("What is the VAT rate?")
        self.assertTrue(ans.refused)
        self.assertFalse(ans.repaired)

    def test_immediate_answer_uses_no_tools(self):
        ans = self.agent(ScriptedLLM("ANSWER: NOT_FOUND: nothing to look up")).run("?")
        self.assertEqual(ans.checks["steps"], 0)
        self.assertEqual(ans.llm_calls, 1)


if __name__ == "__main__":
    unittest.main()
