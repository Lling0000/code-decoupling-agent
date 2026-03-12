from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from common.log import get_logger
from llm.env import env_flag, env_value, env_value_with_aliases

log = get_logger("decoupling.llm.client")

DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.5


class BailianChatClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

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
        payload = self._post_with_retry("/chat/completions", body, context=f"chat_json({model})")
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
        payload = self._post_with_retry("/chat/completions", body, context=f"probe({model})")
        content = _extract_message_content(payload).strip()
        return {
            "response_model": payload.get("model", model),
            "id": payload.get("id"),
            "content_preview": content[:160],
        }

    def _post_with_retry(self, path: str, body: dict[str, object], *, context: str) -> dict[str, object]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = self._post(path, body)
                if attempt > 1:
                    log.info("LLM %s succeeded on attempt %d", context, attempt)
                return result
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    wait = RETRY_BACKOFF_SECONDS * attempt
                    log.warning("LLM %s attempt %d failed: %s — retrying in %.1fs", context, attempt, exc, wait)
                    time.sleep(wait)
        log.error("LLM %s failed after %d attempts", context, self.max_retries)
        raise last_error  # type: ignore[misc]

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
