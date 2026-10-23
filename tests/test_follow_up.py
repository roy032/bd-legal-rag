"""Follow-up questions through the service: the server rewrites "and the fine?" with the
turns it stored itself, retrieves with the rewrite, and reports the visitor's own words."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from rag.chat import condense  # noqa: E402

try:
    from starlette.testclient import TestClient

    from service.app import ServiceConfig, create_app
    from test_service import fake_components
    HAVE_STARLETTE = True
except ImportError:                       # pragma: no cover
    HAVE_STARLETTE = False

REWRITE = "দণ্ডবিধির ধারা ৩০২ অনুযায়ী হত্যার শাস্তি কী?"


class TestCondense(unittest.TestCase):
    def test_explicit_follow_up_is_rewritten_even_when_long(self):
        long_q = "what happens if the employer also refuses to pay the overtime for last month"
        history = [("unpaid wages", "Labour Act s.123")]
        self.assertEqual(condense(history, long_q, lambda s, p: "rewritten question"), long_q)
        self.assertEqual(condense(history, long_q, lambda s, p: "rewritten question", always=True),
                         "rewritten question")

    def test_label_and_quotes_are_stripped(self):
        out = condense([("ক", "খ")], "আর শাস্তি?", lambda s, p: f'Standalone question: "{REWRITE}"')
        self.assertEqual(out, REWRITE)


@unittest.skipUnless(HAVE_STARLETTE, "starlette not installed")
class TestFollowUpEndpoints(unittest.TestCase):
    def client(self):
        pipeline, _, stream = fake_components()
        self.prompts: list[str] = []

        def llm(system, prompt):
            self.prompts.append(prompt)
            if "Standalone question:" in prompt:
                return REWRITE
            return "হত্যার শাস্তি মৃত্যুদণ্ড [1]।"

        app = create_app(ServiceConfig(rate_per_min=6000, burst=100), pipeline=pipeline,
                         llm=llm, stream_llm=stream)
        return TestClient(app)

    def test_follow_up_is_rewritten_from_the_stored_turn(self):
        c = self.client()
        first = c.post("/ask", json={"question": "ধারা ৩০২ কী বলে?"}).json()
        r = c.post("/ask", json={"question": "আর শাস্তি?", "follow_up_of": first["id"]}).json()
        self.assertEqual(r["question"], "আর শাস্তি?")            # the visitor's own words
        self.assertEqual(r["searched_for"], REWRITE)
        self.assertEqual(r["parent"], first["id"])
        condense_prompt = next(p for p in self.prompts if "Standalone question:" in p)
        self.assertIn("ধারা ৩০২ কী বলে?", condense_prompt)       # history came from the store
        # The follow-up's own link keeps the thread, so a third turn sees both.
        stored = c.get(f"/a/{r['id']}?format=json").json()
        self.assertEqual(stored["parent"], first["id"])

    def test_unknown_parent_is_a_plain_question(self):
        c = self.client()
        r = c.post("/ask", json={"question": "আর শাস্তি?", "follow_up_of": "nope"}).json()
        self.assertNotIn("searched_for", r)
        self.assertNotIn("parent", r)
        self.assertFalse(any("Standalone question:" in p for p in self.prompts))

    def test_stream_carries_the_rewrite(self):
        c = self.client()
        first = c.post("/ask", json={"question": "ধারা ৩০২ কী বলে?"}).json()
        body = c.post("/ask/stream", json={"question": "আর শাস্তি?",
                                            "follow_up_of": first["id"]}).text
        final = [json.loads(line[6:]) for line in body.splitlines()
                 if line.startswith("data: ") and '"searched_for"' in line]
        self.assertEqual(final[-1]["searched_for"], REWRITE)
        self.assertEqual(final[-1]["question"], "আর শাস্তি?")

    def test_cached_answer_does_not_leak_another_thread(self):
        c = self.client()
        first = c.post("/ask", json={"question": "ধারা ৩০২ কী বলে?"}).json()
        c.post("/ask", json={"question": "আর শাস্তি?", "follow_up_of": first["id"]})
        # The same standalone question asked directly hits the cache, without the thread.
        direct = c.post("/ask", json={"question": REWRITE}).json()
        self.assertTrue(direct["cached"])
        self.assertEqual(direct["question"], REWRITE)
        self.assertNotIn("parent", direct)
        self.assertNotIn("searched_for", direct)


if __name__ == "__main__":
    unittest.main()
