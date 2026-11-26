"""Prompt library: built-in prompts plus prompts written in the UI.

A saved prompt never changes: editing saves a new prompt (with `base` naming the one it
was copied from). Results stay tied to the exact text that produced them, and the
prompt text is part of the extractor/verifier run id, so caches never mix prompts.
Custom prompts live in data/prompts/<id>.json.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ..extract.llm_extractor import PROMPT_NOTES, PROMPTS
from ..resolve.llm_verifier import PROMPT_VERSION as VERIFY_DEFAULT
from ..resolve.llm_verifier import SYSTEM_PROMPT as VERIFY_PROMPT

Kind = Literal["extract", "verify"]
MAX_CHARS = 20000


class Prompt(BaseModel):
    id: str
    kind: Kind
    name: str
    note: str = ""
    text: str
    base: str | None = None
    builtin: bool = False
    created_at: str | None = None


BUILTIN: dict[str, Prompt] = {
    **{pid: Prompt(id=pid, kind="extract", name=pid.replace("extract-", "prompt "), note=PROMPT_NOTES.get(pid, ""),
                   text=text, builtin=True, base=None if pid == "extract-v1" else "extract-v1")
       for pid, text in PROMPTS.items()},
    VERIFY_DEFAULT: Prompt(id=VERIFY_DEFAULT, kind="verify", name="verify v1", note="baseline", text=VERIFY_PROMPT,
                           builtin=True),
}
DEFAULT = {"extract": "extract-v1", "verify": VERIFY_DEFAULT}


class PromptStore:
    def __init__(self, data_dir: Path):
        self.dir = data_dir / "prompts"

    def all(self) -> dict[str, Prompt]:
        out = dict(BUILTIN)
        if self.dir.exists():
            for p in sorted(self.dir.glob("*.json")):
                try:
                    prompt = Prompt(**json.loads(p.read_text(encoding="utf-8")))
                except (ValueError, TypeError):
                    continue
                out[prompt.id] = prompt
        return out

    def get(self, prompt_id: str) -> Prompt:
        prompt = self.all().get(prompt_id)
        if prompt is None:
            raise KeyError(prompt_id)
        return prompt

    def create(self, kind: Kind, name: str, text: str, note: str = "", base: str | None = None) -> Prompt:
        name, text = name.strip(), text.strip()
        if not name:
            raise ValueError("give the prompt a name")
        if not text:
            raise ValueError("the prompt text is empty")
        if len(text) > MAX_CHARS:
            raise ValueError(f"the prompt is longer than {MAX_CHARS} characters")
        existing = self.all()
        same = [p for p in existing.values() if p.kind == kind and p.text == text]
        if same:
            raise ValueError(f"this text is identical to '{same[0].name}'")
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "prompt"
        prompt_id, n = f"{kind}-{slug}", 2
        while prompt_id in existing:
            prompt_id, n = f"{kind}-{slug}-{n}", n + 1
        prompt = Prompt(id=prompt_id, kind=kind, name=name, note=note.strip(), text=text, base=base,
                        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{prompt_id}.json").write_text(prompt.model_dump_json(indent=2), encoding="utf-8")
        return prompt

    def delete(self, prompt_id: str) -> None:
        if prompt_id in BUILTIN:
            raise ValueError("built-in prompts cannot be deleted")
        path = self.dir / f"{prompt_id}.json"
        if not re.fullmatch(r"[a-z0-9-]+", prompt_id) or not path.exists():
            raise KeyError(prompt_id)
        path.unlink()
