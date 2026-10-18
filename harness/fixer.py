"""Backward-compat shim.

The real fixers live in fixers/*. This module keeps the pipeline tidy and
provides a single entry point `get_patch(bug_id_or_report, fixer=None)`.
"""
from __future__ import annotations
from typing import Optional, Union

from fixers import get as _get_fixer, available as _available
from fixers.base import BugReport, Patch


def _coerce(b: Union[dict, BugReport]) -> BugReport:
    if isinstance(b, BugReport):
        return b
    return BugReport(
        id=b["id"],
        title=b.get("title", ""),
        file=b.get("file", ""),
        symptom=b.get("symptom", ""),
    )


def get_patch(bug: Union[dict, BugReport, str],
              fixer: Optional[str] = None) -> Optional[Patch]:
    # legacy call site passed just the bug id; wrap minimally
    if isinstance(bug, str):
        bug = BugReport(id=bug, title="", file="", symptom="")
    report = _coerce(bug)
    return _get_fixer(fixer).get_patch(report)


def available() -> list[dict]:
    return _available()
