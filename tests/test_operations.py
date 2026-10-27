"""Operations: retention, index age, backups, the gaps report, the probe, alert rules."""
import contextlib
import io
import json
import os
import re
import sqlite3
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from bdrag_tools import backup, gaps, probe  # noqa: E402
from rag.doctor import WARN, check_index_age  # noqa: E402
from rag.pipeline import index_built_at  # noqa: E402
from service.metrics import Metrics  # noqa: E402
from service.retention import Housekeeper, append_jsonl, prune_jsonl  # noqa: E402

try:
    from starlette.testclient import TestClient

    from service.app import ServiceConfig, create_app
    from test_service import fake_components
    HAVE_STARLETTE = True
except ImportError:                       # pragma: no cover
    HAVE_STARLETTE = False

DAY = 86400


class Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestRetention(Tmp):
    def test_old_rows_go_new_rows_and_unreadable_rows_stay(self):
        path = str(self.dir / "q.jsonl")
        now = time.time()
        for age in (200, 120, 10, 1):
            append_jsonl(path, {"ts": now - age * DAY, "question": f"{age} days"})
        with open(path, "a", encoding="utf-8") as f:
            f.write("not json\n")
        self.assertEqual(prune_jsonl(path, 90, now), 2)
        kept = Path(path).read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(x)["question"] for x in kept[:2]], ["10 days", "1 days"])
        self.assertEqual(kept[2], "not json")
        self.assertFalse(Path(path + ".prune").exists())

    def test_nothing_to_do_does_not_rewrite(self):
        path = self.dir / "q.jsonl"
        append_jsonl(str(path), {"ts": time.time(), "question": "today"})
        before = path.stat().st_mtime_ns
        self.assertEqual(prune_jsonl(str(path), 90), 0)
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_off_and_missing_are_no_ops(self):
        self.assertEqual(prune_jsonl(str(self.dir / "absent.jsonl"), 90), 0)
        path = str(self.dir / "q.jsonl")
        append_jsonl(path, {"ts": 0})
        self.assertEqual(prune_jsonl(path, 0), 0)

    def test_housekeeper_counts_and_survives_a_failing_task(self):
        seen = []

        def broken():
            raise OSError("disk")

        keeper = Housekeeper({"a": lambda: 3, "b": broken}, on_result=lambda n, k: seen.append((n, k)))
        with self.assertLogs("service", "ERROR"):
            self.assertEqual(keeper.run_once(), {"a": 3})
            keeper.run_once()
        self.assertEqual(keeper.stats()["deleted"], {"a": 6, "b": 0})
        self.assertEqual(seen, [("a", 3), ("a", 3)])
        with self.assertLogs("service", "ERROR"):
            keeper.start()
            keeper.stop()


class TestIndexAge(Tmp):
    def test_built_at_then_mtime_then_none(self):
        self.assertIsNone(index_built_at(self.dir))
        info = self.dir / "index.json"
        info.write_text(json.dumps({"dim": 4, "built_at": "2026-01-02T03:04:05Z"}))
        self.assertEqual(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(index_built_at(self.dir))),
                         "2026-01-02T03:04:05Z")
        info.write_text(json.dumps({"dim": 4}))          # an index built before the field
        self.assertAlmostEqual(index_built_at(self.dir), info.stat().st_mtime, delta=1)

    def test_saved_index_records_its_build_time(self):
        import numpy as np

        from rag.store import NumpyStore
        store = NumpyStore(dim=2, embedder_name="hashing")
        store.add(np.eye(2, dtype=np.float32), [{"chunk_id": "a", "text": "x", "metadata": {}},
                                                {"chunk_id": "b", "text": "y", "metadata": {}}])
        store.save(self.dir)
        self.assertLess(abs(time.time() - index_built_at(self.dir)), 5)

    def test_doctor_warns_on_an_old_index(self):
        (self.dir / "index.json").write_text(json.dumps({"built_at": "2026-01-01T00:00:00Z"}))
        jan_1 = 1767225600
        self.assertEqual(check_index_age(self.dir, 45, now=jan_1 + 10 * DAY).status, "ok")
        old = check_index_age(self.dir, 45, now=jan_1 + 60 * DAY)
        self.assertEqual(old.status, WARN)
        self.assertIn("60 days ago", old.detail)


