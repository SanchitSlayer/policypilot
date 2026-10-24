"""Deterministic offline stand-in for a tool-calling model, so the contract review runs end to
end without API keys. It does not judge compliance: every clause becomes needs_review with the
closest policy passage attached. Four steps: list clauses, search all, record all, finish."""

import json
import re

from app.llm.base import ChatMessage, ToolCall

_CONTRACT_ID_RE = re.compile(r"contract_id: ([0-9a-fA-F-]{36})")


def _tool_results(messages: list[ChatMessage], name: str) -> dict[str, dict]:
    """tool_call_id -> parsed JSON result, for all results of the given tool."""
    results = {}
    for message in messages:
        if message.role == "tool" and message.name == name:
            try:
                results[message.tool_call_id or ""] = json.loads(message.content)
            except json.JSONDecodeError:
                continue
    return results


def fake_agent_step(messages: list[ChatMessage]) -> tuple[str, list[ToolCall]]:
    listed = _tool_results(messages, "list_contract_clauses")
    if not listed:
        first_user = next((m.content for m in messages if m.role == "user"), "")
        match = _CONTRACT_ID_RE.search(first_user)
        contract_id = match.group(1) if match else ""
        call = ToolCall(
            id="fake_list", name="list_contract_clauses", arguments={"contract_id": contract_id}
        )
        return "Reading the contract.", [call]

    clauses = next(iter(listed.values())).get("clauses", [])
    searches = _tool_results(messages, "search_policies")
    if not searches:
        calls = [
            ToolCall(
                id=f"fake_search_{c['id']}",
                name="search_policies",
                arguments={"query": f"{c['title']}: {c['text'][:200]}", "top_k": 2},
            )
            for c in clauses
        ]
        return "Searching the policies for each clause.", calls

    if not _tool_results(messages, "record_finding"):
        calls = []
        for clause in clauses:
            results = searches.get(f"fake_search_{clause['id']}", {}).get("results", [])
            calls.append(
                ToolCall(
                    id=f"fake_record_{clause['id']}",
                    name="record_finding",
                    arguments={
                        "clause_id": clause["id"],
                        "status": "needs_review",
                        "reason": "Offline demo provider: the closest policy passage is attached "
                        "for manual review. Choose a real model for an actual assessment.",
                        "policy_citations": [r["source_id"] for r in results[:1]],
                    },
                )
            )
        return "Recording findings.", calls

    summary = (
        f"Offline demo review of {len(clauses)} clauses. Each clause is linked to its closest "
        "policy passage and marked for manual review; run the review with OpenAI, Claude or "
        "Gemini for a real compliance assessment."
    )
    return "", [ToolCall(id="fake_finish", name="finish_review", arguments={"summary": summary})]
