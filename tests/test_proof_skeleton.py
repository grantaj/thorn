from pathlib import Path

from thorn.eval_review import build_result_review_context
from thorn.latex import extract_project
from thorn.proof_skeleton import build_proof_skeleton, SkeletonSourceKind
from thorn.semantic_review_render import build_semantic_review_request


CASES = Path("eval/cases/ladder")


def _build(path: Path, target_identifier: str):
    project = extract_project(path)
    unit = project.unit(target_identifier)
    context = build_result_review_context(project, target_identifier)
    assert len(context.items) == 1
    request = build_semantic_review_request(context.items[0])
    return unit, build_proof_skeleton(unit, request)


def test_skeleton_retains_math_atoms_but_not_full_theorem_prose() -> None:
    unit, skeleton = _build(
        CASES / "03_hypotheses/clean_nonzero_cancellation.tex",
        "thm:clean-nonzero",
    )

    rendered = skeleton.render_initial()
    assert rendered.startswith("T0:")
    assert "a\\ne 0" in rendered
    assert "ax=ay" in rendered
    assert "For all real numbers" not in rendered
    assert skeleton.source("T0").text == unit.statement
    assert skeleton.source("T0").source_range == unit.statement_range


def test_prose_only_nodes_are_withheld_but_exactly_recoverable() -> None:
    unit, skeleton = _build(
        CASES / "06_support_structure/sneaky_prose_downstream.tex",
        "lem:sneaky-limit",
    )

    rendered = skeleton.render_initial()
    assert rendered.startswith("T0:~\n")
    assert "full rank" not in rendered
    assert skeleton.source("T0").text == unit.statement

    claim_sources = [
        source for source in skeleton.sources if source.kind == SkeletonSourceKind.CLAIM
    ]
    full_rank = next(source for source in claim_sources if "full rank" in source.text)
    assert full_rank.source_span is not None
    assert full_rank.source_span.end_offset > full_rank.source_span.start_offset
    assert skeleton.source(full_rank.address).text == full_rank.text
    assert f"{full_rank.address}:~" in rendered


def test_skeleton_addresses_are_unique_deterministic_and_not_source_payloads() -> None:
    _, first = _build(
        CASES / "03_hypotheses/clean_nonzero_cancellation.tex",
        "thm:clean-nonzero",
    )
    _, second = _build(
        CASES / "03_hypotheses/clean_nonzero_cancellation.tex",
        "thm:clean-nonzero",
    )

    addresses = [source.address for source in first.sources]
    assert len(addresses) == len(set(addresses))
    assert first.render_initial() == second.render_initial()
    assert first.canonical_json() == second.canonical_json()

    rendered = first.render_initial()
    for source in first.sources:
        assert source.address in rendered
        source_text = source.text.strip()
        if (
            source_text
            and source.kind
            in {
                SkeletonSourceKind.RESULT,
                SkeletonSourceKind.CLAIM,
                SkeletonSourceKind.SUPPORT,
            }
            and not any(marker in source.text for marker in ("$", "\\[", "\\("))
        ):
            assert source_text not in rendered


def test_unknown_source_address_fails_loudly() -> None:
    _, skeleton = _build(
        CASES / "03_hypotheses/clean_nonzero_cancellation.tex",
        "thm:clean-nonzero",
    )

    try:
        skeleton.source("C999")
    except KeyError as exc:
        assert "C999" in str(exc)
    else:
        raise AssertionError("unknown source address should fail loudly")
