import pytest
from fastapi.testclient import TestClient

from app.api import get_workflow
from app.config import Settings
from app.main import app
from app.models import GenerateSqlRequest, PipelineResponse


class FakeWorkflow:
    async def run(
        self,
        user_query: str,
        include_intermediate_stages: bool,
        semantic_context: dict,
    ) -> PipelineResponse:
        return PipelineResponse(
            query=user_query,
            pipeline_status="needs_clarification",
            message="Test response.",
            stopped_at_stage="stage_1",
        )


def _client() -> TestClient:
    app.dependency_overrides[get_workflow] = lambda: FakeWorkflow()
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_generate_sql_accepts_standard_json_object_body() -> None:
    response = _client().post(
        "/api/v1/sql/generate",
        json={"query": "Show total value for residential sale in Pune in 2024"},
    )

    assert response.status_code == 200
    assert response.json()["query"] == "Show total value for residential sale in Pune in 2024"


def test_generate_sql_accepts_json_object_encoded_as_string() -> None:
    response = _client().post(
        "/api/v1/sql/generate",
        json='{"query":"Show total value for residential sale in Pune in 2024"}',
    )

    assert response.status_code == 200
    assert response.json()["query"] == "Show total value for residential sale in Pune in 2024"


@pytest.mark.parametrize(
    "model", ["gpt-4o-mini", "gpt-5.1", "deepseek.v3.2", "moonshotai.kimi-k2.5"]
)
def test_generate_sql_accepts_supported_selected_model(model: str) -> None:
    response = _client().post(
        "/api/v1/sql/generate",
        json={
            "query": "Show total value for residential sale in Pune in 2024",
            "model": model,
        },
    )

    assert response.status_code == 200


def test_generate_sql_rejects_unsupported_selected_model() -> None:
    response = _client().post(
        "/api/v1/sql/generate",
        json={
            "query": "Show total value for residential sale in Pune in 2024",
            "model": "gpt-4",
        },
    )

    assert response.status_code == 422


def test_get_workflow_passes_selected_model_to_agent(monkeypatch) -> None:
    selected: dict[str, str | None] = {}

    class StubAgent:
        def __init__(self, settings: Settings, model: str | None = None) -> None:
            selected["model"] = model

    monkeypatch.setattr("app.api.OpenAIJsonAgent", StubAgent)

    get_workflow(
        GenerateSqlRequest(
            query="Show total value for residential sale in Pune in 2024",
            model="gpt-5.1",
        ),
        Settings(OPENAI_API_KEY="test-key"),
    )

    assert selected["model"] == "gpt-5.1"


def test_frontend_page_and_assets_are_served() -> None:
    client = TestClient(app)

    page = client.get("/")
    javascript = client.get("/static/app.js")

    assert page.status_code == 200
    assert "Real Estate SQL Agent" in page.text
    assert 'value="gpt-4o-mini"' in page.text
    assert 'value="gpt-5.1"' in page.text
    assert 'value="deepseek.v3.2"' in page.text
    assert 'value="moonshotai.kimi-k2.5"' in page.text
    assert javascript.status_code == 200
    assert "/api/v1/sql/generate" in javascript.text
    assert "model: modelSelect.value" in javascript.text
    assert "clarificationAnswerPanel" in page.text
    assert "Submit Answer & Rerun" in javascript.text
    assert "Clarification answer:" in javascript.text
    assert "downloadReportButton" in page.text
    assert "downloadWordReport(data, modelLabel)" in javascript.text
    assert "application/msword" in javascript.text
    assert "ReAct Iteration" in javascript.text
    assert "iteration-group" in javascript.text
    assert "Stage 3.2 - SQL Probe" in javascript.text
