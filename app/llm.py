import json
from typing import Any, Protocol

from openai import AsyncOpenAI

from app.config import Settings
from app.models import SupportedModel


class JsonAgent(Protocol):
    async def complete_json(
        self, stage_name: str, prompt: str, input_context: str | None = None
    ) -> dict[str, Any]: ...


class OpenAIJsonAgent:
    """Runs one prompt stage and parses its strict JSON response."""

    def __init__(self, settings: Settings, model: SupportedModel | None = None) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required to run the SQL generation pipeline.")
        self._model = model or settings.openai_model
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def complete_json(
        self, stage_name: str, prompt: str, input_context: str | None = None
    ) -> dict[str, Any]:
        messages = [{"role": "system", "content": prompt}]
        if input_context is not None:
            messages.append({"role": "user", "content": input_context})
        completion = await self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=messages,
        )
        content = completion.choices[0].message.content
        if not content:
            raise ValueError(f"{stage_name} returned an empty model response.")
        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{stage_name} returned invalid JSON.") from exc
        if not isinstance(result, dict):
            raise ValueError(f"{stage_name} returned JSON that is not an object.")
        return result
