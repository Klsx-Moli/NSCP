"""Explicit bounded file IO for the context workbench and CLI."""
from __future__ import annotations

import json
from pathlib import Path

MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_MESSAGES = 4096


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("Non-finite JSON number")


def load_messages(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("Input exceeds 4 MiB workbench limit")
    data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs,
                      parse_constant=_invalid_constant)
    if isinstance(data, dict):
        data = data.get("messages")
    if (not isinstance(data, list) or len(data) > MAX_MESSAGES
            or any(not isinstance(row, dict) or not isinstance(row.get("role"), str) for row in data)):
        raise ValueError("Expected a bounded message list")
    return data


def export_plan(path, plan):
    """Explicit exclusive output creation; never replace an existing file."""
    if not plan.report.get("verification") or plan.report["verification"].get("status") != "structurally_verified":
        raise ValueError("Plan must be structurally verified")
    if not plan.report.get("fits_metered_budget"):
        raise ValueError("Plan exceeds estimated budget")
    data = json.dumps({"messages": plan.messages, "report": plan.report},
                      ensure_ascii=False, allow_nan=False, indent=2)
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(data + "\n")
