from __future__ import annotations

from pathlib import Path

from thorn.eval_review import build_result_review_context
from thorn.latex import extract_project
from thorn.lean_export import LeanExportStatus, project_lean
from thorn.semantic_review_render import build_semantic_review_request
from thorn.semantic_transformations import build_semantic_transformation_ir

_CASES = Path(__file__).parent / "lean_cases"


def _semantic(path: Path):
    project = extract_project(path)
    unit = project.unit("thm:main")
    context = build_result_review_context(project, unit.identifier)
    request = build_semantic_review_request(context.items[0])
    return build_semantic_transformation_ir(
        unit,
        request,
        symbol_table=project.symbol_table,
        dependency_graph=project.dependency_graph,
    )


def test_named_domain_n_is_not_promoted_to_lean_nat() -> None:
    semantic = _semantic(_CASES / "theorem_application_named_domain.tex")
    export = project_lean(semantic)

    assert export.status == LeanExportStatus.UNSUPPORTED
    assert not export.is_mechanically_checkable
    assert len(export.obligations) == 1
    assert export.obligations[0].reason == (
        "predicate Nat domain is not mechanically established by canonical Proof IR"
    )
    assert "Nat → Prop" not in export.source
    assert "Thorn Lean export status: unsupported" in export.source