class TestBackup(Tmp):
    def make_data(self):
        data = self.dir / "data"
        data.mkdir()
        db = sqlite3.connect(data / "answers.sqlite3")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE answers (id TEXT PRIMARY KEY, created REAL, payload TEXT)")
        db.executemany("INSERT INTO answers VALUES (?, ?, ?)",
                       [(f"a{i}", time.time(), "{}") for i in range(3)])
        db.commit()                  # left open, mid-WAL, as the running service holds it
        self.addCleanup(db.close)
        (data / "queries.jsonl").write_text('{"ts": 1}\n{"ts": 2}\n', encoding="utf-8")
        return data

    def test_backup_verify_restore(self):
        data = self.make_data()
        archive = backup.create(data, self.dir / "backups")
        manifest = backup._read(archive)[0]
        self.assertEqual(manifest["files"]["answers.sqlite3"]["rows"], 3)
        self.assertEqual(manifest["files"]["queries.jsonl"]["rows"], 2)
        self.assertEqual(backup.verify(archive), [])
        target = self.dir / "restored"
        backup.restore(archive, target)
        with contextlib.closing(sqlite3.connect(target / "answers.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM answers").fetchone()[0], 3)
        with self.assertRaises(SystemExit):              # will not overwrite by accident
            backup.restore(archive, target)
        backup.restore(archive, target, force=True)

    def test_tampered_archive_fails_verification(self):
        archive = backup.create(self.make_data(), self.dir / "backups")
        manifest, files = backup._read(archive)
        files["queries.jsonl"] = b'{"ts": 1}\n'
        bad = self.dir / "bad.tar.gz"
        with tarfile.open(bad, "w:gz") as tar:
            for name, blob in [("manifest.json", json.dumps(manifest).encode()), *files.items()]:
                info = tarfile.TarInfo(name)
                info.size = len(blob)
                tar.addfile(info, io.BytesIO(blob))
        self.assertEqual(backup.verify(bad), ["queries.jsonl: checksum mismatch"])
        with self.assertRaises(SystemExit):
            backup.restore(bad, self.dir / "out")

    def test_paths_in_an_archive_are_refused(self):
        evil = self.dir / "evil.tar.gz"
        with tarfile.open(evil, "w:gz") as tar:
            info = tarfile.TarInfo("../escape.txt")
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
        with self.assertRaises(SystemExit):
            backup.verify(evil)

    def test_keeps_the_newest_n(self):
        data = self.make_data()
        out = self.dir / "backups"
        for i in range(4):
            backup.create(data, out, keep=2, now=1_800_000_000 + i * 60)
        self.assertEqual([p.name for p in sorted(out.glob("bdrag-*.tar.gz"))],
                         ["bdrag-20270115T080200Z.tar.gz", "bdrag-20270115T080300Z.tar.gz"])

    def test_cli_exit_status(self):
        from rag.cli import main
        archive = backup.create(self.make_data(), self.dir / "backups")
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as ok:
            main(["backup", "--verify", str(archive)])
        self.assertIn(ok.exception.code, (0, None))
        archive.write_bytes(archive.read_bytes()[:40])
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as bad:
            main(["backup", "--verify", str(archive)])
        self.assertEqual(bad.exception.code, 1)


class TestGaps(unittest.TestCase):
    def test_groups_and_ranks_by_visitors(self):
        t = 1_790_000_000
        queries = [
            {"ts": t, "client": "a", "question": "Can my landlord double the rent?", "refused": True},
            {"ts": t + 1, "client": "b", "question": "can my landlord double the rent", "general": True},
            {"ts": t + 2, "client": "c", "question": "ধারা ৩০২ কী?", "refused": False, "failures": []},
            {"ts": t + 3, "client": "c", "question": "How do I register a drone?", "refused": True},
        ]
        feedback = [{"ts": t + 4, "rating": "down", "question": "How do I register a drone?",
                     "comment": "nothing useful"}]
        report = gaps.analyse(queries, feedback)
        top = report["gaps"]
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0]["visitors"], 2)
        self.assertEqual(top[0]["reasons"], {"refused": 1, "general guidance": 1})
        self.assertEqual(top[1]["reasons"], {"refused": 1, "thumbs down": 1})
        self.assertEqual(report["summary"]["answers"], 4)
        self.assertEqual(report["summary"]["thumbs_down"], 1)
        text = gaps.markdown(report)
        self.assertIn("nothing useful", text)
        self.assertIn("**none**", text)                   # the drone question matches no topic

    def test_since_filters(self):
        rows = [{"ts": 0, "question": "old", "refused": True}]
        self.assertEqual(gaps.analyse(rows, [], since=10)["gaps"], [])


