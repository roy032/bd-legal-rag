"""Documentation: relative links and images in the Markdown files point at files that exist."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# [text](target) and ![alt](target), plus <img src="target">.
MD_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMG_SRC = re.compile(r"<img[^>]*\bsrc=\"([^\"]+)\"")
FENCE = re.compile(r"^```.*?^```", re.S | re.M)


def markdown_files():
    skip = {".git", ".venv", "node_modules"}
    for path in ROOT.rglob("*.md"):
        parts = set(path.relative_to(ROOT).parts)
        if parts & skip or any(p.endswith(".egg-info") for p in parts):
            continue
        yield path


def local_targets(text):
    text = FENCE.sub("", text)              # code blocks hold commands, not links
    for target in MD_LINK.findall(text) + IMG_SRC.findall(text):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
            continue                        # URLs, mailto:, in-page anchors
        if "<" in target:
            continue                        # placeholders such as <you>/bdrag-index
        yield target.split("#", 1)[0]


class TestDocLinks(unittest.TestCase):
    def test_relative_links_resolve(self):
        broken = []
        for md in markdown_files():
            for target in local_targets(md.read_text(encoding="utf-8")):
                if target and not (md.parent / target).exists():
                    broken.append(f"{md.relative_to(ROOT)} -> {target}")
        self.assertEqual(broken, [], "broken links:\n" + "\n".join(broken))

    def test_readme_screenshots_are_committed(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        shots = [t for t in local_targets(readme) if t.endswith(".png")]
        self.assertTrue(shots)
        for shot in shots:
            self.assertTrue((ROOT / shot).is_file(), shot)


if __name__ == "__main__":
    unittest.main()
