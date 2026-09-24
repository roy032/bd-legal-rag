"""Follow-up questions.

"ধারা ৩০২ কী বলে?" then "আর শাস্তি?" — the second question retrieves nothing on
its own, because the subject only exists in the first one. The fix is not to
stuff the history into the retrieval query (that drags in words that pull
retrieval off-topic); it is to rewrite the follow-up into a standalone question
first, and retrieve with that.

    history + "আর শাস্তি?"  ->  "ধারা ৩০২ অনুযায়ী শাস্তি কী?"  ->  retrieval

Keep the rewrite for retrieval only. The answer prompt still sees the real
question, so the model answers what was asked.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .answer import Answer, answer_question
from .guardrails import GuardConfig
from .llm import LLM

CONDENSE_PROMPT = """Rewrite the follow-up question as a standalone question that can be
understood with no conversation history. Keep the original language. Resolve pronouns and
references ("it", "that section", "সেটা", "ওই ধারা") using the conversation. Change nothing
else, and add nothing that was not asked.

Conversation:
{history}

Follow-up: {question}

Standalone question:"""

# Short questions that lean on the previous turn.
FOLLOW_UP_HINT = re.compile(
    r"^(and|what about|why|how|then|আর|তাহলে|সেটা|ওটা|এটা|ওই|সেই|কেন|কীভাবে|কিভাবে)\b",
    re.IGNORECASE)


def looks_like_follow_up(question: str) -> bool:
    q = question.strip()
    return bool(FOLLOW_UP_HINT.match(q)) or len(q.split()) <= 4


def condense(history: list[tuple[str, str]], question: str, llm, max_turns: int = 3) -> str:
    """Rewrite a follow-up into a standalone question. Falls back to the original."""
    if not history or not llm or not looks_like_follow_up(question):
        return question
    recent = history[-max_turns:]
    text = "\n".join(f"Q: {q}\nA: {a[:300]}" for q, a in recent)
    try:
        out = llm("You rewrite follow-up questions into standalone ones. Output only the question.",
                  CONDENSE_PROMPT.format(history=text, question=question))
    except Exception:
        return question
    out = (out or "").strip().splitlines()[0].strip() if out else ""
    # A rewrite that drops everything or explodes in length is worse than the original.
    return out if 3 <= len(out) <= 400 else question


@dataclass
class ChatSession:
    retriever: object
    llm: LLM
    k: int = 5
    guard: GuardConfig = field(default_factory=GuardConfig)
    sandwich: bool = True
    history: list[tuple[str, str]] = field(default_factory=list)
    search_kw: dict = field(default_factory=dict)

    def ask(self, question: str) -> Answer:
        standalone = condense(self.history, question, self.llm)
        ans = answer_question(standalone, self.retriever, self.llm, k=self.k,
                              sandwich=self.sandwich, guard=self.guard, **self.search_kw)
        ans.question = question            # report what the user actually asked
        if standalone != question:
            ans.checks = {**ans.checks, "rewritten_query": standalone}
        self.history.append((question, ans.text))
        return ans

    def reset(self) -> None:
        self.history.clear()