class TestProbe(unittest.TestCase):
    def fake(self, ready="ready", hits=1, built="2026-10-01T00:00:00Z"):
        def get(url, body, timeout):
            path = url.split("localhost", 1)[1]
            if path == "/livez":
                return 200, {"status": "alive"}, 0.01
            if path == "/readyz":
                return (200 if ready == "ready" else 503), {"status": ready, "index_built_at": built}, 0.01
            if path == "/search":
                return 200, {"results": [{"citation": "Penal Code s.302"}] * hits}, 0.2
            return 200, "<!doctype html><html></html>", 0.01
        return get

    def test_healthy(self):
        checks = probe.run("http://localhost", get=self.fake())
        self.assertTrue(all(c["ok"] for c in checks), checks)

    def test_failures_are_named(self):
        checks = probe.run("http://localhost", get=self.fake(ready="loading", hits=0))
        self.assertEqual([c["check"] for c in checks if not c["ok"]], ["ready", "search"])

    def test_stale_index_and_unreachable(self):
        checks = probe.run("http://localhost", max_index_age_days=1, get=self.fake())
        self.assertFalse(next(c for c in checks if c["check"] == "index age")["ok"])

        def down(url, body, timeout):
            raise OSError("connection refused")
        self.assertTrue(all(not c["ok"] for c in probe.run("http://localhost", get=down)))


class TestAlertRules(unittest.TestCase):
    """Every metric an alert names must be one the service exports, or the alert
    silently never fires."""

    def test_rules_reference_exported_metrics(self):
        import yaml
        rules = yaml.safe_load((ROOT / "deploy/monitoring/alerts.yml").read_text(encoding="utf-8"))
        exprs = [r["expr"] for g in rules["groups"] for r in g["rules"]]
        records = {r["record"] for g in rules["groups"] for r in g["rules"] if "record" in r}
        names = {m.group(0) for e in exprs for m in re.finditer(r"\b[a-z_]+(?=\{|\[| ==| >)", e)}
        builtin = {"up", "rate", "sum", "increase", "histogram_quantile", "clamp_min", "vector",
                   "by", "le"}
        exported = set(Metrics.HELP)
        exported |= {f"{n}_bucket" for n in Metrics.HELP if n.endswith("_seconds")}
        unknown = {n for n in names - builtin - records
                   if not n.startswith("bdrag:")} - exported
        self.assertEqual(unknown, set())
        self.assertTrue({"requests_total", "index_age_seconds", "circuit_open"} <= names)


@unittest.skipUnless(HAVE_STARLETTE, "starlette not installed")
class TestServiceRetention(Tmp):
    def test_logs_are_pruned_and_index_age_is_reported(self):
        index = self.dir / "index"
        index.mkdir()
        (index / "index.json").write_text(json.dumps({"built_at": "2026-01-01T00:00:00Z"}))
        queries, fb = str(self.dir / "queries.jsonl"), str(self.dir / "feedback.jsonl")
        append_jsonl(queries, {"ts": time.time() - 400 * DAY, "question": "old"})
        append_jsonl(queries, {"ts": time.time(), "question": "new"})
        pipeline, llm, stream = fake_components()
        cfg = ServiceConfig(index=str(index), analytics_path=queries, feedback_path=fb,
                            rate_per_min=6000, burst=100, log_days=90)
        app = create_app(cfg, pipeline=pipeline, llm=llm, stream_llm=stream, records=[])
        with TestClient(app) as c:                        # lifespan starts the housekeeper
            for _ in range(50):
                if app.state.housekeeper.last_run:
                    break
                time.sleep(0.05)
            self.assertEqual(app.state.housekeeper.deleted["queries"], 1)
            self.assertEqual(c.get("/readyz").json()["index_built_at"], "2026-01-01T00:00:00Z")
            stats = c.get("/stats").json()
            self.assertEqual(stats["retention"]["log_days"], 90)
            self.assertGreater(stats["index_age_days"], 200)
            body = c.get("/metrics").text
            self.assertIn('retention_deleted_total{store="queries"} 1', body)
            self.assertIn("index_age_seconds ", body)
            c.post("/ask", json={"question": "হত্যার শাস্তি কী?"})
        rows = [json.loads(x) for x in Path(queries).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[0]["question"], "new")
        self.assertIn("general", rows[-1])
        self.assertTrue(os.path.exists(queries))


if __name__ == "__main__":
    unittest.main()
