import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from app.config import Settings
from app.llm import OpenAIJsonAgent


class FakeCompletions:
    def __init__(self, content: str = '{"status":"ready"}') -> None:
        self.arguments: dict[str, Any] = {}
        self.content = content

    async def create(self, **kwargs: Any) -> Any:
        self.arguments = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


class FakeClient:
    def __init__(self, captured: dict[str, Any], **kwargs: Any) -> None:
        captured.update(kwargs)
        self.chat = SimpleNamespace(completions=FakeCompletions())


@pytest.mark.parametrize("model", ["deepseek.v3.2", "moonshotai.kimi-k2.5"])
def test_bedrock_models_use_mantle_endpoint_and_bedrock_api_key(
    monkeypatch, model: str
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        "app.llm.AsyncOpenAI", lambda **kwargs: FakeClient(captured, **kwargs)
    )

    agent = OpenAIJsonAgent(
        Settings(
            OPENAI_API_KEY="openai-key",
            BEDROCK_API_KEY="bedrock-key",
            BEDROCK_REGION="ap-south-1",
        ),
        model=model,
    )
    result = asyncio.run(agent.complete_json("stage_1", "Return JSON."))

    assert captured == {
        "api_key": "bedrock-key",
        "base_url": "https://bedrock-mantle.ap-south-1.api.aws/v1",
    }
    assert result == {"status": "ready"}
    assert agent._client.chat.completions.arguments["model"] == model
    assert "response_format" not in agent._client.chat.completions.arguments
    bedrock_message = agent._client.chat.completions.arguments["messages"][0]
    assert bedrock_message["role"] == "user"
    assert "MANDATORY OUTPUT CONTRACT" in bedrock_message["content"]


@pytest.mark.parametrize("model", ["deepseek.v3.2", "moonshotai.kimi-k2.5"])
def test_bedrock_models_combine_stage_context_into_user_message(
    monkeypatch, model: str
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        "app.llm.AsyncOpenAI", lambda **kwargs: FakeClient(captured, **kwargs)
    )

    agent = OpenAIJsonAgent(
        Settings(BEDROCK_API_KEY="bedrock-key", BEDROCK_REGION="ap-south-1"),
        model=model,
    )
    asyncio.run(agent.complete_json("stage_2_1", "Resolve values.", '{"city_name":["Pune"]}'))

    messages = agent._client.chat.completions.arguments["messages"]
    assert len(messages) == 1
    assert "INPUT CONTEXT:" in messages[0]["content"]
    assert '{"city_name":["Pune"]}' in messages[0]["content"]


def test_bedrock_kimi_normalizes_wrapped_json_response(monkeypatch) -> None:
    class WrappedResponseClient(FakeClient):
        def __init__(self, captured: dict[str, Any], **kwargs: Any) -> None:
            super().__init__(captured, **kwargs)
            self.chat = SimpleNamespace(
                completions=FakeCompletions(
                    "Completed stage output:\n```json\n{\"status\":\"ready\"}\n```"
                )
            )

    monkeypatch.setattr(
        "app.llm.AsyncOpenAI", lambda **kwargs: WrappedResponseClient({}, **kwargs)
    )

    agent = OpenAIJsonAgent(
        Settings(BEDROCK_API_KEY="bedrock-key", BEDROCK_REGION="ap-south-1"),
        model="moonshotai.kimi-k2.5",
    )

    assert asyncio.run(agent.complete_json("stage_1", "Return JSON.")) == {"status": "ready"}


def test_openai_model_keeps_json_mode_and_openai_api_key(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        "app.llm.AsyncOpenAI", lambda **kwargs: FakeClient(captured, **kwargs)
    )

    agent = OpenAIJsonAgent(Settings(OPENAI_API_KEY="openai-key"), model="gpt-4o-mini")
    asyncio.run(agent.complete_json("stage_1", "Return JSON."))

    assert captured == {"api_key": "openai-key"}
    assert agent._client.chat.completions.arguments["response_format"] == {
        "type": "json_object"
    }


@pytest.mark.parametrize("model", ["deepseek.v3.2", "moonshotai.kimi-k2.5"])
def test_bedrock_models_require_bedrock_api_key(model: str) -> None:
    with pytest.raises(ValueError, match="BEDROCK_API_KEY"):
        OpenAIJsonAgent(
            Settings(OPENAI_API_KEY="openai-key", BEDROCK_API_KEY=None),
            model=model,
        )


@pytest.mark.parametrize(
    "content",
    [
        '```json\n{"status":"ready"}\n```',
        'Here is the JSON output:\n{"status":"ready"}',
        '<think>Checked the requested fields.</think>\n{"status":"ready"}',
    ],
)
def test_json_parser_accepts_provider_wrapped_object(content: str) -> None:
    assert OpenAIJsonAgent._parse_json_object(content, "stage_1") == {"status": "ready"}


def test_json_parser_rejects_response_without_json_object() -> None:
    with pytest.raises(ValueError, match="stage_1 returned invalid JSON"):
        OpenAIJsonAgent._parse_json_object("I cannot produce structured output.", "stage_1")
