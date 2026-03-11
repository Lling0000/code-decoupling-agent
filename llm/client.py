from __future__ import annotations

import json
import urllib.error
import urllib.request

from llm.env import env_flag, env_value, env_value_with_aliases

DEFAULT_TIMEOUT_SECONDS = 45


class BailianChatClient:
    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def chat_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_payload: dict[str, object],
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> dict[str, object]:
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False, indent=2),
                },
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        payload = self._post("/chat/completions", body)
        content = _extract_message_content(payload)
        return {
            "raw_text": content,
            "json": _extract_json_object(content),
            "response_model": payload.get("model", model),
            "id": payload.get("id"),
        }

    def probe_model(self, *, model: str) -> dict[str, object]:
        body = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Reply with a short confirmation for a connectivity check.",
                },
                {
                    "role": "user",
                    "content": "Respond with OK.",
                },
            ],
            "temperature": 0,
            "max_tokens": 32,
            "stream": False,
        }
        payload = self._post("/chat/completions", body)
        content = _extract_message_content(payload).strip()
        return {
            "response_model": payload.get("model", model),
            "id": payload.get("id"),
            "content_preview": content[:160],
        }

    def _post(self, path: str, body: dict[str, object]) -> dict[str, object]:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


def live_agent_runtime_enabled() -> bool:
    return env_flag("ENABLE_LIVE_AGENTS", default=True)


def build_bailian_client() -> BailianChatClient | None:
    api_key = env_value("DASHSCOPE_API_KEY")
    base_url, _ = env_value_with_aliases(
        "DASHSCOPE_BASE_URL",
        ["BAILIAN_BASE_URL"],
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    if not api_key or not live_agent_runtime_enabled():
        return None
    return BailianChatClient(base_url=base_url, api_key=api_key)


def provider_request_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        body = exc.read().decode("utf-8", errors="ignore")
        return f"HTTP {exc.code}: {body[:500]}"
    return repr(exc)


def _extract_message_content(payload: dict[str, object]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        return "\n".join(text_parts)
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def _extract_json_object(text: str) -> dict[str, object]:
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty LLM response")

    direct = _try_parse_json(stripped)
    if direct is not None:
        return direct

    fence_start = stripped.find("```json")
    if fence_start != -1:
        fence_end = stripped.find("```", fence_start + 7)
        if fence_end != -1:
            fenced = stripped[fence_start + 7 : fence_end].strip()
            parsed = _try_parse_json(fenced)
            if parsed is not None:
                return parsed

    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
        candidate = stripped[first_brace : last_brace + 1]
        parsed = _try_parse_json(candidate)
        if parsed is not None:
            return parsed

    raise ValueError("Could not parse JSON object from LLM response")


def _try_parse_json(text: str) -> dict[str, object] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
