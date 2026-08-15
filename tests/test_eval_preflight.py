from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import thorn.eval as eval_module
from thorn.eval import CaseExpectation
from thorn.linguistic import LinguisticDocument, LinguisticToken
from thorn.semantic_review import build_review_context

_PLACEHOLDER_RE = re.compile(r"THORN[A-Z]+\d+")


class StaticDependencyFrontend:
    name = "static-dependencies"

    def __init__(self) -> None:
        self.parsed: list[str] = []

    def parse(self, text: str) -> LinguisticDocument:
        self.parsed.append(text)
        tokens = [
            LinguisticToken(
                index=0,
                text="predicate",
                lemma="predicate",
                pos="VERB",
                dependency="ROOT",
                head_index=0,
                sentence_index=0,
                start=0,
                end=0,
            )
        ]
        for match in _PLACEHOLDER_RE.finditer(text):
            tokens.append(
                LinguisticToken(
                    index=len(tokens),
                    text=match.group(0),
                    lemma=match.group(0),
                    pos="PROPN",
                    dependency="obl",
                    head_index=0,
                    sentence_index=0,
                    start=match.start(),
                    end=match.end(),
                )
            )
        return LinguisticDocument(text=text, tokens=tokens)


def _write_ambiguous_project(path: Path) -> None:
    path.write_text(
        r"""\documentclass{article}
\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{lemma}\label{lem:base}
A base fact.
\end{lemma}
\begin{theorem}\label{thm:main}
A conclusion.
\end{theorem}
\begin{proof}
Via Lemma~\ref{lem:base}, the conclusion follows.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )


def _write_zero_item_project(path: Path) -> None:
    path.write_text(
        r"""\documentclass{article}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{theorem}\label{thm:clean}
Let $x$ be real. Then $x=x$.
\end{theorem}
\begin{proof}
This is immediate.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )


def _expectation(name: str, identifier: str) -> CaseExpectation:
    return CaseExpectation(
        name=name,
        kind="clean",
        modes=["review"],
        target_identifier=identifier,
    )


def _summary(output: str) -> dict[str, object]:
    start = output.find("{\n")
    assert start >= 0
    payload = json.loads(output[start:])
    assert isinstance(payload, dict)
    return payload


def test_semantic_evaluator_extraction_accepts_and_uses_linguistic_frontend(
    tmp_path: Path,
) -> None:
    tex = tmp_path / "main.tex"
    _write_ambiguous_project(tex)
    frontend = StaticDependencyFrontend()

    project = eval_module._extract_evaluation_project(
        tex,
        use_local_linguistic_frontend=True,
        linguistic_frontend=frontend,
    )

    assert frontend.parsed
    context = build_review_context(project)
    assert len(context.items) == 1
    assert context.items[0].result.identifier == "thm:main"


def test_targeted_preflight_preserves_stable_item_trigger_ids_and_status(
    tmp_path: Path,
) -> None:
    tex = tmp_path / "main.tex"
    _write_ambiguous_project(tex)
    project = eval_module._extract_evaluation_project(
        tex,
        use_local_linguistic_frontend=True,
        linguistic_frontend=StaticDependencyFrontend(),
    )
    unit = project.unit("thm:main")
    selected = build_review_context(project).items

    record = eval_module._targeted_preflight_record(
        tex_path=tex,
        project=project,
        unit=unit,
        expectation=_expectation("ambiguous support", "thm:main"),
    )

    assert record.semantic_review_item_count == 1
    assert record.review_item_identifiers == [selected[0].identifier]
    assert record.review_items[0].review_item_identifier == selected[0].identifier
    assert [
        trigger.relation_identifier
        for trigger in record.review_items[0].trigger_relations
    ] == selected[0].trigger_relation_identifiers
    assert {trigger.status for trigger in record.review_items[0].trigger_relations} == {
        "AMBIGUOUS"
    }
    assert record.would_make_semantic_request_count == 1
    assert record.provider_request_count == 0
    assert record.no_semantic_escalation_required is False


