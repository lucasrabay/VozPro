from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

PROMPT_PATH = os.environ.get(
    "BIU_PROMPT_PATH", str(Path(__file__).resolve().parent.parent / "prompts" / "biu_system.md")
)


@lru_cache(maxsize=1)
def system_prompt() -> str:
    path = Path(PROMPT_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Biu system prompt not found at {path}")
    return path.read_text(encoding="utf-8")


def reload_prompt() -> None:
    system_prompt.cache_clear()
