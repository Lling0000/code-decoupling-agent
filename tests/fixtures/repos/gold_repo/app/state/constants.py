__all__ = ["PROMPTS"]
PROMPTS = {"welcome": "hello"}


def get_prompt() -> str:
    return PROMPTS["welcome"]
