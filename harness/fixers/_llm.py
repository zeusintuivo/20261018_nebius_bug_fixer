"""Shared prompt + response parsing for LLM-backed fixers.

The LLM is instructed to return STRICT JSON: {"files": {"path": "contents"}}.
Anything else = no patch. The confidence layer around us then decides whether
to ship. We do NOT try to be clever here — garbage in → NO_PATCH → escalate.
"""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Optional

from .base import BugReport, Patch, REPO


SYSTEM_PROMPT = """You are a surgical bug-fix engine for a Python repository.
Do NOT emit chain-of-thought, reasoning, or any text before the JSON. Your \
entire reply must be a single JSON object and nothing else.

RULES — enforced by downstream interlocks; violating them means your patch is \
rejected and the bug is escalated to a human:
  1. Reply with STRICT JSON only. No prose, no markdown, no fenced code block, \
     no preamble.
  2. Shape: {"files": {"<relative/path.py>": "<FULL new file contents>"}}
     Every file you return REPLACES the existing one. Include the complete \
     file, not a diff. Use \\n for newlines inside the string.
  3. Change as few files as possible. Keep edits small and localized.
  4. Never edit anything under 'protected/'. Never add imports of subprocess, \
     socket, ctypes. Never introduce secrets or credentials in literals.
  5. If you cannot produce a confidently correct small fix, reply with \
     {"files": {}}. Escalation is respected — guessing is not.
"""


def build_user_prompt(bug: BugReport) -> str:
    """Give the model the bug + the file it most likely needs."""
    target = REPO / bug.file
    src = target.read_text() if target.exists() else ""
    tree = sorted(str(p.relative_to(REPO)) for p in REPO.rglob("*.py"))
    return (
        f"BUG ID: {bug.id}\n"
        f"TITLE: {bug.title}\n"
        f"SYMPTOM: {bug.symptom}\n"
        f"PRIMARY FILE: {bug.file}\n\n"
        f"REPO FILES:\n" + "\n".join(f"  - {t}" for t in tree) + "\n\n"
        f"--- CURRENT CONTENTS OF {bug.file} ---\n{src}\n--- END ---\n\n"
        f"Return JSON per the system rules."
    )


def _try_json(s: str):
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def _scan_for_json_object(text: str) -> Optional[dict]:
    """Walk the text and return the LAST well-formed {...} that has a 'files'
    key. Reasoning models often emit thinking first and the final JSON last,
    sometimes truncated mid-answer. Scanning balanced braces is more robust
    than a greedy regex."""
    best: Optional[dict] = None
    for start in (i for i, c in enumerate(text) if c == "{"):
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start:i + 1]
                        obj = _try_json(candidate)
                        if isinstance(obj, dict) and "files" in obj:
                            best = obj
                        break
    return best


def parse_patch(raw: str) -> Optional[Patch]:
    """Best-effort JSON extraction. Returns None on anything suspicious."""
    if not raw:
        return None
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    obj = _try_json(stripped) or _scan_for_json_object(stripped)
    if not isinstance(obj, dict):
        return None
    files = obj.get("files")
    if not isinstance(files, dict) or not files:
        return None
    out: Patch = {}
    for k, v in files.items():
        if not isinstance(k, str) or not isinstance(v, str):
            return None
        if ".." in k or k.startswith("/"):
            return None  # path traversal — refuse
        out[k] = v
    return out
