Two kinds of fixture live here.

* `*.html` in this folder are **synthetic** pages modelled on the structure of
  bdlaws.minlaw.gov.bd (title in h3, act number in h4, date in [ ], chapter
  headings as plain text, section links to /act-{id}/section-{sid}.html, plus a
  nav bar and footer). They exercise the structure-agnostic fallback parser.
* `real/` holds pages saved **verbatim** from the live site (Penal Code, Evidence
  Act, Insurance Act 2010, Women and Children Repression Prevention Act 2000,
  and the repealed Environment Court Act 2000). `tests/test_real_pages.py` runs
  the parser against them; these are the tests that matter.
