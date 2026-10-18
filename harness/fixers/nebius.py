"""Nebius Token Factory fixer — Nemotron by default.

Uses the OpenAI-compatible chat.completions endpoint, which Nebius exposes at
https://api.tokenfactory.nebius.com/v1/. Any text2text model id from the Nebius
catalog works. Picks the key from NEMOTRON_LIGHTING_NEBIUS_API_KEY first
(hackathon-provided), then NEBIUS_API_KEY as a generic fallback.
"""
from __future__ import annotations
import os
from typing import Optional

from .base import Fixer, BugReport, Patch
from ._llm import SYSTEM_PROMPT, build_user_prompt, parse_patch


BASE_URL = os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
DEFAULT_MODEL = os.environ.get("NEBIUS_MODEL", "nvidia/Nemotron-3_5-Lightning")


def _api_key() -> str:
    return (
        os.environ.get("NEMOTRON_LIGHTING_NEBIUS_API_KEY")
        or os.environ.get("NEBIUS_API_KEY")
        or ""
    )


class NebiusFixer:
    name = "nebius"

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError:
            return None
        key = _api_key()
        if not key:
            return None
        self._client = OpenAI(base_url=BASE_URL, api_key=key)
        return self._client

    def ready(self) -> bool:
        return bool(_api_key())

    def note(self) -> str:
        if not self.ready():
            return "set NEMOTRON_LIGHTING_NEBIUS_API_KEY or NEBIUS_API_KEY"
        return f"model={self.model}"

    def get_patch(self, bug: BugReport) -> Optional[Patch]:
        client = self._get_client()
        if client is None:
            return None
        self.last_raw = ""
        self.last_error = ""
        kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": build_user_prompt(bug)},
            ],
            temperature=0.1,
            max_tokens=16000,
        )
        try:
            resp = client.chat.completions.create(
                response_format={"type": "json_object"}, **kwargs,
            )
        except Exception as e:
            # not all models accept response_format; retry without it
            try:
                resp = client.chat.completions.create(**kwargs)
            except Exception as e2:
                self.last_error = f"{type(e2).__name__}: {e2}"
                return None
        try:
            raw = resp.choices[0].message.content or ""
        except Exception as e:
            self.last_error = f"no choices: {e}"
            return None
        self.last_raw = raw
        return parse_patch(raw)
