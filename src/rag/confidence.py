"""A confidence number the user can act on — and a warning about it.

Made of four signals the system already has:
  retrieval strength  how far the top hit is above the rest
  agreement           how many distinct sections were cited
  grounding           entailment support rate, when an entailer is configured
  checks              guardrail failures and whether a repair was needed

This is a heuristic, not a calibrated probability. Before showing it to anyone,
bucket your evaluation answers by predicted confidence and plot the share that
were actually correct: if "high" is right 60% of the time, the number is a lie
and you either recalibrate it or remove it. That plot is a strong README figure.
"""
from __future__ import annotations

from .store import Hit


def confidence(hits: list[Hit], cited: list[int], checks: dict | None = None,
               entailment: dict | None = None) -> dict:
    checks = checks or {}
    if not hits:
        return {"score": 0.0, "label": "none", "why": ["nothing retrieved"]}

    why: list[str] = []
    top = hits[0].score
    rest = [h.score for h in hits[1:]] or [0.0]
    margin = (top - max(rest)) / abs(top) if top else 0.0
    retrieval = min(max(margin * 2.5, 0.0), 1.0)
    if retrieval < 0.2:
        why.append("several excerpts scored about the same")

    distinct = {(hits[n - 1].metadata.get("act_id"), hits[n - 1].metadata.get("section_id"))
                for n in cited if 1 <= n <= len(hits)}
    agreement = min(len(distinct) / 2.0, 1.0) if distinct else 0.0
    if not distinct:
        why.append("the answer cited nothing")

    grounding = float(entailment["support_rate"]) if entailment else 0.75
    if entailment and entailment.get("unsupported"):
        why.append(f"{len(entailment['unsupported'])} claim(s) not entailed by the cited text")

    penalty = 0.25 * len(checks.get("failures", [])) + (0.1 if checks.get("repaired") else 0.0)
    if checks.get("failures"):
        why.append("guardrail checks failed: " + ", ".join(checks["failures"]))

    score = max(0.0, min(1.0, 0.35 * retrieval + 0.25 * agreement + 0.40 * grounding - penalty))
    label = "high" if score >= 0.7 else "medium" if score >= 0.45 else "low"
    if label != "high" and not why:
        why.append("weak support overall")
    return {"score": round(score, 3), "label": label, "why": why,
            "parts": {"retrieval": round(retrieval, 3), "agreement": round(agreement, 3),
                      "grounding": round(grounding, 3), "penalty": round(penalty, 3)}}
