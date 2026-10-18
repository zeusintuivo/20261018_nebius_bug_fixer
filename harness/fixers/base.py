"""Fixer contract. Every engine (lookup, Nebius Nemotron, Gemini, future LLMs,
multi-agent factories) obeys the same tiny interface."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

HARNESS = Path(__file__).resolve().parent.parent
REPO = HARNESS.parent / "sample_repo"


@dataclass
class BugReport:
    id: str
    title: str
    file: str
    symptom: str


Patch = dict[str, str]  # {relative_path: full_new_contents}


class Fixer(Protocol):
    name: str

    def ready(self) -> bool: ...
    def note(self) -> str: ...
    def get_patch(self, bug: BugReport) -> Optional[Patch]: ...


def read_repo_file(rel: str) -> str:
    p = REPO / rel
    return p.read_text() if p.exists() else ""
