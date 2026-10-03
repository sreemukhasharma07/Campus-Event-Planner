"""Minimal async client for the xAI (Grok) chat completions API."""
import asyncio

import httpx

from .config import settings


class GrokError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.message = message
        self.status = status


async def chat(messages: list[dict]) -> str:
    if not settings.xai_api_key:
        raise GrokError("XAI_API_KEY is not set on the server. Add it to the .env file and restart.", 503)
    payload = {"model": settings.model, "messages": messages}
    if settings.temperature is not None:
        payload["temperature"] = settings.temperature
    headers = {"Authorization": f"Bearer {settings.xai_api_key}", "Content-Type": "application/json"}
    last: GrokError | None = None
    async with httpx.AsyncClient(timeout=settings.timeout) as client:
        for attempt in range(2):
            try:
                r = await client.post(f"{settings.xai_base_url}/chat/completions", json=payload, headers=headers)
            except httpx.TimeoutException:
                last = GrokError("Grok did not answer in time.", 504)
                continue
            except httpx.HTTPError as exc:
                last = GrokError(f"Could not reach the Grok API ({exc.__class__.__name__}).", 502)
                continue
            if r.status_code in (429, 500, 502, 503) and attempt == 0:
                await asyncio.sleep(1.5)
                last = GrokError(f"Grok API returned {r.status_code}.", 502)
                continue
            if r.status_code in (401, 403):
                raise GrokError("The Grok API rejected the API key. Check XAI_API_KEY.", 502)
            if r.status_code >= 400:
                raise GrokError(f"Grok API error {r.status_code}: {r.text[:300]}", 502)
            try:
                return r.json()["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, ValueError):
                raise GrokError("Unexpected response format from the Grok API.", 502)
    raise last or GrokError("Grok request failed.")
