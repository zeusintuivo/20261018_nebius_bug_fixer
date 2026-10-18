"""Pluggable fixers. The confidence layer treats each one as a black box.

A fixer takes a bug report and returns {relative_path: new_contents} or None.
Nothing else. The interlocks around it don't care which engine produced the diff —
that's the whole point of the dark-factory frame.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

from .base import Fixer, BugReport, Patch
from .offline import OfflineFixer
from .nebius import NebiusFixer
from .gemini import GeminiFixer


_REGISTRY: dict[str, Fixer] = {}


def register(name: str, fixer: Fixer) -> None:
    _REGISTRY[name] = fixer


def available() -> list[dict]:
    """List fixers with readiness so the UI can grey-out unconfigured ones."""
    return [{"name": n, "ready": f.ready(), "note": f.note()} for n, f in _REGISTRY.items()]


def get(name: Optional[str] = None) -> Fixer:
    name = name or os.environ.get("DARKFACTORY_FIXER") or "offline"
    if name not in _REGISTRY:
        raise KeyError(f"unknown fixer: {name}")
    return _REGISTRY[name]


# default roster — order matters, first = default
register("offline",  OfflineFixer())
register("nebius",   NebiusFixer())
register("gemini",   GeminiFixer())
