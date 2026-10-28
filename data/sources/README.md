# Sources beyond the Acts

`manifest.jsonl` lists the rules, regulations, SROs, orders and court judgments that
`bdrag sources` fetches and ingests. One JSON object per line.

| field | required | meaning |
|---|---|---|
| `id` | yes | stable slug, lowercase (`consumer-rules-2021`); never reuse one |
| `kind` | yes | `rule`, `regulation`, `sro`, `order` or `judgment` |
| `title` | yes | the official title, in the document's language |
| `url` | yes | the government's own copy; only `*.gov.bd` hosts are accepted |
| `parent_act` | rules/SROs | the act it is made under, as titled on bdlaws |
| `citation` | no | `এস.আর.ও. নং ১২৩-আইন/২০২১`, shown with the title |
| `date` | no | `YYYY-MM-DD`; for a judgment, the date it was delivered |
| `division`, `case_number`, `parties` | judgments | read from the PDF when left out |

Where to find them, free and official:

- **Supreme Court judgments**: `bdrag sources discover` reads the latest lists on
  supremecourt.gov.bd (High Court and Appellate Division). Older judgments are on the
  same site's search form.
- **Rules and SROs**: the Bangladesh Gazette at dpp.gov.bd (download the gazette PDF),
  the Legislative and Parliamentary Affairs Division (legislativediv.gov.bd), and the
  ministry or directorate that administers the act (its `*.gov.bd` portal, for example
  the Directorate of National Consumer Rights Protection for the consumer rules, or
  nbr.gov.bd for tax SROs).

After editing: `bdrag sources check`, then `fetch`, `ingest` and `bdrag index --bm25`.
