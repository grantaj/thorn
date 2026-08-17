from __future__ import annotations

import re

from thorn.dependencies import DependencyGraph, DependencyResolution
from thorn.evidence import InferenceStatus, StructuralEvidence
from thorn.formula_ir import (
    ExprLoweringStatus,
    IdentifierExpr,
    MathExpr,
    RelationExpr,
    RelationOperator,
    lower_math_expression,
)
from thorn.models import TheoremUnit
from thorn.result_application import ResultApplicationMatch, match_result_application
from thorn.support import Claim, ProofSupportGraph, SupportEdge, SupportKind

_MATH_RE = re.compile(
    r"(?s)(\$\$.*?\$\$|\\\[.*?\\\]|\\\(.*?\\\)|(?<!\$)\$(?!\$).*?(?<!\\)\$)"
)
_ASSERTED_APPLICATION_RE = re.compile(
    r"^\s*(?:by|using|from|applying|apply|invoking|invoke)\s+(.+?),\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _resolved_result_identifier(
    dependencies: DependencyGraph,
    *,
    source_identifier: str,
    target_label: str,
) -> str | None:
    identifiers = {
        edge.target_identifier
        for edge in dependencies.edges
        if edge.source_identifier == source_identifier
        and edge.target_label == target_label
        and edge.resolution == DependencyResolution.RESOLVED
        and edge.target_identifier is not None
    }
    return next(iter(identifiers)) if len(identifiers) == 1 else None


def _fully_lowered_expression(text: str) -> MathExpr | None:
    lowered = lower_math_expression(text)
    if lowered.status != ExprLoweringStatus.FULL:
        return None
    return lowered.expression


def _math_expressions(text: str) -> list[MathExpr]:
    matches = list(_MATH_RE.finditer(text))
    texts = [match.group(0) for match in matches] if matches else [text]
    expressions: list[MathExpr] = []
    for item in texts:
        expression = _fully_lowered_expression(item)
        if expression is not None and expression not in expressions:
            expressions.append(expression)
    return expressions


def _asserted_target_text(claim: Claim) -> str | None:
    """Return the claimed consequence of an explicit support assertion.

    This is intentionally stricter than merely finding a support-looking word
    somewhere before a reference. The source must grammatically present a
    support phrase followed by a claimed consequence. Mathematical matching
    then decides whether the cited result can actually produce that consequence.
    """

    match = _ASSERTED_APPLICATION_RE.match(claim.raw.strip())
    return match.group(2).strip() if match is not None else None


def _target_expressions(claim: Claim) -> list[MathExpr]:
    """Return mechanically isolated target candidates from the asserted consequence.

    A consequence may contain a binding as well as its claimed result, for
    example ``with $x=2$, we obtain $Q(2)$``. Rather than guessing which math
    fragment is the conclusion, retain each fully lowered fragment and require
    the cited result to select exactly one compatible target.
    """

    target_text = _asserted_target_text(claim)
    return _math_expressions(target_text) if target_text is not None else []


def _binding_values(claim: Claim, name: str) -> list[MathExpr]:
    """Recover exact equality bindings stated in the application sentence.

    These are consistency checks only. The cited-result/target match remains the
    source of the inferred universal binding; an explicit equality can veto that
    inference when it disagrees but cannot make an otherwise ambiguous match
    confident.
    """

    values: list[MathExpr] = []
    for expression in _math_expressions(claim.raw):
        if (
            not isinstance(expression, RelationExpr)
            or expression.operator != RelationOperator.EQUAL
        ):
            continue
        if isinstance(expression.left, IdentifierExpr) and expression.left.name == name:
            values.append(expression.right)
        elif isinstance(expression.right, IdentifierExpr) and expression.right.name == name:
            values.append(expression.left)
    return values


def _bindings_agree(claim: Claim, application: ResultApplicationMatch) -> bool:
    for binding in application.bindings:
        explicit_values = _binding_values(claim, binding.name)
        if explicit_values and any(value != binding.argument for value in explicit_values):
            return False
    return True


def _application_match(
    *,
    claim: Claim,
    cited_result: TheoremUnit,
) -> tuple[MathExpr, ResultApplicationMatch] | None:
    result_expression = _fully_lowered_expression(cited_result.statement)
    if result_expression is None:
        return None

    matches: list[tuple[MathExpr, ResultApplicationMatch]] = []
    for target in _target_expressions(claim):
        application = match_result_application(result_expression, target)
        if application is not None and _bindings_agree(claim, application):
            matches.append((target, application))
    return matches[0] if len(matches) == 1 else None


def _corroborated_edge(
    edge: SupportEdge,
    *,
    graph: ProofSupportGraph,
    dependencies: DependencyGraph,
    units: dict[str, TheoremUnit],
) -> SupportEdge:
    if (
        edge.kind != SupportKind.RESULT_REFERENCE
        or not edge.explicit
        or edge.status == InferenceStatus.CONFIDENT
        or edge.target_label is None
    ):
        return edge

    claim = graph.claim(edge.target_claim_identifier)
    if _asserted_target_text(claim) is None:
        return edge
    cited_identifier = _resolved_result_identifier(
        dependencies,
        source_identifier=claim.result_identifier,
        target_label=edge.target_label,
    )
    if cited_identifier is None:
        return edge
    cited_result = units.get(cited_identifier)
    if cited_result is None:
        return edge

    matched = _application_match(claim=claim, cited_result=cited_result)
    if matched is None:
        return edge
    _target, application = matched

    binding_names = ", ".join(binding.name for binding in application.bindings)
    binding_text = (
        f"; universal bindings are uniquely fixed ({binding_names})"
        if binding_names
        else ""
    )
    precondition_text = (
        "; any instantiated precondition remains a separate proof obligation"
        if application.precondition is not None
        else ""
    )
    evidence = StructuralEvidence(
        reason=(
            "explicit proof-position result reference is corroborated by an asserted "
            "application role, exact result identity, and a unique fully lowered "
            "target/application match"
            f"{binding_text}{precondition_text}"
        ),
        source=edge.source,
        target=claim.source,
        context=claim.raw,
        frontend="thorn-math",
    )
    return edge.model_copy(
        update={
            "confidence": 1.0,
            "status": InferenceStatus.CONFIDENT,
            "evidence": [*edge.evidence, evidence],
        }
    )


def corroborate_explicit_result_support(
    graph: ProofSupportGraph,
    *,
    dependencies: DependencyGraph,
    units: list[TheoremUnit],
) -> ProofSupportGraph:
    """Strengthen only explicit cited-result uses whose source role and formula agree.

    Local NLP is intentionally conservative about references because a theorem
    can be mentioned without being consumed as a premise. This pass combines an
    asserted application role with independent deterministic mathematical
    evidence before semantic review or formal replay sees the relation.

    It does not discharge implication preconditions, prove the target, repair a
    contradictory source binding, or make a bare/expository reference confident.
    A failed, non-unique, or merely expository match leaves the original
    ambiguity untouched.
    """

    unit_by_identifier = {unit.identifier: unit for unit in units}
    edges = [
        _corroborated_edge(
            edge,
            graph=graph,
            dependencies=dependencies,
            units=unit_by_identifier,
        )
        for edge in graph.edges
    ]
    return graph.model_copy(update={"edges": edges})
