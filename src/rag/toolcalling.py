"""Native tool-calling adapter.

`agent.py` drives the loop through a text protocol (THINK / ACTION / ANSWER) so
it runs on any model, including local ones with no function-calling support.
That is the portable path; this is the production path.

Providers expose the same idea with different envelopes: a JSON schema per tool,
an assistant message containing tool_use blocks, a tool_result message back.
This module turns the ToolBox's own SPECS into those schemas and normalises the
two request/response shapes, so switching the agent to native tool calling is a
change of driver, not a rewrite of the agent.

It is written and unit-tested against recorded shapes; it has not been run
against a live API from this machine. That is stated plainly rather than
implied, and it is the first thing to verify when you have a key.
"""
from __future__ import annotations

import json
from typing import Any

JSON_TYPES = {"int": "integer", "float": "number", "str": "string", "bool": "boolean"}


def _schema_for(spec: dict) -> dict:
    properties, required = {}, []
    for name, description in spec["args"].items():
        kind = next((JSON_TYPES[k] for k in JSON_TYPES if description.startswith(k)), "string")
        properties[name] = {"type": kind, "description": description}
        if "required" in description:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


def anthropic_tools(specs: dict) -> list[dict]:
    return [{"name": name, "description": spec["use"], "input_schema": _schema_for(spec)}
            for name, spec in specs.items()]


def openai_tools(specs: dict) -> list[dict]:
    return [{"type": "function",
             "function": {"name": name, "description": spec["use"],
                          "parameters": _schema_for(spec)}}
            for name, spec in specs.items()]


def parse_tool_calls(response: Any, provider: str) -> list[dict]:
    """Normalise a provider response to [{"id", "tool", "args"}]."""
    calls: list[dict] = []
    if provider == "anthropic":
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "tool_use":
                calls.append({"id": block.id, "tool": block.name, "args": dict(block.input or {})})
    elif provider == "openai":
        choice = response.choices[0].message
        for call in getattr(choice, "tool_calls", None) or []:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append({"id": call.id, "tool": call.function.name, "args": args})
    else:
        raise ValueError(f"unknown provider '{provider}'")
    return calls


def tool_result_message(call_id: str, output: str, provider: str) -> dict:
    """The message that carries a tool's output back to the model."""
    if provider == "anthropic":
        return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call_id,
                                             "content": output}]}
    if provider == "openai":
        return {"role": "tool", "tool_call_id": call_id, "content": output}
    raise ValueError(f"unknown provider '{provider}'")


def text_of(response: Any, provider: str) -> str:
    if provider == "anthropic":
        return "".join(b.text for b in getattr(response, "content", [])
                       if getattr(b, "type", None) == "text")
    if provider == "openai":
        return response.choices[0].message.content or ""
    raise ValueError(f"unknown provider '{provider}'")