def test_targeted_preflight_groups_related_uncertain_edges_into_one_request(
    tmp_path: Path,
) -> None:
    tex = tmp_path / "main.tex"
    _write_ambiguous_project(tex)
    project = eval_module._extract_evaluation_project(
        tex,
        use_local_linguistic_frontend=True,
        linguistic_frontend=StaticDependencyFrontend(),
    )
    ambiguous = [
        edge
        for edge in project.proof_support_graph.edges
        if edge.status.value == "ambiguous"
    ]
    assert len(ambiguous) == 1
    project.proof_support_graph.edges.append(
        ambiguous[0].model_copy(
            update={"identifier": f"{ambiguous[0].identifier}:related"}
        )
    )

    record = eval_module._targeted_preflight_record(
        tex_path=tex,
        project=project,
        unit=project.unit("thm:main"),
        expectation=_expectation("grouped support", "thm:main"),
    )

    assert record.semantic_review_item_count == 1
    assert record.would_make_semantic_request_count == 1
    assert len(record.review_items[0].trigger_relations) == 2


def test_targeted_preflight_represents_zero_item_selection_explicitly(
    tmp_path: Path,
) -> None:
    tex = tmp_path / "main.tex"
    _write_zero_item_project(tex)
    project = eval_module._extract_evaluation_project(
        tex,
        use_local_linguistic_frontend=True,
        linguistic_frontend=StaticDependencyFrontend(),
    )

    record = eval_module._targeted_preflight_record(
        tex_path=tex,
        project=project,
        unit=project.unit("thm:clean"),
        expectation=_expectation("clean result", "thm:clean"),
    )

    assert record.semantic_review_item_count == 0
    assert record.review_item_identifiers == []
    assert record.review_items == []
    assert record.would_make_semantic_request_count == 0
    assert record.provider_request_count == 0
    assert record.no_semantic_escalation_required is True


def test_targeted_preflight_cli_is_keyless_and_never_instantiates_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case_dir = tmp_path / "cases"
    case_dir.mkdir()
    tex = case_dir / "ambiguous.tex"
    _write_ambiguous_project(tex)
    (case_dir / "ambiguous.json").write_text(
        json.dumps(
            {
                "name": "ambiguous support",
                "kind": "clean",
                "modes": ["review"],
                "target_identifier": "thm:main",
                "level": 1,
            }
        ),
        encoding="utf-8",
    )

    constructed_frontends: list[StaticDependencyFrontend] = []

    def make_linguistic_frontend() -> StaticDependencyFrontend:
        frontend = StaticDependencyFrontend()
        constructed_frontends.append(frontend)
        return frontend

    def forbidden_provider(model: str) -> object:
        raise AssertionError(f"targeted preflight instantiated provider {model}")

    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setattr(
        eval_module,
        "SpacyLinguisticFrontend",
        make_linguistic_frontend,
    )
    monkeypatch.setattr(eval_module, "OpenAIProvider", forbidden_provider)

    assert eval_module.main([str(case_dir), "--targeted-preflight"]) == 0
    summary = _summary(capsys.readouterr().out)

    assert constructed_frontends
    assert summary["mode"] == "targeted-preflight"
    assert summary["review_context"] == "targeted"
    assert summary["provider_instantiated"] is False
    assert summary["requests"] == 0
    assert summary["input_tokens"] == 0
    assert summary["output_tokens"] == 0
    assert summary["total_tokens"] == 0
    results = summary["results"]
    assert isinstance(results, list)
    assert results[0]["semantic_review_item_count"] == 1
    assert results[0]["provider_request_count"] == 0


def test_eval_help_uses_post_pr40_analysis_and_ir_terminology() -> None:
    help_text = eval_module._parser().format_help()

    assert "--analyze" in help_text
    assert "structural-analysis" in help_text
    assert "targeted SemanticReviewItem selection" in help_text
    assert "--check" not in help_text
