import asyncio
import json
from typing import Any

import promt

from app.workflow import SqlAgentWorkflow


class FakeAgent:
    def __init__(self, outputs: list[dict[str, Any]]) -> None:
        self.outputs = outputs
        self.calls: list[str] = []
        self.prompts: dict[str, str] = {}
        self.input_contexts: dict[str, str | None] = {}

    async def complete_json(
        self, stage_name: str, prompt: str, input_context: str | None = None
    ) -> dict[str, Any]:
        self.calls.append(stage_name)
        self.prompts[stage_name] = prompt
        self.input_contexts[stage_name] = input_context
        return self.outputs.pop(0)


def test_workflow_runs_all_sql_generation_and_review_stages() -> None:
    outputs = [
        {
            "OUTPUT_JSON_SCHEMA": {},
            "MAPPED_JSON_SCHEMA": {"needs_clarification": False},
        },
        {"MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"algorithm_status": "ready", "final_algorithm_structure": {}},
        {"algorithm_status": "ready", "final_algorithm_structure": {}},
        {"sql_build_status": "ready", "combined_sql": {"sql_query": "SELECT COUNT(*) FROM transactions"}},
        {"sql_review_status": "approved"},
    ]
    agent = FakeAgent(outputs)

    result = asyncio.run(
        SqlAgentWorkflow(agent).run(
            "Total residential sale transactions in Pune for 2024",
            semantic_context={"distinct_database_values": {"city_name": ["Pune"]}},
        )
    )

    assert result.pipeline_status == "completed"
    assert agent.calls == [
        "stage_1",
        "stage_1_5",
        "stage_1_6",
        "stage_2",
        "stage_2_1",
        "stage_3",
        "stage_3_1",
    ]
    assert result.sql_review_output == {"sql_review_status": "approved"}
    assert agent.prompts["stage_2_1"] == promt.stage_2_1
    stage_2_1_input = json.loads(agent.input_contexts["stage_2_1"] or "{}")
    assert stage_2_1_input["Distinct database values"] == {"city_name": ["Pune"]}


def test_workflow_stops_when_stage_one_requires_clarification() -> None:
    agent = FakeAgent(
        [
            {
                "needs_clarification": True,
                "clarification_question": "Please provide: time_period",
            }
        ]
    )

    result = asyncio.run(SqlAgentWorkflow(agent).run("Show residential sales in Pune"))

    assert result.pipeline_status == "needs_clarification"
    assert result.stopped_at_stage == "stage_1"
    assert result.clarification_question == "Please provide: time_period"
    assert agent.calls == ["stage_1"]


def test_workflow_stops_at_stage_two_when_algorithm_needs_clarification() -> None:
    outputs = [
        {
            "OUTPUT_JSON_SCHEMA": {},
            "MAPPED_JSON_SCHEMA": {"needs_clarification": False},
        },
        {"MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {
            "algorithm_status": "needs_clarification",
            "calculation_logic_validation": [
                {"clarification_required": "Do you mean total or average agreement value?"}
            ],
            "final_algorithm_structure": {},
        },
    ]
    agent = FakeAgent(outputs)

    result = asyncio.run(
        SqlAgentWorkflow(agent).run("Show value for residential sale in Pune for 2024")
    )

    assert result.pipeline_status == "needs_clarification"
    assert result.stopped_at_stage == "stage_2"
    assert result.clarification_question == "Do you mean total or average agreement value?"
    assert agent.calls == ["stage_1", "stage_1_5", "stage_1_6", "stage_2"]


def test_workflow_stops_at_stage_two_one_when_semantic_resolution_is_unclear() -> None:
    outputs = [
        {
            "OUTPUT_JSON_SCHEMA": {},
            "MAPPED_JSON_SCHEMA": {"needs_clarification": False},
        },
        {"MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"algorithm_status": "ready", "final_algorithm_structure": {}},
        {
            "algorithm_status": "needs_clarification",
            "calculation_logic_validation": [
                {"clarification_required": "Confirm the database-valid property_type value."}
            ],
            "final_algorithm_structure": {},
        },
    ]
    agent = FakeAgent(outputs)

    result = asyncio.run(
        SqlAgentWorkflow(agent).run(
            "Show total value for residential sale in Pune in 2024",
            semantic_context={"distinct_database_values": {"property_type": ["Residential"]}},
        )
    )

    assert result.pipeline_status == "needs_clarification"
    assert result.stopped_at_stage == "stage_2_1"
    assert result.clarification_question == "Confirm the database-valid property_type value."
    assert agent.calls == ["stage_1", "stage_1_5", "stage_1_6", "stage_2", "stage_2_1"]
