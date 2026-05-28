import asyncio
import json
from typing import Any

import promt
import pytest

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


class FakeSqlProbe:
    def __init__(self, outputs: list[dict[str, Any]]) -> None:
        self.outputs = outputs
        self.calls: list[tuple[dict[str, Any], int]] = []

    def execute_approved_sql(
        self, sql_review_output: dict[str, Any], iteration: int
    ) -> dict[str, Any]:
        self.calls.append((sql_review_output, iteration))
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
        {
            "sql_review_status": "approved",
            "metric_relationship": "combined",
            "approved_sql": {"combined_sql": {"sql_query": "SELECT COUNT(*) FROM transactions"}},
        },
        {
            "sql_observe_status": "success",
            "react_decision": {"decision": "stop_success"},
            "send_to_sql_fix": False,
        },
    ]
    agent = FakeAgent(outputs)
    probe = FakeSqlProbe(
        [
            {
                "stage": "Stage 3.2 - SQL Probe",
                "sql_probe_status": "success",
                "execution_results": {
                    "combined_sql": {
                        "applicable": True,
                        "execution_status": "success",
                        "output_availability": "data_available",
                        "row_count": 1,
                    }
                },
            }
        ]
    )

    result = asyncio.run(
        SqlAgentWorkflow(agent, sql_probe=probe).run(
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
        "stage_3_3",
    ]
    assert result.sql_review_output["sql_review_status"] == "approved"
    assert result.sql_probe_output["sql_probe_status"] == "success"
    assert result.sql_observe_output["react_decision"]["decision"] == "stop_success"
    assert len(result.react_iterations or []) == 1
    assert probe.calls[0][1] == 1
    assert agent.prompts["stage_2_1"] == promt.stage_2_1
    stage_2_1_input = json.loads(agent.input_contexts["stage_2_1"] or "{}")
    assert stage_2_1_input["Distinct database values"] == {"city_name": ["Pune"]}


def test_workflow_reacts_to_probe_evidence_and_re_reviews_fixed_sql() -> None:
    outputs = [
        {"OUTPUT_JSON_SCHEMA": {}, "MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"algorithm_status": "ready", "final_algorithm_structure": {}},
        {"algorithm_status": "ready", "final_algorithm_structure": {}},
        {"sql_build_status": "ready", "combined_sql": {"sql_query": "SELECT 1"}},
        {
            "sql_review_status": "approved",
            "metric_relationship": "combined",
            "approved_sql": {"combined_sql": {"sql_query": "SELECT 1"}},
        },
        {
            "sql_observe_status": "needs_fix",
            "send_to_sql_fix": True,
            "react_decision": {"decision": "send_to_sql_fix"},
        },
        {
            "sql_fix_status": "fixed",
            "send_back_to_sql_review": True,
            "fixed_sql_output": {"combined_sql": {"fixed_sql": "SELECT 2"}},
        },
        {
            "sql_review_status": "approved",
            "metric_relationship": "combined",
            "approved_sql": {"combined_sql": {"sql_query": "SELECT 2"}},
        },
        {
            "sql_observe_status": "success",
            "send_to_sql_fix": False,
            "react_decision": {"decision": "stop_success"},
        },
    ]
    probe = FakeSqlProbe(
        [
            {
                "stage": "Stage 3.2 - SQL Probe",
                "sql_probe_status": "failed",
                "needs_correction": True,
                "execution_results": {"combined_sql": {"applicable": True}},
            },
            {
                "stage": "Stage 3.2 - SQL Probe",
                "sql_probe_status": "success",
                "execution_results": {
                    "combined_sql": {
                        "applicable": True,
                        "execution_status": "success",
                        "output_availability": "data_available",
                    }
                },
            },
        ]
    )

    result = asyncio.run(
        SqlAgentWorkflow(FakeAgent(outputs), sql_probe=probe).run(
            "Show residential sale value in Pune in 2024"
        )
    )

    assert result.pipeline_status == "completed"
    assert len(result.react_iterations or []) == 2
    assert [call[1] for call in probe.calls] == [1, 2]
    assert result.sql_fix_output["sql_fix_status"] == "fixed"
    assert "stage_3_1_iteration_2" in (result.stages or {})


def test_workflow_blocks_observe_success_without_probe_data() -> None:
    outputs = [
        {"OUTPUT_JSON_SCHEMA": {}, "MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"algorithm_status": "ready", "final_algorithm_structure": {}},
        {"algorithm_status": "ready", "final_algorithm_structure": {}},
        {"sql_build_status": "ready", "combined_sql": {"sql_query": "SELECT 1"}},
        {"sql_review_status": "approved", "metric_relationship": "combined"},
        {"react_decision": {"decision": "stop_success"}, "send_to_sql_fix": False},
    ]
    probe = FakeSqlProbe(
        [
            {
                "stage": "Stage 3.2 - SQL Probe",
                "sql_probe_status": "failed",
                "execution_results": {
                    "combined_sql": {
                        "applicable": True,
                        "execution_status": "failed",
                        "output_availability": "not_executed",
                    }
                },
            }
        ]
    )

    result = asyncio.run(SqlAgentWorkflow(FakeAgent(outputs), sql_probe=probe).run("Query"))

    assert result.pipeline_status == "blocked"
    assert result.stopped_at_stage == "stage_3_3"


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


def test_workflow_stops_at_stage_one_five_with_nested_question() -> None:
    outputs = [
        {"OUTPUT_JSON_SCHEMA": {}, "MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {
            "MAPPED_JSON_SCHEMA": {
                "needs_clarification": True,
                "clarification_question": "By value, do you mean total or average value?",
            }
        },
    ]
    agent = FakeAgent(outputs)

    result = asyncio.run(SqlAgentWorkflow(agent).run("Show residential sale value in Pune in 2024"))

    assert result.pipeline_status == "needs_clarification"
    assert result.stopped_at_stage == "stage_1_5"
    assert result.clarification_question == "By value, do you mean total or average value?"


def test_workflow_stops_at_stage_one_six_with_relationship_question() -> None:
    outputs = [
        {"OUTPUT_JSON_SCHEMA": {}, "MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {
            "metric_relationship_status": "needs_clarification",
            "MAPPED_JSON_SCHEMA": {
                "needs_clarification": True,
                "clarification_question": "Should the two metrics be calculated together?",
            },
        },
    ]
    agent = FakeAgent(outputs)

    result = asyncio.run(SqlAgentWorkflow(agent).run("Show sales and value for Pune in 2024"))

    assert result.pipeline_status == "needs_clarification"
    assert result.stopped_at_stage == "stage_1_6"
    assert result.clarification_question == "Should the two metrics be calculated together?"


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


def test_workflow_stops_at_stage_three_when_sql_build_has_question() -> None:
    outputs = [
        {"OUTPUT_JSON_SCHEMA": {}, "MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"algorithm_status": "ready", "final_algorithm_structure": {}},
        {"algorithm_status": "ready", "final_algorithm_structure": {}},
        {
            "sql_build_status": "blocked",
            "clarification_required": "Confirm whether the requested ranking needs a limit.",
        },
    ]
    agent = FakeAgent(outputs)

    result = asyncio.run(SqlAgentWorkflow(agent).run("Rank residential sale value in Pune in 2024"))

    assert result.pipeline_status == "needs_clarification"
    assert result.stopped_at_stage == "stage_3"
    assert result.clarification_question == "Confirm whether the requested ranking needs a limit."


def test_workflow_stops_at_sql_review_when_it_requests_clarification() -> None:
    outputs = [
        {"OUTPUT_JSON_SCHEMA": {}, "MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"MAPPED_JSON_SCHEMA": {"needs_clarification": False}},
        {"algorithm_status": "ready", "final_algorithm_structure": {}},
        {"algorithm_status": "ready", "final_algorithm_structure": {}},
        {"sql_build_status": "ready", "combined_sql": {"sql_query": "SELECT 1"}},
        {
            "sql_review_status": "blocked",
            "clarification_required": "Confirm whether null transactions should be excluded.",
        },
    ]
    agent = FakeAgent(outputs)

    result = asyncio.run(SqlAgentWorkflow(agent).run("Show residential sale value in Pune in 2024"))

    assert result.pipeline_status == "needs_clarification"
    assert result.stopped_at_stage == "stage_3_1"
    assert result.clarification_question == "Confirm whether null transactions should be excluded."


def test_workflow_reports_missing_stage_one_contract_key() -> None:
    agent = FakeAgent([{"intent": "total agreement value", "needs_clarification": False}])

    with pytest.raises(ValueError, match="OUTPUT_JSON_SCHEMA, MAPPED_JSON_SCHEMA"):
        asyncio.run(SqlAgentWorkflow(agent).run("Total residential sale value in Pune in 2024"))
