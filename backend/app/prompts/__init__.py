from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).parent


@lru_cache
def load_prompt(name: str) -> str:
    """app/prompts/<name>.md 를 읽어 온다. 프롬프트를 코드와 분리해 두기 위한 도우미."""
    return (_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
