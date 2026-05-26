import json
import logging
from typing import Any

from app.llm import JsonAgent
from app.models import PipelineResponse
from app.prompt_renderer import PromptRenderer

logger = logging.getLogger(__name__)


class SqlAgentWorkflow:
    """Executes the supplied prompt stages in their dependency order."""

    def __init__(self, agent: JsonAgent, renderer: PromptRenderer | None = None) -> None:
        self._agent = agent
        self._renderer = renderer or PromptRenderer()

    async def run(
        self,
        user_query: str,
        include_intermediate_stages: bool = True,
        semantic_context: dict[str, Any] | None = None,
    ) -> PipelineResponse:
        stages: dict[str, dict[str, Any]] = {}
        semantic_context = semantic_context or {}

        stage_1 = await self._agent.complete_json("stage_1", self._renderer.stage_1(user_query))
        stages["stage_1"] = stage_1
        if self._needs_clarification(stage_1):
            return self._clarification_response(
                user_query, "stage_1", stage_1, stages, include_intermediate_stages
            )

        stage_1_5 = await self._agent.complete_json(
            "stage_1_5", self._renderer.stage_1_5(user_query, stage_1)
        )
        stages["stage_1_5"] = stage_1_5
        if self._needs_clarification(stage_1_5):
            return self._clarification_response(
                user_query, "stage_1_5", stage_1_5, stages, include_intermediate_stages
            )

        stage_1_6 = await self._agent.complete_json(
            "stage_1_6", self._renderer.stage_1_6(user_query, stage_1_5)
        )
        stages["stage_1_6"] = stage_1_6
        if self._needs_clarification(stage_1_6):
            return self._clarification_response(
                user_query, "stage_1_6", stage_1_6, stages, include_intermediate_stages
            )

        stage_2 = await self._agent.complete_json("stage_2", self._renderer.stage_2(stage_1_6))
        stages["stage_2"] = stage_2
        if stage_2.get("algorithm_status") == "needs_clarification":
            return self._clarification_response(
                user_query, "stage_2", stage_2, stages, include_intermediate_stages
            )

        stage_2_1 = await self._agent.complete_json(
            "stage_2_1",
            self._renderer.stage_2_1_prompt(),
            self._renderer.stage_2_1_context(stage_2, semantic_context),
        )
        stages["stage_2_1"] = stage_2_1
        if stage_2_1.get("algorithm_status") == "needs_clarification":
            return self._clarification_response(
                user_query, "stage_2_1", stage_2_1, stages, include_intermediate_stages
            )

        stage_3 = await self._agent.complete_json("stage_3", self._renderer.stage_3(stage_2_1))
        stages["stage_3"] = stage_3
        logger.info("Stage 3 generated SQL output:\n%s", json.dumps(stage_3, indent=2))

        stage_3_1 = await self._agent.complete_json(
            "stage_3_1", self._renderer.stage_3_1(stage_2_1, stage_3)
        )
        stages["stage_3_1"] = stage_3_1
        logger.info("Stage 3.1 SQL review output:\n%s", json.dumps(stage_3_1, indent=2))

        completed = stage_3.get("sql_build_status") == "ready"
        approved = stage_3_1.get("sql_review_status") == "approved"
        status = "completed" if completed and approved else "blocked"
        message = (
            "SQL was generated and approved by the SQL review stage."
            if status == "completed"
            else "SQL generation or SQL review did not reach approved status."
        )
        return PipelineResponse(
            query=user_query,
            pipeline_status=status,
            message=message,
            stopped_at_stage="stage_3_1" if status == "blocked" else "",
            clarification_question=self._clarification_question(stage_3_1),
            next_action=(
                "Inspect sql_review_output errors and correct the prompt/schema or SQL generation logic."
                if status == "blocked"
                else ""
            ),
            sql_build_output=stage_3,
            sql_review_output=stage_3_1,
            stages=stages if include_intermediate_stages else None,
        )

    @staticmethod
    def _needs_clarification(output: dict[str, Any]) -> bool:
        if output.get("needs_clarification") is True:
            return True
        mapped = output.get("MAPPED_JSON_SCHEMA")
        return isinstance(mapped, dict) and mapped.get("needs_clarification") is True

    @staticmethod
    def _clarification_question(output: dict[str, Any]) -> str:
        question = output.get("clarification_question")
        if isinstance(question, str):
            return question
        mapped = output.get("MAPPED_JSON_SCHEMA")
        if isinstance(mapped, dict) and isinstance(mapped.get("clarification_question"), str):
            return mapped["clarification_question"]
        clarification = output.get("clarification_required")
        if isinstance(clarification, str) and clarification:
            return clarification
        validation = output.get("calculation_logic_validation")
        if isinstance(validation, list):
            questions = [
                item.get("clarification_required", "")
                for item in validation
                if isinstance(item, dict) and item.get("clarification_required")
            ]
            if questions:
                return " ".join(questions)
        return ""

    def _clarification_response(
        self,
        query: str,
        stage_name: str,
        output: dict[str, Any],
        stages: dict[str, dict[str, Any]],
        include_intermediate_stages: bool,
    ) -> PipelineResponse:
        return PipelineResponse(
            query=query,
            pipeline_status="needs_clarification",
            message="More information is required before an SQL algorithm can be created.",
            stopped_at_stage=stage_name,
            clarification_question=self._clarification_question(output),
            next_action=(
                "Send a new POST request with one complete corrected query containing "
                "your original requirements and the clarification answer."
            ),
            stages=stages if include_intermediate_stages else None,
        )
