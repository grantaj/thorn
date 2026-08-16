from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from thorn.canonical_proof_ir import (
    CanonicalNodeKind,
    CanonicalProofEdge,
    CanonicalProofIR,
    CanonicalProofNode,
    CanonicalProofSource,
    build_canonical_proof_ir,
)
from thorn.formula_ir import (
    ApplyExpr,
    ExprLoweringStatus,
    LogicalExpr,
    MathExpr,
    NotExpr,
    OperatorExpr,
    QuantifiedExpr,
    RelationExpr,
    SetExpr,
    TupleExpr,
    lower_math_expression,
    render_math_expr,
)
from thorn.models import TheoremUnit
from thorn.semantic_review_render import SemanticReviewRequest


class ExpressionOwnerKind(StrEnum):
    NODE = "node"
    EDGE = "edge"


class ExpressionProvenance(BaseModel):
    """Source-address association for one expression or subexpression."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_kind: ExpressionOwnerKind
    owner_address: str
    path: tuple[str, ...] = ()
    source_address: str


class CanonicalTypedProofNode(CanonicalProofNode):
    """Graph node with a canonical expression when lowering is justified."""

    expression: MathExpr | None = None
    expression_status: ExprLoweringStatus | None = None


class CanonicalTypedProofEdge(CanonicalProofEdge):
    """Existing graph edge plus any safely lowered mathematical payload."""

    expression: MathExpr | None = None
    expression_status: ExprLoweringStatus | None = None


class CanonicalTypedProofIR(BaseModel):
    """Graph-derived proof IR enriched with Thorn-owned typed expressions."""

    result_identifier: str
    nodes: list[CanonicalTypedProofNode] = Field(default_factory=list)
    edges: list[CanonicalTypedProofEdge] = Field(default_factory=list)
    sources: list[CanonicalProofSource] = Field(default_factory=list)
    pruned_claims: int = 0
    unresolved_math_claims: int = 0
    expression_provenance: list[ExpressionProvenance] = Field(default_factory=list)

    def _legacy_graph(self) -> CanonicalProofIR:
        """Project to the issue-57 graph representation for compatible rendering."""

        return CanonicalProofIR(
            result_identifier=self.result_identifier,
            nodes=[
                CanonicalProofNode(
                    address=node.address,
                    kind=node.kind,
                    atom=node.atom,
                    opaque=node.opaque,
                )
                for node in self.nodes
            ],
            edges=[
                CanonicalProofEdge(
                    address=edge.address,
                    kind=edge.kind,
                    source=edge.source,
                    target=edge.target,
                    status=edge.status,
                    atom=edge.atom,
                )
                for edge in self.edges
            ],
            sources=self.sources,
            pruned_claims=self.pruned_claims,
            unresolved_math_claims=self.unresolved_math_claims,
        )

    def render_initial(self) -> str:
        """Retain the existing graph-derived debug rendering unchanged."""

        return self._legacy_graph().render_initial()

    def source(self, address: str) -> CanonicalProofSource:
        for item in self.sources:
            if item.address == address:
                return item
        raise KeyError(f"unknown canonical-proof source address {address!r}")

    def expression_source(
        self,
        owner_address: str,
        path: tuple[str, ...] = (),
    ) -> CanonicalProofSource:
        for item in self.expression_provenance:
            if item.owner_address == owner_address and item.path == path:
                return self.source(item.source_address)
        raise KeyError(f"unknown expression source {owner_address!r} at path {path!r}")

    @property
    def opaque_nodes(self) -> int:
        return sum(node.opaque for node in self.nodes)

    @property
    def expression_nodes(self) -> int:
        return sum(node.expression is not None for node in self.nodes)

    @property
    def fully_lowered_nodes(self) -> int:
        return sum(
            node.expression_status == ExprLoweringStatus.FULL for node in self.nodes
        )

    @property
    def partially_lowered_nodes(self) -> int:
        return sum(
            node.expression_status == ExprLoweringStatus.PARTIAL for node in self.nodes
        )

    @property
    def opaque_expression_nodes(self) -> int:
        return sum(
            node.expression_status == ExprLoweringStatus.OPAQUE for node in self.nodes
        )


def _expression_paths(expression: MathExpr) -> tuple[tuple[str, ...], ...]:
    paths: list[tuple[str, ...]] = []

    def visit(item: MathExpr, path: tuple[str, ...]) -> None:
        paths.append(path)
        if isinstance(item, ApplyExpr):
            visit(item.function, (*path, "function"))
            for index, argument in enumerate(item.arguments):
                visit(argument, (*path, "arguments", str(index)))
        elif isinstance(item, OperatorExpr):
            for index, argument in enumerate(item.arguments):
                visit(argument, (*path, "arguments", str(index)))
        elif isinstance(item, RelationExpr):
            visit(item.left, (*path, "left"))
            visit(item.right, (*path, "right"))
        elif isinstance(item, LogicalExpr):
            for index, argument in enumerate(item.arguments):
                visit(argument, (*path, "arguments", str(index)))
        elif isinstance(item, NotExpr):
            visit(item.operand, (*path, "operand"))
        elif isinstance(item, (TupleExpr, SetExpr)):
            for index, child in enumerate(item.items):
                visit(child, (*path, "items", str(index)))
        elif isinstance(item, QuantifiedExpr):
            visit(item.binder.name, (*path, "binder", "name"))
            if item.binder.domain is not None:
                visit(item.binder.domain, (*path, "binder", "domain"))
            visit(item.body, (*path, "body"))

    visit(expression, ())
    return tuple(paths)


def _node_input_text(
    node: CanonicalProofNode,
    source: CanonicalProofSource,
) -> str:
    if node.kind in {
        CanonicalNodeKind.RESULT,
        CanonicalNodeKind.DEPENDENCY,
    }:
        return source.text
    return node.atom


def _typed_node(
    node: CanonicalProofNode,
    source: CanonicalProofSource,
) -> CanonicalTypedProofNode:
    # The graph layer has already classified this as prose. Do not reinterpret a
    # short prose fragment as an identifier merely because it is tokenizable.
    if node.kind == CanonicalNodeKind.OPAQUE_PROSE:
        return CanonicalTypedProofNode(**node.model_dump())

    lowering = lower_math_expression(_node_input_text(node, source))
    return CanonicalTypedProofNode(
        **node.model_dump(),
        expression=lowering.expression,
        expression_status=lowering.status,
    )


def _typed_edge(edge: CanonicalProofEdge) -> CanonicalTypedProofEdge:
    if edge.atom is None:
        return CanonicalTypedProofEdge(**edge.model_dump())
    lowering = lower_math_expression(edge.atom)
    if lowering.status == ExprLoweringStatus.OPAQUE:
        return CanonicalTypedProofEdge(**edge.model_dump())
    return CanonicalTypedProofEdge(
        **edge.model_dump(),
        expression=lowering.expression,
        expression_status=lowering.status,
    )


def _provenance(
    *,
    owner_kind: ExpressionOwnerKind,
    owner_address: str,
    expression: MathExpr,
) -> list[ExpressionProvenance]:
    return [
        ExpressionProvenance(
            owner_kind=owner_kind,
            owner_address=owner_address,
            path=path,
            source_address=owner_address,
        )
        for path in _expression_paths(expression)
    ]


def build_canonical_typed_proof_ir(
    unit: TheoremUnit,
    request: SemanticReviewRequest,
) -> CanonicalTypedProofIR:
    """Partially elaborate the existing graph slice without changing its topology.

    The issue-57 graph-derived IR remains the graph/slicing authority. This layer
    replaces safely interpreted mathematical payloads with typed expressions while
    retaining the legacy atom as a deterministic diagnostic/debug rendering.
    """

    graph_ir = build_canonical_proof_ir(unit, request)
    sources = {source.address: source for source in graph_ir.sources}

    nodes = [_typed_node(node, sources[node.address]) for node in graph_ir.nodes]
    edges = [_typed_edge(edge) for edge in graph_ir.edges]
    provenance: list[ExpressionProvenance] = []
    for node in nodes:
        if node.expression is not None:
            provenance.extend(
                _provenance(
                    owner_kind=ExpressionOwnerKind.NODE,
                    owner_address=node.address,
                    expression=node.expression,
                )
            )
    for edge in edges:
        if edge.expression is not None:
            provenance.extend(
                _provenance(
                    owner_kind=ExpressionOwnerKind.EDGE,
                    owner_address=edge.address,
                    expression=edge.expression,
                )
            )

    return CanonicalTypedProofIR(
        result_identifier=graph_ir.result_identifier,
        nodes=nodes,
        edges=edges,
        sources=graph_ir.sources,
        pruned_claims=graph_ir.pruned_claims,
        unresolved_math_claims=graph_ir.unresolved_math_claims,
        expression_provenance=provenance,
    )


def render_typed_expression_debug(ir: CanonicalTypedProofIR) -> str:
    """Compact diagnostic view of typed node payloads; not the issue-65 LLM language."""

    lines: list[str] = []
    for node in ir.nodes:
        if node.expression is None:
            continue
        status = node.expression_status.value if node.expression_status is not None else "?"
        lines.append(f"{node.address}[{status}]:{render_math_expr(node.expression)}")
    return "\n".join(lines) + ("\n" if lines else "")
