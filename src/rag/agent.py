"""Agentic retrieval: the model decides what to look up, and when it has enough.

Phase 2-5 retrieve once and answer. That fails on questions that need a second
lookup: "ধারা ৩০২ এর শাস্তি কী এবং ৩০৪ক এর সাথে পার্থক্য কী?" needs two sections;
"as defined in section 2" needs a follow-up the first search never saw.

The loop, deliberately boring:

    THINK/ACTION -> tool -> evidence -> THINK/ACTION -> ... -> ANSWER
                                                   ^ bounded by max_steps

It is written against a plain (system, prompt) -> str callable rather than a
vendor tool-calling API, so it runs on Claude, GPT or a local model unchanged.
A production version would use native tool calling; the control flow, the
budget and the stopping rules are the same either way — and those are what make
an agent shippable, not the API.

Safety rails, each one because agents fail this way:
  * hard step cap and an LLM-call budget
  * repeated identical action -> stop and answer with what it has
  * two steps in a row with no new evidence -> stop
  * malformed output -> one format reminder, then stop
  * the final answer goes through the same Phase 5 guardrails as everything else
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .answer import REFUSAL_MARK, Answer, check_citations
from .guardrails import GuardConfig, repair_instruction, run_checks
from .tools import EvidenceBook, SectionLookup, ToolBox

SYSTEM = """You are a legal research agent working with the laws of Bangladesh.

You answer ONLY from excerpts you have retrieved with the tools. You never use outside
knowledge, and you never guess a section number.

Each turn, reply in EXACTLY one of these two forms and nothing else:

THINK: <one line on what is missing>
ACTION: {{"tool": "<name>", "args": {{...}}}}

You may ask for several independent lookups at once — they run in parallel and
cost one step, so prefer this over asking for them one at a time:

THINK: <one line>
ACTION: [{{"tool": "get_section", "args": {{...}}}}, {{"tool": "search", "args": {{...}}}}]

or, when the excerpts you already have answer the question:

ANSWER: <the answer, with the excerpt number in square brackets after every sentence
that states something, e.g. [2]>

Tools:
{tools}

Rules:
- One action per turn. Do not invent tools or arguments.
- Search again with different wording if the first search misses; do not repeat the same
  search twice.
- If an excerpt says a term is defined elsewhere, use follow_refs on that excerpt.
- Quote the words of a provision exactly as they appear, or paraphrase without quotation marks.
- Answer in the same language as the question.
- If, after searching, the corpus does not answer the question, reply:
  ANSWER: NOT_FOUND: <what is missing>
