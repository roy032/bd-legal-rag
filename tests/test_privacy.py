"""The "your question never leaves this computer" claim is computed, not written:
service/privacy.py decides it from the settings, and the page, /about and
`bdrag doctor` only repeat what it found."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from bdrag_tools.start import OUTSIDE_SETTINGS, private_env  # noqa: E402
from rag.doctor import OK, WARN, check_privacy  # noqa: E402
from service.privacy import is_loopback, model_is_local, report  # noqa: E402

try:
    from starlette.testclient import TestClient

    from service.app import ServiceConfig, create_app
    from test_service import fake_components
    HAVE_STARLETTE = True
except ImportError:                       # pragma: no cover
    HAVE_STARLETTE = False


class TestPrivacyReport(unittest.TestCase):
    def test_loopback_hosts(self):
        for url in ("http://127.0.0.1:11434", "localhost:11434", "http://[::1]:8080/v1",
                    "http://0.0.0.0:11434", "127.0.0.2"):
            self.assertTrue(is_loopback(url), url)
        for url in ("http://192.168.1.5:11434", "https://api.groq.com/openai/v1", "gpu-box:11434", ""):
            self.assertFalse(is_loopback(url), url)

    def test_local_ollama_is_private(self):
        r = report(["ollama:gemma4:e4b"], env={})
        self.assertEqual(r, {"private": True, "outbound": []})

    def test_ollama_on_another_machine_is_not_local(self):
        env = {"OLLAMA_HOST": "http://192.168.1.20:11434"}
        self.assertFalse(model_is_local("ollama", env))
        r = report(["ollama:gemma4:e4b"], env=env)
        self.assertFalse(r["private"])
        self.assertEqual(r["outbound"][0]["where"], "192.168.1.20")

    def test_compat_is_judged_by_its_url_not_its_name(self):
        self.assertTrue(model_is_local("compat", {}))
        self.assertFalse(model_is_local("compat", {"RAG_LLM_BASE_URL": "https://llm.example.org/v1"}))

    def test_hosted_providers_carry_the_question(self):
        for spec, host in (("groq:llama", "api.groq.com"), ("gemini:x", "generativelanguage.googleapis.com"),
                           ("hf:qwen", "router.huggingface.co"), ("openai:gpt", "api.openai.com"),
                           ("anthropic:x", "api.anthropic.com")):
            r = report(["ollama:gemma4:e4b", spec], env={})
            self.assertFalse(r["private"], spec)
            self.assertEqual([o["where"] for o in r["outbound"]], [host])

    def test_remote_redis_holds_questions_tracing_does_not(self):
        r = report(["ollama:g"], env={"REDIS_URL": "redis://cache.example.org:6379/0"})
        self.assertFalse(r["private"])
        r = report(["ollama:g"], env={"REDIS_URL": "redis://127.0.0.1:6379/0"})
        self.assertTrue(r["private"])
        r = report(["ollama:g"], verify_live=True,
                   env={"BDRAG_OTEL_ENDPOINT": "https://tempo.example.org/v1/traces"})
        self.assertTrue(r["private"])                     # timings and section pages only
        self.assertEqual(len(r["outbound"]), 2)

    def test_echo_calls_nothing(self):
        self.assertEqual(report(["echo:"], env={})["outbound"], [])


class TestDoctorPrivacy(unittest.TestCase):
    def test_local_setup_passes(self):
        c = check_privacy({"RAG_LLM": "ollama", "RAG_MODEL": "gemma4:e4b"})
        self.assertEqual(c.status, OK)
        self.assertIn("stay on this machine", c.detail)

    def test_hosted_model_warns_and_names_the_host(self):
        c = check_privacy({"RAG_LLM": "groq", "GROQ_API_KEY": "k"})
        self.assertEqual(c.status, WARN)
        self.assertIn("api.groq.com", c.detail)


class TestStartIsPrivate(unittest.TestCase):
    def test_start_drops_every_outside_setting(self):
        env = {"RAG_LLM": "groq", "GROQ_API_KEY": "k", "OLLAMA_HOST": "http://10.0.0.5:11434",
               "BDRAG_MODELS": "groq:x", "RAG_LLM_BASE_URL": "https://x.example.org/v1",
               "REDIS_URL": "redis://cache.example.org", "BDRAG_OTEL_ENDPOINT": "https://t.example.org",
               "BDRAG_VERIFY_LIVE": "true", "PATH": "/usr/bin"}
        out = private_env(env, "gemma4:e4b", offline=True)
        self.assertFalse(set(OUTSIDE_SETTINGS) & set(out))
        self.assertEqual((out["RAG_LLM"], out["RAG_MODEL"]), ("ollama", "gemma4:e4b"))
        self.assertEqual(out["HF_HUB_OFFLINE"], "1")
        self.assertEqual(out["PATH"], "/usr/bin")
        self.assertEqual(check_privacy(out).status, OK)
        self.assertNotIn("HF_HUB_OFFLINE", private_env({}, "m", offline=False))


@unittest.skipUnless(HAVE_STARLETTE, "starlette not installed")
class TestPrivacyOnThePage(unittest.TestCase):
    def client(self, **kw):
        pipeline, llm, stream = fake_components()
        return TestClient(create_app(ServiceConfig(rate_per_min=6000, burst=100, **kw),
                                     pipeline=pipeline, llm=llm, stream_llm=stream))

    def test_health_reports_a_local_setup_as_private(self):
        with mock.patch.dict("os.environ", {}, clear=False) as env:
            for k in ("OLLAMA_HOST", "REDIS_URL", "BDRAG_OTEL_ENDPOINT", "RAG_LLM_BASE_URL"):
                env.pop(k, None)
            h = self.client(models=["ollama:gemma4:e4b"]).get("/health").json()
        self.assertTrue(h["private"])
        self.assertEqual(h["outbound"], [])
        self.assertFalse(h["same_machine"])           # the test client is not 127.0.0.1

    def test_health_names_a_hosted_model(self):
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "k"}):
            h = self.client(models=["ollama:gemma4:e4b", "groq:llama-3.3-70b-versatile"]).get("/health").json()
        self.assertFalse(h["private"])
        self.assertEqual(h["outbound"][0]["where"], "api.groq.com")
        self.assertNotIn("k", [v for o in h["outbound"] for v in o.values()])

    def test_remote_compat_server_is_flagged_in_the_picker(self):
        with mock.patch.dict("os.environ", {"RAG_LLM_BASE_URL": "https://llm.example.org/v1"}):
            models = self.client(models=["ollama:gemma4:e4b", "compat:qwen"]).get("/models").json()["models"]
        self.assertEqual([m["local"] for m in models], [True, False])

    def test_about_page_is_served_bangla_first(self):
        c = self.client()
        r = c.get("/about")
        self.assertEqual(r.status_code, 200)
        self.assertLess(r.text.index("বাংলায় আইনের প্রশ্ন"), r.text.index("Bangladeshi law, in Bangla"))
        self.assertIn('id="private"', r.text)
        self.assertIn("Allow: /about", c.get("/robots.txt").text)
        home = c.get("/").text
        self.assertIn('href="/about"', home)
        self.assertIn('<html lang="bn">', home)

    def test_the_page_loads_nothing_from_other_sites(self):
        c = self.client()
        for path in ("/", "/about", "/privacy"):
            r = c.get(path)
            self.assertIn("connect-src 'self'", r.headers["content-security-policy"])
            for tag in ("<script src=\"http", "<link rel=\"stylesheet\" href=\"http", "@import"):
                self.assertNotIn(tag, r.text, path)


if __name__ == "__main__":
    unittest.main()
