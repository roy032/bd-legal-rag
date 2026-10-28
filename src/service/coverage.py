"""The public "what this covers, and what it can't answer yet" page (/coverage).

Three parts, each from its own source so each can be checked on its own:

  * what is indexed: counted from the index records (acts, rules, SROs,
    judgments) with the date the index was built;
  * known gaps: data/coverage/known_gaps.json, written by hand. The kinds of law
    that are not in the collection at all, said plainly in both languages;
  * questions we could not answer: data/coverage/public_gaps.json from
    `bdrag gaps --public`, which keeps only questions several different visitors
    asked. Absent until the operator publishes one.

Rendered on the server as plain HTML (no script), so it reads the same with
JavaScript off and is cheap to crawl.
"""
from __future__ import annotations

import html
import json
import time
from collections import defaultdict
from pathlib import Path

from ingest.sources import KIND_LABELS

ORDER = ("act", "rule", "regulation", "sro", "order", "judgment")


def corpus_counts(records: list[dict] | None) -> dict:
    """{doc_type: {"documents": n, "chunks": n}} from the index records."""
    docs: dict[str, set] = defaultdict(set)
    chunks: dict[str, int] = defaultdict(int)
    for r in records or []:
        m = r.get("metadata") or {}
        kind = m.get("doc_type") or "act"
        if m.get("act_id") is not None:
            docs[kind].add(m["act_id"])
        chunks[kind] += 1
    return {k: {"documents": len(docs[k]), "chunks": chunks[k]}
            for k in sorted(chunks, key=lambda k: ORDER.index(k) if k in ORDER else 99)}


def load_json(path: str | Path) -> dict | list | None:
    p = Path(path) if path else None
    if not p or not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def coverage_data(records: list[dict] | None, built_at: float | None,
                  known_path: str, public_path: str) -> dict:
    public = load_json(public_path)
    return {
        "index_built_at": time.strftime("%Y-%m-%d", time.gmtime(built_at)) if built_at else None,
        "corpus": corpus_counts(records),
        "known_gaps": (load_json(known_path) or {}).get("gaps", []),
        "unanswered": public if isinstance(public, dict) else None,
    }


def _e(text) -> str:
    # Text and double-quoted attribute values only; apostrophes stay readable.
    return html.escape(str(text if text is not None else ""), quote=False).replace('"', "&quot;")


_STYLE = """
  .legal { max-width: 760px; margin: 0 auto; padding: 32px 16px 64px; line-height: 1.65; }
  .legal h1 { font-size: clamp(24px, 3vw, 32px); margin: 0 0 6px; }
  .legal h2 { font-size: 20px; margin: 32px 0 8px; }
  .legal .updated { color: var(--muted); font-size: 14px; margin: 0 0 20px; }
  .legal ul { padding-left: 1.3em; }
  .legal li { margin: 6px 0; }
  .legal nav { display: flex; gap: 8px 18px; flex-wrap: wrap; margin: 0 0 8px; font-size: 15px; }
  .legal table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
  .legal th, .legal td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); }
  .legal td.n { text-align: right; }
  .legal .muted { color: var(--muted); font-size: 14px; }
  .legal .q { margin: 10px 0; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; }
  .legal hr { border: 0; border-top: 1px solid var(--line); margin: 40px 0; }
"""

TEXT = {
    "en": {
        "title": "What we can and can't answer",
        "lead": "This service only answers from the documents below. When a question needs "
                "something that is not here, it says so instead of guessing. This page lists "
                "what is in the collection, what is known to be missing, and questions people "
                "asked that it could not answer yet.",
        "indexed": "What is in the collection", "kind": "Kind", "docs": "Documents",
        "parts": "Searchable parts", "built": "Last updated from the official sources on {d}.",
        "nobuilt": "The collection is loading.",
        "known": "Known gaps",
        "unanswered": "Questions we could not answer yet",
        "none": "No list has been published yet.",
        "asked": "Questions that at least {k} different visitors asked, and the service refused, "
                 "could only answer with general guidance, or answered badly. Updated {d}.",
        "why": {"unanswered": "not answered", "answered badly": "answer rated poor"},
        "help": "Know a free official source for one of these? Open an issue on the project page.",
        "back": "← Bangladesh Law Assistant", "other": "বাংলায় পড়ুন", "privacy": "Privacy and terms",
    },
    "bn": {
        "title": "আমরা কী উত্তর দিতে পারি, কী পারি না",
        "lead": "এই সেবা শুধু নিচের দলিলগুলো থেকে উত্তর দেয়। প্রশ্নের উত্তর এখানে না থাকলে "
                "অনুমান না করে তা জানিয়ে দেয়। এই পাতায় আছে সংগ্রহে কী আছে, কী নেই বলে জানা, "
                "এবং মানুষ যেসব প্রশ্ন করেছে কিন্তু এখনো উত্তর দেওয়া যায়নি।",
        "indexed": "সংগ্রহে যা আছে", "kind": "ধরন", "docs": "দলিল", "parts": "খোঁজার অংশ",
        "built": "সরকারি উৎস থেকে সর্বশেষ হালনাগাদ: {d}।", "nobuilt": "সংগ্রহ লোড হচ্ছে।",
        "known": "জানা ঘাটতি",
        "unanswered": "যেসব প্রশ্নের উত্তর এখনো দিতে পারিনি",
        "none": "এখনো কোনো তালিকা প্রকাশ করা হয়নি।",
        "asked": "অন্তত {k} জন আলাদা ব্যবহারকারী এই প্রশ্নগুলো করেছেন, এবং সেবাটি উত্তর দেয়নি, "
                 "শুধু সাধারণ নির্দেশনা দিয়েছে, বা উত্তর ভালো হয়নি। হালনাগাদ: {d}।",
        "why": {"unanswered": "উত্তর হয়নি", "answered badly": "উত্তর দুর্বল"},
        "help": "এগুলোর কোনোটির বিনামূল্যের সরকারি উৎস জানলে প্রকল্পের পাতায় জানান।",
        "back": "← বাংলাদেশ আইন সহায়ক", "other": "Read in English", "privacy": "গোপনীয়তা ও শর্ত",
    },
}


