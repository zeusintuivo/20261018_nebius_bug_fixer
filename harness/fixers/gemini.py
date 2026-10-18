"""Gemini fixer via google-genai SDK.

Reads GEMINI_API_KEY (or GOOGLE_API_KEY). Model defaults to gemini-2.5-flash,
override with GEMINI_MODEL.
"""
from __future__ import annotations
import os
from typing import Optional

from .base import Fixer, BugReport, Patch
from ._llm import SYSTEM_PROMPT, build_user_prompt, parse_patch


DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def _api_key() -> str:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""


class GeminiFixer:
    name = "gemini"

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from google import genai
        except ImportError:
            return None
        key = _api_key()
        if not key:
            return None
        self._client = genai.Client(api_key=key)
        return self._client

    def ready(self) -> bool:
        return bool(_api_key())

    def note(self) -> str:
        if not self.ready():
            return "set GEMINI_API_KEY"
        return f"model={self.model}"

    def get_patch(self, bug: BugReport) -> Optional[Patch]:
        client = self._get_client()
        if client is None:
            return None
        try:
            resp = client.models.generate_content(
                model=self.model,
                contents=[SYSTEM_PROMPT + "\n\n" + build_user_prompt(bug)],
            )
            raw = (resp.text or "")
        except Exception:
            return None
        return parse_patch(raw)
