import json
from pathlib import Path

MEASUREMENTS = (
    Path(__file__).resolve().parents[1]
    / "research"
    / "dependency-semantics"
    / "structural_effect_measurements.json"
)


def _measurements() -> dict[str, object]:
    return json.loads(MEASUREMENTS.read_text())


def test_operator_inventory_is_the_precommitted_small_vocabulary() -> None:
    payload = _measurements()
    assert payload["operator_inventory"] == {
        "conditions": ["if", "provided", "when", "whenever"],
        "hypothetical_auxiliaries": ["could", "might", "would"],
        "introduce": ["assume", "define", "fix", "let", "set", "suppose"],
        "name": ["call", "mean", "say", "term"],
        "support_nouns": ["consequence"],
        "support_verbs": ["apply", "follow", "invoke", "use"],
    }


def test_structural_require_screen_removes_reference_only_false_authority() -> None:
    payload = _measurements()
    effects = payload["effects"]
    baseline = effects["resolved_reference_implies_require_baseline"]

    assert baseline == {
        "fp": 12,
        "precision": 0.3684210526315789,
        "recall": 1.0,
        "tp": 7,
    }
    assert effects["require_tp"] == 5
    assert effects["require_fp"] == 0
    assert effects["require_fn"] == 2
    assert effects["require_precision"] == 1.0
    assert effects["require_recall"] == 0.7142857142857143
    assert effects["require_endpoint_exact_rate"] == 0.7142857142857143


def test_recognized_requirements_have_exact_expected_reference_endpoints() -> None:
    payload = _measurements()
    records = payload["effects"]["records"]
    recognized = [record for record in records if "require" in record["actual"]]

    assert {record["id"] for record in recognized} == {
        "require-by-ref",
        "require-follows-from",
        "require-using",
        "require-applying",
        "require-consequence",
    }
    assert all(record["prerequisites"] == ["THORNREF1"] for record in recognized)
    assert all(record["rules"] == ["support-operator"] for record in recognized)


def test_missed_pressure_cases_remain_missed_instead_of_post_hoc_tuning() -> None:
    payload = _measurements()
    records = {record["id"]: record for record in payload["effects"]["records"]}

    assert records["require-joint"]["actual"] == []
    assert records["require-alternative"]["actual"] == []
    assert records["declare-write"]["actual"] == []
    assert records["visibility-retract"]["actual"] == []
    assert records["status-unproved"]["actual"] == []
    assert records["status-established"]["actual"] == []
    assert payload["effects"]["visibility_exact_grounding_rate"] == 0.0
    assert payload["effects"]["status_supported"] is False


def test_declaration_screen_is_conservative_and_exact_where_matched() -> None:
    payload = _measurements()
    declarations = payload["declarations"]

    assert declarations["precision"] == 1.0
    assert declarations["recall"] == 0.5714285714285714
    assert declarations["unsafe_negative_cases"] == 0
    assert declarations["negative_cases"] == 17
    assert declarations["false_authority_case_rate"] == 0.0
    assert declarations["exact_grounding_rate_on_matched"] == 1.0
