import json
from pathlib import Path

from pydantic import BaseModel, Field

from thorn.eval import _load_cases, _select_unit
from thorn.latex import extract_project
from thorn.support import SupportKind


class SupportMatrixExpectation(BaseModel):
    claim_count: int
    edge_kinds: list[SupportKind] = Field(default_factory=list)
    unsupported_load_bearing: list[str] = Field(default_factory=list)
    trailing_binders: list[str] = Field(default_factory=list)
    reverse_result_dependencies: list[str] = Field(default_factory=list)


def _load_support_expectations() -> dict[str, SupportMatrixExpectation]:
    payload = json.loads(
        Path("eval/support-expectations.json").read_text(encoding="utf-8")
    )
    if not isinstance(payload, dict):
        raise ValueError("support expectation manifest must be an object")
    return {
        str(name): SupportMatrixExpectation.model_validate(expectation)
        for name, expectation in payload.items()
    }


def test_support_expectations_reference_public_cases() -> None:
    cases = _load_cases(Path("eval/cases"))
    case_names = {expectation.name for _, expectation in cases}
    support_names = set(_load_support_expectations())

    assert len(support_names) >= 4
    assert support_names <= case_names


def test_public_support_ir_matrix_matches_exact_expectations() -> None:
    cases = {
        expectation.name: (tex_path, expectation)
        for tex_path, expectation in _load_cases(Path("eval/cases"))
    }

    for name, expected in _load_support_expectations().items():
        tex_path, case = cases[name]
        project = extract_project(tex_path)
        unit = _select_unit(project.units, case)
        graph = project.proof_support_graph
        claims = graph.claims_for_result(unit.identifier)
        claim_ids = {claim.identifier for claim in claims}

        observed_edge_kinds = sorted(
            edge.kind
            for edge in graph.edges
            if edge.target_claim_identifier in claim_ids
        )
        observed_unsupported = sorted(
            graph.claim(identifier).raw
            for identifier in graph.unsupported_load_bearing_claim_ids()
            if graph.claim(identifier).result_identifier == unit.identifier
        )
        observed_binders = [
            bound.name
            for claim in claims
            for qualifier in claim.qualifiers
            for bound in qualifier.bound_names
        ]

        assert len(claims) == expected.claim_count, name
        assert observed_edge_kinds == sorted(expected.edge_kinds), name
        assert observed_unsupported == sorted(expected.unsupported_load_bearing), name
        assert observed_binders == expected.trailing_binders, name
        assert (
            project.dependency_graph.reverse_dependency_ids(unit.identifier)
            == expected.reverse_result_dependencies
        ), name


def test_clearly_is_not_treated_as_support() -> None:
    cases = {
        expectation.name: tex_path
        for tex_path, expectation in _load_cases(Path("eval/cases"))
    }
    project = extract_project(
        cases["load-bearing sneaky prose feeds a downstream theorem"]
    )

    assert all(
        "clearly" not in edge.raw_justification.casefold()
        for edge in project.proof_support_graph.edges
    )