def _section(data: dict, lang: str) -> str:
    t = TEXT[lang]
    i = 0 if lang == "bn" else 1
    rows = "".join(
        f"<tr><td>{_e(KIND_LABELS.get(k, (k, k))[i])}</td><td class=n>{v['documents']:,}</td>"
        f"<td class=n>{v['chunks']:,}</td></tr>" for k, v in data["corpus"].items())
    built = (t["built"].format(d=_e(data["index_built_at"])) if data["index_built_at"]
             else t["nobuilt"])
    out = [f"<h1>{_e(t['title'])}</h1>", f"<p>{_e(t['lead'])}</p>",
           f"<h2>{_e(t['indexed'])}</h2>"]
    if rows:
        out.append(f"<table><thead><tr><th>{_e(t['kind'])}</th><th>{_e(t['docs'])}</th>"
                   f"<th>{_e(t['parts'])}</th></tr></thead><tbody>{rows}</tbody></table>")
    out.append(f"<p class=muted>{built}</p>")
    if data["known_gaps"]:
        out.append(f"<h2>{_e(t['known'])}</h2><ul>")
        for g in data["known_gaps"]:
            text = g.get(lang) or g.get("en") or ""
            out.append(f"<li>{_e(text)}</li>")
        out.append("</ul>")
    out.append(f"<h2>{_e(t['unanswered'])}</h2>")
    pub = data["unanswered"]
    qs = [q for q in (pub or {}).get("questions", []) if q.get("language") in (lang, "mixed")] \
        or (pub or {}).get("questions", [])
    if not pub or not qs:
        out.append(f"<p>{_e(t['none'])}</p>")
    else:
        out.append(f"<p class=muted>{_e(t['asked'].format(k=pub.get('min_visitors', 3), d=pub.get('generated', '')))}</p>")
        for q in qs:
            why = t["why"].get(q.get("why"), q.get("why", ""))
            out.append(f"<div class=q lang=\"{_e(q.get('language') if q.get('language') in ('bn', 'en') else lang)}\">"
                       f"{_e(q.get('question'))}<div class=muted>{_e(why)}</div></div>")
    out.append(f"<p>{_e(t['help'])} <a href=\"https://github.com/roy032/bd-legal-rag/issues\">"
               "github.com/roy032/bd-legal-rag</a></p>")
    return "\n".join(out)


def render(data: dict) -> str:
    en, bn = TEXT["en"], TEXT["bn"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{_e(en['title'])} · Bangladesh Law Assistant</title>
<meta name="description" content="What the Bangladesh Law Assistant covers, what is missing, and questions it cannot answer yet.">
<meta name="theme-color" content="#0b4f3a">
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/static/app.css">
<style>{_STYLE}</style>
</head>
<body>
<main class="legal">
<nav><a href="/">{_e(en['back'])}</a> <a href="#bn" lang="bn">{_e(en['other'])}</a> <a href="/privacy">{_e(en['privacy'])}</a></nav>
<section id="en">
{_section(data, "en")}
</section>
<hr>
<section id="bn" lang="bn">
<nav><a href="/">{_e(bn['back'])}</a> <a href="#en" lang="en">{_e(bn['other'])}</a> <a href="/privacy">{_e(bn['privacy'])}</a></nav>
{_section(data, "bn")}
</section>
</main>
</body>
</html>
"""
