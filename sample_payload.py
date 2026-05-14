"""
Heuristic sample invocation JSON derived from workflow text (instructions, roles).
Used by the API and UI so callers know the shape agents were prompted to expect.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

# Dotted paths like user.account_age_days, applicant.credit_score
_PATH_RE = re.compile(
    r"\b([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+)\b"
)

# First path segment often false-positive when instructions mention generic words
_SKIP_ROOTS = frozenset(
    {
        "the", "and", "for", "from", "with", "your", "this", "that", "json",
        "each", "all", "see", "use", "one", "two", "any", "not", "may", "can",
        "output", "format", "fields", "list", "object", "string", "array",
        "read", "base", "never", "input", "data", "both", "prior", "agent",
        "low", "medium", "high", "complete", "incomplete",
        # Do not synthesize a "validation" block in samples — callers should not
        # mirror a stale is_valid into the model as if it were ground truth.
        "validation",
    }
)


def _leaf_placeholder(path_parts: List[str]) -> Any:
    leaf = path_parts[-1].lower()
    joined = ".".join(p.lower() for p in path_parts)

    if "email" in leaf:
        return "user@example.com"
    if leaf in ("user_id", "customer_id", "account_id") or leaf.endswith("_id"):
        return "usr_123"
    if leaf == "id" and "user" in joined:
        return "usr_123"
    if leaf == "id":
        return 1001
    if "name" in leaf and "user" not in leaf:
        return "Jane Doe"
    if leaf.endswith("status") or "status" in leaf:
        return "completed"
    if leaf.startswith("is_") or leaf.startswith("has_") or "mismatch" in leaf:
        return False
    if any(
        x in leaf
        for x in (
            "amount",
            "price",
            "income",
            "debt",
            "loan",
            "score",
            "days",
            "age",
            "count",
            "ratio",
            "chargebacks",
            "returns",
        )
    ):
        if "score" in leaf:
            return 720
        if "days" in leaf or "age" in leaf:
            return 45
        if "amount" in leaf or "price" in leaf or "loan" in leaf:
            return 4500
        return 0
    if leaf in ("quantity", "qty"):
        return 1
    return "sample"


def _deep_set(root: Dict[str, Any], path: str) -> None:
    parts = path.split(".")
    if len(parts) < 2:
        return
    root_seg = parts[0].lower()
    if root_seg in _SKIP_ROOTS:
        return
    cur: Any = root
    for _, seg in enumerate(parts[:-1]):
        if seg not in cur or not isinstance(cur[seg], dict):
            cur[seg] = {}
        cur = cur[seg]
    leaf = parts[-1]
    if leaf not in cur:
        cur[leaf] = _leaf_placeholder(parts)


def _collect_text(workflow: Dict[str, Any]) -> str:
    chunks: List[str] = []
    chunks.append(str(workflow.get("description") or ""))
    chunks.append(str(workflow.get("name") or ""))
    schema = workflow.get("schema") or {}
    for agent in schema.get("agents") or []:
        chunks.append(str(agent.get("instructions") or ""))
        chunks.append(str(agent.get("role") or ""))
    wf = schema.get("workflow") or {}
    for node in wf.get("nodes") or []:
        chunks.append(str(node.get("instruction") or ""))
    return "\n".join(chunks)


def _extract_paths(text: str) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for m in _PATH_RE.finditer(text):
        p = m.group(1)
        if p.count(".") < 1:
            continue
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


def build_sample_payload_from_workflow(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a nested dict of plausible example values from dotted field paths
    mentioned in the workflow schema text.
    """
    paths = _extract_paths(_collect_text(workflow))
    if not paths:
        return {
            "_note": (
                "No dotted field paths (like user.account_age_days) were found in "
                "the generated instructions. Send any JSON your workflow describes, "
                "or edit agent instructions to list explicit field names."
            )
        }
    out: Dict[str, Any] = {}
    for p in paths:
        _deep_set(out, p)
    return out
