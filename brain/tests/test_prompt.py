from __future__ import annotations

from app import prompt


def test_system_prompt_loads():
    prompt.reload_prompt()
    text = prompt.system_prompt()
    assert len(text) > 500
    for needle in [
        "Biu",
        "user_transcript",
        "dados_pessoais",
        "type: \"curriculo\"" if False else "curriculo",
    ]:
        assert needle in text, f"prompt missing: {needle}"
