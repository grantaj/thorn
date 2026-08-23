from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path
from typing import Any

import thorn.project_context as project_context
from thorn.latex import extract_project
from thorn.spacy_linguistic import SpacyLinguisticFrontend

_SOURCE = r"""\documentclass{article}
\usepackage{amsthm}
\newtheorem{theorem}{Theorem}
\begin{document}
Define $x \star y$ to mean $x+y$.
\[
q := 1
\]
\begin{theorem}\label{thm:main}
For $x,y\in\mathbb R$, $x\star y=x+y$ and $q=q$.
\end{theorem}
\end{document}
"""


def _project_symbol(project: Any, name: str) -> Any | None:
    return next(
        (
            symbol
            for symbol in project.symbol_table.symbols
            if symbol.scope_identifier == "project" and symbol.name == name
        ),
        None,
    )


def _definition_rhs(project: Any, symbol_identifier: str) -> str | None:
    definition = next(
        (
            item
            for item in project.symbol_table.definitions
            if item.symbol_identifier == symbol_identifier
        ),
        None,
    )
    return definition.expression_latex if definition is not None else None


def _resolved_uses(project: Any, name: str) -> list[str | None]:
    return [
        use.resolved_symbol_identifier
        for use in project.symbol_table.uses
        if use.name == name
    ]


def measure() -> dict[str, Any]:
    """Ablate only the handwritten infix ``to mean`` bridge.

    The explicit ``q := 1`` declaration is frozen in the same source as a control:
    it must survive unchanged in both arms. Source/workspace/linguistic facts must
    also remain byte-for-byte equivalent. The only allowed differential is the
    mathematical alias authority supplied by the bridge under test.
    """

    frontend = SpacyLinguisticFrontend()
    with tempfile.TemporaryDirectory(prefix="thorn-issue-203-project-context-") as directory:
        path = Path(directory) / "paper.tex"
        path.write_text(_SOURCE, encoding="utf-8")

        baseline = extract_project(path, linguistic_frontend=frontend)

        original_bridge = project_context._ALIAS_BRIDGE_RE
        project_context._ALIAS_BRIDGE_RE = re.compile(r"(?!)")
        try:
            candidate = extract_project(path, linguistic_frontend=frontend)
        finally:
            project_context._ALIAS_BRIDGE_RE = original_bridge

    baseline_alias = _project_symbol(baseline, r"\star")
    candidate_alias = _project_symbol(candidate, r"\star")
    baseline_control = _project_symbol(baseline, "q")
    candidate_control = _project_symbol(candidate, "q")

    assert baseline_alias is not None
    assert _definition_rhs(baseline, baseline_alias.identifier) == "x+y"
    assert candidate_alias is None

    assert baseline_control is not None
    assert candidate_control is not None
    assert baseline_control.model_dump(mode="json") == candidate_control.model_dump(mode="json")
    assert _definition_rhs(baseline, baseline_control.identifier) == "1"
    assert _definition_rhs(candidate, candidate_control.identifier) == "1"
    assert _resolved_uses(baseline, "q") == _resolved_uses(candidate, "q")

    assert baseline.workspace is not None
    assert candidate.workspace is not None
    assert baseline.workspace.model_dump(mode="json") == candidate.workspace.model_dump(mode="json")
    assert baseline.linguistic_statements is not None
    assert candidate.linguistic_statements is not None
    baseline_statements = baseline.linguistic_statements.model_dump(mode="json")
    candidate_statements = candidate.linguistic_statements.model_dump(mode="json")
    assert baseline_statements == candidate_statements
    assert any(
        r"Define $x \star y$ to mean $x+y$." in statement.text
        for statement in candidate.linguistic_statements.statements
    )

    baseline_alias_uses = _resolved_uses(baseline, r"\star")
    candidate_alias_uses = _resolved_uses(candidate, r"\star")
    assert any(target == baseline_alias.identifier for target in baseline_alias_uses)
    assert candidate_alias_uses == []

    return {
        "issue": 203,
        "mechanism": "project_context infix alias bridge",
        "candidate_arm": "disable only _ALIAS_BRIDGE_RE",
        "source_and_linguistic_evidence_equal": True,
        "workspace_evidence_equal": True,
        "explicit_formula_control": {
            "source": r"q := 1",
            "baseline_definition": _definition_rhs(baseline, baseline_control.identifier),
            "candidate_definition": _definition_rhs(candidate, candidate_control.identifier),
            "unchanged": True,
        },
        "alias_differential": {
            "source": r"Define $x \star y$ to mean $x+y$.",
            "baseline_project_symbol": baseline_alias.identifier,
            "baseline_definition": _definition_rhs(baseline, baseline_alias.identifier),
            "baseline_resolved_uses": len(
                [target for target in baseline_alias_uses if target == baseline_alias.identifier]
            ),
            "candidate_project_symbol": None,
            "candidate_resolved_uses": 0,
        },
        "classification": (
            "material loss of explicit mathematical definition/identity; source evidence survives"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payload = measure()
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