- You have at most {max_steps} actions. Spend them; do not stall."""

ACTION_RE = re.compile(r"ACTION:\s*([\[{].*)", re.S)   # one object or a list of them
ANSWER_RE = re.compile(r"ANSWER:\s*(.*)", re.S)


@dataclass
class AgentConfig:
    max_steps: int = 5
    per_call_k: int = 5
    max_evidence: int = 12          # excerpts carried into the final answer prompt
    max_parallel: int = 3           # tool calls run together in one step
    guard: GuardConfig = field(default_factory=GuardConfig)
    verbose: bool = False


def _parse_action(text: str) -> tuple[str | None, dict]:
    """The first tool call after ACTION: (compatibility wrapper)."""
    calls = _parse_actions(text)
    return (calls[0]["tool"], calls[0]["args"]) if calls else (None, {})


def _parse_actions(text: str) -> list[dict]:
    """Every tool call after ACTION:. Accepts one object or a list of them."""
    m = ACTION_RE.search(text or "")
    if not m:
        return []
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(m.group(1).strip())
    except json.JSONDecodeError:
        return []
    items = obj if isinstance(obj, list) else [obj]
    calls = []
    for item in items:
        if isinstance(item, dict) and item.get("tool"):
            calls.append({"tool": item["tool"], "args": item.get("args") or {}})
    return calls


class LegalAgent:
    def __init__(self, pipeline, records: list[dict], llm, config: AgentConfig | None = None):
        self.pipeline = pipeline
        self.lookup = SectionLookup(records)
        self.llm = llm
        self.cfg = config or AgentConfig()

    def run(self, question: str) -> Answer:
        cfg = self.cfg
        t0 = time.perf_counter()
        book = EvidenceBook()
        tools = ToolBox(self.pipeline, self.lookup, book, per_call_k=cfg.per_call_k)
        system = SYSTEM.format(tools=tools.describe(), max_steps=cfg.max_steps)

        trace: list[dict] = []
        transcript: list[str] = []
        seen_actions: set[str] = set()
        stalled = 0
        calls = 0
        final: str | None = None
        stop_reason = "max_steps"

        for step in range(1, cfg.max_steps + 1):
            prompt = (f"Question: {question}\n\n"
                      f"Excerpts you have so far:\n{book.render()}\n\n"
                      + ("Your work so far:\n" + "\n".join(transcript) + "\n\n" if transcript else "")
                      + f"Step {step} of {cfg.max_steps}. Reply with THINK+ACTION or ANSWER.")
            reply = (self.llm(system, prompt) or "").strip()
            calls += 1

            answer_m = ANSWER_RE.search(reply)
            if answer_m and "ACTION:" not in reply.split("ANSWER:")[0][-200:]:
                final = answer_m.group(1).strip()
                stop_reason = "answered"
                trace.append({"step": step, "type": "answer"})
                break

            actions = _parse_actions(reply)[: cfg.max_parallel]
            if not actions:
                trace.append({"step": step, "type": "malformed", "reply": reply[:200]})
                transcript.append("(your last reply had no valid ACTION or ANSWER)")
                if any(t["type"] == "malformed" for t in trace[:-1]):
                    stop_reason = "malformed_twice"     # it is not going to recover
                    break
                continue

            signature = json.dumps(actions, sort_keys=True, ensure_ascii=False)
            if signature in seen_actions:
                trace.append({"step": step, "type": "repeat", "calls": actions})
                stop_reason = "repeated_action"
                break
            seen_actions.add(signature)

            before = len(book)
            if len(actions) == 1:
                results = [tools.run(actions[0]["tool"], actions[0]["args"])]
            else:
                # Independent lookups: run them together. The EvidenceBook is the
                # only shared state and it is append-only, so ordering is stable
                # as long as results are collected in submission order.
                with ThreadPoolExecutor(max_workers=cfg.max_parallel) as pool:
                    results = list(pool.map(lambda c: tools.run(c["tool"], c["args"]), actions))
            gained = len(book) - before
            stalled = stalled + 1 if gained == 0 else 0
            trace.append({"step": step, "type": "tool", "calls": actions,
                          "tool": actions[0]["tool"], "args": actions[0]["args"],
                          "parallel": len(actions), "new_excerpts": gained})
            for call, result in zip(actions, results, strict=False):
                transcript.append(
                    f"ACTION {call['tool']}({json.dumps(call['args'], ensure_ascii=False)}) "
                    f"-> {result[:600]}")
            transcript.append(f"({gained} new excerpt(s) this step)")
            if cfg.verbose:
                print(f"  step {step}: {[c['tool'] for c in actions]} -> +{gained}")
            if stalled >= 2:
                stop_reason = "no_new_evidence"
                break

        hits = book.hits[: cfg.max_evidence]
        if final is None:
            # Out of steps (or stopped early): make one final attempt to answer
            # from whatever was gathered, rather than returning nothing.
            if not hits:
                return Answer(question, f"{REFUSAL_MARK}: no excerpts were retrieved.", [],
                              refused=True, latency_s=time.perf_counter() - t0,
                              llm_calls=calls, checks={"trace": trace, "stop_reason": stop_reason})
            final = (self.llm(system, f"Question: {question}\n\nExcerpts:\n{book.render()}\n\n"
                                      f"You are out of actions. Answer now from these excerpts "
                                      f"only, citing [n], or reply ANSWER: NOT_FOUND: <what is "
                                      f"missing>.") or "").strip()
            calls += 1
            match = ANSWER_RE.search(final)
            final = match.group(1).strip() if match else final

        refused = final.startswith(REFUSAL_MARK)
        checks = {} if refused else run_checks(question, final, hits, cfg.guard)
        repaired = False
        if not refused and checks["failures"] and cfg.guard.repair:
            retry = (self.llm(system, f"Question: {question}\n\nExcerpts:\n"
                                      f"{book.render(list(range(1, len(hits) + 1)))}\n\n"
                                      f"--- your previous answer ---\n{final}\n\n"
                                      f"{repair_instruction(checks)}") or "").strip()
            calls += 1
            match = ANSWER_RE.search(retry)
            retry = match.group(1).strip() if match else retry
            repaired = True
            retry_refused = retry.startswith(REFUSAL_MARK)
            retry_checks = {} if retry_refused else run_checks(question, retry, hits, cfg.guard)
            if retry_refused or len(retry_checks["failures"]) < len(checks["failures"]):
                final, checks, refused = retry, retry_checks, retry_refused

        cited, invalid = check_citations(final, len(hits))
        return Answer(
            question=question, text=final, hits=hits, cited=cited, invalid_citations=invalid,
            refused=refused, latency_s=time.perf_counter() - t0, repaired=repaired,
            llm_calls=calls,
            checks={**checks, "trace": trace, "stop_reason": stop_reason,
                    "steps": len([t for t in trace if t["type"] == "tool"]),
                    "tool_calls": tools.calls, "evidence": len(book)},
        )
