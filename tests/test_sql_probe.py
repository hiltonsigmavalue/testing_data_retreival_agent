from sqlalchemy import create_engine, text

from app.config import Settings
from app.sql_probe import SqlProbeService


def _probe(sample_limit: int = 25) -> SqlProbeService:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE transactions ("
                "location_name TEXT, micro_market TEXT, village_name TEXT, agreement_price INTEGER)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO transactions "
                "(location_name, micro_market, village_name, agreement_price) "
                "VALUES ('Baner', 'Western Pune', 'Baner', 120)"
            )
        )
    return SqlProbeService(Settings(SQL_PROBE_SAMPLE_LIMIT=sample_limit), engine=engine)


def _review(query: str) -> dict:
    return {
        "sql_review_status": "approved",
        "metric_relationship": "combined",
        "approved_sql": {"combined_sql": {"sql_query": query}},
    }


def test_sql_probe_executes_reviewed_select_and_returns_sample_data() -> None:
    result = _probe().execute_approved_sql(
        _review("SELECT agreement_price FROM transactions WHERE location_name = 'Baner'"), 1
    )

    assert result["sql_probe_status"] == "success"
    assert result["execution_results"]["combined_sql"]["row_count"] == 1
    assert result["execution_results"]["combined_sql"]["sample_output"] == [
        {"agreement_price": 120}
    ]
    assert result["send_to_sql_observe"] is True


def test_sql_probe_collects_evidence_for_wrong_spatial_column_mapping() -> None:
    result = _probe().execute_approved_sql(
        _review(
            "SELECT agreement_price FROM transactions "
            "WHERE location_name = 'Western Pune'"
        ),
        1,
    )

    assert result["sql_probe_status"] == "failed"
    assert result["needs_correction"] is True
    assert result["column_value_verification"][0]["verification_status"] == "found_in_other_column"
    instruction = result["correction_instructions_for_sql_observe"][0]
    assert instruction["suggested_candidate_column"] == "micro_market"
    assert instruction["evidence_count"] == 1


def test_sql_probe_counts_full_result_while_limiting_returned_samples() -> None:
    probe = _probe(sample_limit=1)
    engine = probe._engine
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO transactions "
                "(location_name, micro_market, village_name, agreement_price) "
                "VALUES ('Baner', 'Western Pune', 'Baner', 140)"
            )
        )

    result = probe.execute_approved_sql(
        _review("SELECT agreement_price FROM transactions WHERE location_name = 'Baner'"), 1
    )
    execution = result["execution_results"]["combined_sql"]

    assert execution["row_count"] == 2
    assert len(execution["sample_output"]) == 1
    assert "sample is limited" in execution["output_summary"]


def test_sql_probe_rejects_non_select_statement_before_execution() -> None:
    result = _probe().execute_approved_sql(_review("DELETE FROM transactions"), 1)

    execution = result["execution_results"]["combined_sql"]
    assert execution["execution_status"] == "failed"
    assert "SELECT queries only" in execution["error_details"]
