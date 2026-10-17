"""scripts/sync_index.py against a stand-in for huggingface_hub (no network)."""
import runpy
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = str(ROOT / "scripts" / "sync_index.py")


def fake_hub(calls):
    hub = types.ModuleType("huggingface_hub")

    class HfApi:
        def create_repo(self, repo_id, **kw):
            calls.append(("create", repo_id, kw))

        def upload_folder(self, **kw):
            calls.append(("upload", kw))

    def snapshot_download(**kw):
        calls.append(("download", kw))
        return kw["local_dir"]

    hub.HfApi, hub.snapshot_download = HfApi, snapshot_download
    return hub


class TestSyncIndex(unittest.TestCase):
    def run_script(self, *argv):
        calls = []
        with mock.patch.dict(sys.modules, {"huggingface_hub": fake_hub(calls)}), \
             mock.patch.object(sys, "argv", [SCRIPT, *argv]):
            runpy.run_path(SCRIPT, run_name="__main__")
        return calls

    def test_push_uploads_only_index_files_to_a_dataset(self):
        calls = self.run_script("push", "--repo", "me/idx", "--index", str(ROOT / "data/sample/index"),
                                "--private")
        self.assertEqual(calls[0], ("create", "me/idx", {"repo_type": "dataset", "private": True,
                                                          "exist_ok": True}))
        upload = calls[1][1]
        self.assertEqual(upload["repo_type"], "dataset")
        self.assertIn("vectors.npy", upload["allow_patterns"])

    def test_push_refuses_without_an_index(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit):
            self.run_script("push", "--repo", "me/idx", "--index", d)

    def test_pull(self):
        calls = self.run_script("pull", "--repo", "me/idx", "--index", "/tmp/x")
        self.assertEqual(calls[0][1]["repo_id"], "me/idx")
        self.assertEqual(calls[0][1]["local_dir"], "/tmp/x")


if __name__ == "__main__":
    unittest.main()
