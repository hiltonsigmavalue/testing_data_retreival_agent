import json
from typing import Any

import promt
from schema import SPACE_SCHEMA, TRANSACTION_QUERY_SCHEMA


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True)


def _fill(template: str, replacements: dict[str, str]) -> str:
    """Replace only named context tokens; prompt JSON braces must remain literal."""
    rendered = template
    for token, value in replacements.items():
        rendered = rendered.replace("{" + token + "}", value)
    return rendered


class PromptRenderer:
    def stage_1(self, user_query: str) -> str:
        return _fill(
            promt.stage_1,
            {
                "schema": TRANSACTION_QUERY_SCHEMA,
                "space_schema": SPACE_SCHEMA,
                "user_query": user_query,
            },
        )

    def stage_1_5(self, user_query: str, stage_1_output: dict[str, Any]) -> str:
        return _fill(
            promt.stage_1_5,
            {
                "OUTPUT_JSON_SCHEMA": _json(stage_1_output["OUTPUT_JSON_SCHEMA"]),
                "MAPPED_JSON_SCHEMA": _json(stage_1_output["MAPPED_JSON_SCHEMA"]),
                "user_query": user_query,
            },
        )

    def stage_1_6(self, user_query: str, stage_1_5_output: dict[str, Any]) -> str:
        return _fill(
            promt.stage_1_6,
            {
                "MAPPED_JSON_SCHEMA": _json(stage_1_5_output["MAPPED_JSON_SCHEMA"]),
                "user_query": user_query,
            },
        )

    def stage_2(self, stage_1_6_output: dict[str, Any]) -> str:
        return _fill(
            promt.stage_2,
            {
                "schema": TRANSACTION_QUERY_SCHEMA,
                # The full Stage 1.6 payload includes its metric_relationship decision.
                "MAPPED_JSON_SCHEMA": _json(stage_1_6_output),
            },
        )

    def stage_2_1_prompt(self) -> str:
        return promt.stage_2_1

    def stage_2_1_context(
        self, stage_2_output: dict[str, Any], semantic_context: dict[str, Any]
    ) -> str:
        return _json(
            {
                "Stage 2 JSON schema": stage_2_output,
                "Transaction schema": TRANSACTION_QUERY_SCHEMA,
                "Attribute master tables": semantic_context.get("attribute_master_tables", {}),
                "Distinct database values": semantic_context.get("distinct_database_values", {}),
                "Lookup results": semantic_context.get("lookup_results", {}),
            }
        )

    def stage_3(self, stage_2_output: dict[str, Any]) -> str:
        return _fill(
            promt.stage_3,
            {
                "algorithm_status": str(stage_2_output.get("algorithm_status", "")),
                "final_algorithm_structure": _json(
                    stage_2_output.get("final_algorithm_structure", {})
                ),
                "schema": TRANSACTION_QUERY_SCHEMA,
            },
        )

    def stage_3_1(
        self, stage_2_output: dict[str, Any], stage_3_output: dict[str, Any]
    ) -> str:
        return _fill(
            promt.stage_3_1,
            {
                "final_algorithm_structure": _json(
                    stage_2_output.get("final_algorithm_structure", {})
                ),
                "sql_build_output": _json(stage_3_output),
                "schema": TRANSACTION_QUERY_SCHEMA,
            },
        )
