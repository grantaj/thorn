from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from thorn.evidence import InferenceStatus
from thorn.formula_ir import (
    ApplyExpr,
    Binder,
    IdentifierExpr,
    LiteralExpr,
    LogicalExpr,
    MathExpr,
    NotExpr,
    OpaqueExpr,
    OperatorExpr,
    QuantifiedExpr,
    Quantifier,
    RelationExpr,
    RelationOperator,
    SetExpr,
    TupleExpr,
)
from thorn.frontend import SourceSpan
from thorn.models import TheoremUnit
from thorn.proof_obligations import (
    ProofObligationIR,
    ProofProposition,
    ProofRuleKind,
    build_proof_obligation_ir,
)
from thorn.semantic_review_render import SemanticReviewRequest
from thorn.symbols import (
    Scope,
    ScopeKind,
    Symbol,
    SymbolIntroductionCandidate,
    SymbolRole,
    SymbolTable,
    SymbolUse,
)


class ResolutionStatus(StrEnum):
    """Identity status for one identifier occurrence."""

    BOUND = "bound"
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class ScopeOrigin(StrEnum):
    RESULT = "result"
    SOURCE = "source"
    BINDER = "binder"


class DeclarationKind(StrEnum):
    SOURCE = "source"
    SOURCE_CANDIDATE = "source_candidate"
    BINDER = "binder"


class ExpressionRef(BaseModel):
    """Stable reference to a canonical AST node, never a rewritten text fragment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_address: str
    path: tuple[str, ...] = ()


class ResolutionProvenance(BaseModel):
    """Source and AST provenance for a resolution-layer object."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_address: str | None = None
    source_span: SourceSpan | None = None
    expression_ref: ExpressionRef | None = None


class ResolvedScope(BaseModel):
    """A source or AST lexical scope with explicit parent certainty."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    origin: ScopeOrigin
    parent_address: str | None = None
    parent_status: InferenceStatus = InferenceStatus.UNRESOLVED
    source_scope_identifier: str | None = None
    source_kind: ScopeKind | None = None
    provenance: ResolutionProvenance = Field(default_factory=ResolutionProvenance)


class SymbolDeclaration(BaseModel):
    """Identity-bearing declaration. Names alone never identify declarations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    name: str
    kind: DeclarationKind
    scope_address: str
    status: InferenceStatus
    role: SymbolRole = SymbolRole.UNKNOWN
    arity: int | None = None
    domain_latex: str | None = None
    codomain_latex: str | None = None
    domain_ref: ExpressionRef | None = None
    source_symbol_identifier: str | None = None
    provenance: ResolutionProvenance = Field(default_factory=ResolutionProvenance)


class SymbolReference(BaseModel):
    """One identifier occurrence and its explicit identity candidates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expression_ref: ExpressionRef
    name: str
    status: ResolutionStatus
    declaration_addresses: tuple[str, ...] = ()
    lexical_scope_chain: tuple[str, ...] = ()
    provenance: ResolutionProvenance


class InstantiationOperation(BaseModel):
    """A universal parameter instantiated by an AST node in the conclusion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    step_address: str
    quantified_ref: ExpressionRef
    parameter_ref: ExpressionRef
    argument_ref: ExpressionRef | None = None
    conclusion_ref: ExpressionRef
    status: InferenceStatus = InferenceStatus.UNRESOLVED
    provenance: tuple[ResolutionProvenance, ...] = ()


class SubstitutionOperation(BaseModel):
    """Equality-directed replacement expressed only through canonical AST refs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    step_address: str
    equality_ref: ExpressionRef | None = None
    from_ref: ExpressionRef | None = None
    to_ref: ExpressionRef | None = None
    input_ref: ExpressionRef | None = None
    output_ref: ExpressionRef
    replacement_sites: tuple[ExpressionRef, ...] = ()
    status: InferenceStatus = InferenceStatus.UNRESOLVED
    provenance: tuple[ResolutionProvenance, ...] = ()


class WitnessOperation(BaseModel):
    """An existential witness recovered as an AST node from supporting evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    step_address: str
    existential_ref: ExpressionRef
    binder_ref: ExpressionRef
    witness_ref: ExpressionRef | None = None
    evidence_ref: ExpressionRef | None = None
    status: InferenceStatus = InferenceStatus.UNRESOLVED
    provenance: tuple[ResolutionProvenance, ...] = ()


class SymbolResolutionIR(BaseModel):
    """Issue-62 elaboration over explicit proof obligations and typed expressions."""

    result_identifier: str
    proof: ProofObligationIR
    scopes: list[ResolvedScope] = Field(default_factory=list)
    declarations: list[SymbolDeclaration] = Field(default_factory=list)
    references: list[SymbolReference] = Field(default_factory=list)
    instantiations: list[InstantiationOperation] = Field(default_factory=list)
    substitutions: list[SubstitutionOperation] = Field(default_factory=list)
    witnesses: list[WitnessOperation] = Field(default_factory=list)
    source_scope_complete: bool = False

    def declaration(self, address: str) -> SymbolDeclaration:
        for item in self.declarations:
            if item.address == address:
                return item
        raise KeyError(f"unknown declaration address {address!r}")

    def reference(self, ref: ExpressionRef) -> SymbolReference:
        for item in self.references:
            if item.expression_ref == ref:
                return item
        raise KeyError(f"unknown identifier reference {ref!r}")

    def expression(self, ref: ExpressionRef) -> MathExpr:
        proposition = self.proof.proposition(ref.owner_address)
        if proposition.expression is None:
            raise KeyError(f"proposition {ref.owner_address!r} has no expression")
        return expression_at_path(proposition.expression, ref.path)


class _InstantiationMatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    argument: MathExpr
    argument_path: tuple[str, ...]


class _ReplacementMatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sites: tuple[tuple[str, ...], ...]


def _source_scope_address(identifier: str) -> str:
    return f"S:source:{identifier}"


def _source_declaration_address(identifier: str) -> str:
    return f"D:source:{identifier}"


def _candidate_declaration_address(identifier: str) -> str:
    return f"D:candidate:{identifier}"


def _binder_scope_address(owner: str, binder_path: tuple[str, ...]) -> str:
    suffix = "/".join(binder_path) or "root"
    return f"S:binder:{owner}:{suffix}"


def _binder_declaration_address(owner: str, binder_path: tuple[str, ...]) -> str:
    suffix = "/".join(binder_path) or "root"
    return f"D:binder:{owner}:{suffix}"


def _root_scope_address(result_identifier: str) -> str:
    return f"S:result:{result_identifier}"


def _span_overlaps(left: SourceSpan, right: SourceSpan) -> bool:
    return (
        left.file == right.file
        and left.start_offset < right.end_offset
        and right.start_offset < left.end_offset
    )


def _owner_span(proof: ProofObligationIR, proposition: ProofProposition) -> SourceSpan | None:
    return proof.source(proposition.source_address).source_span


def expression_at_path(expression: MathExpr, path: tuple[str, ...]) -> MathExpr:
    """Resolve an issue-60 AST path without serializing or reparsing the expression."""

    current = expression
    index = 0
    while index < len(path):
        part = path[index]
        if isinstance(current, ApplyExpr):
            if part == "function":
                current = current.function
                index += 1
                continue
            if part == "arguments" and index + 1 < len(path):
                current = current.arguments[int(path[index + 1])]
                index += 2
                continue
        elif isinstance(current, (OperatorExpr, LogicalExpr)):
            if part == "arguments" and index + 1 < len(path):
                current = current.arguments[int(path[index + 1])]
                index += 2
                continue
        elif isinstance(current, RelationExpr):
            if part == "left":
                current = current.left
                index += 1
                continue
            if part == "right":
                current = current.right
                index += 1
                continue
        elif isinstance(current, NotExpr) and part == "operand":
            current = current.operand
            index += 1
            continue
        elif isinstance(current, (TupleExpr, SetExpr)):
            if part == "items" and index + 1 < len(path):
                current = current.items[int(path[index + 1])]
                index += 2
                continue
        elif isinstance(current, QuantifiedExpr):
            if part == "binder" and index + 1 < len(path):
                child = path[index + 1]
                if child == "name":
                    current = current.binder.name
                    index += 2
                    continue
                if child == "domain" and current.binder.domain is not None:
                    current = current.binder.domain
                    index += 2
                    continue
            if part == "body":
                current = current.body
                index += 1
                continue
        raise KeyError(f"invalid expression path {path!r} at component {part!r}")
    return current


def alpha_normalize_math_expr(expression: MathExpr) -> MathExpr:
    """Canonicalize bound names while leaving free identifiers untouched.

    This is deliberately only alpha normalization. It does not perform theorem
    instantiation, algebraic simplification, beta reduction, or type inference.
    """

    def normalize(item: MathExpr, environment: tuple[tuple[str, str], ...]) -> MathExpr:
        if isinstance(item, IdentifierExpr):
            for source_name, canonical_name in reversed(environment):
                if item.name == source_name:
                    return IdentifierExpr(name=canonical_name)
            return item
        if isinstance(item, (LiteralExpr, OpaqueExpr)):
            return item
        if isinstance(item, ApplyExpr):
            return ApplyExpr(
                function=normalize(item.function, environment),
                arguments=tuple(normalize(arg, environment) for arg in item.arguments),
            )
        if isinstance(item, OperatorExpr):
            return OperatorExpr(
                operator=item.operator,
                arguments=tuple(normalize(arg, environment) for arg in item.arguments),
            )
        if isinstance(item, RelationExpr):
            return RelationExpr(
                operator=item.operator,
                left=normalize(item.left, environment),
                right=normalize(item.right, environment),
            )
        if isinstance(item, LogicalExpr):
            return LogicalExpr(
                operator=item.operator,
                arguments=tuple(normalize(arg, environment) for arg in item.arguments),
            )
        if isinstance(item, NotExpr):
            return NotExpr(operand=normalize(item.operand, environment))
        if isinstance(item, TupleExpr):
            return TupleExpr(items=tuple(normalize(child, environment) for child in item.items))
        if isinstance(item, SetExpr):
            return SetExpr(items=tuple(normalize(child, environment) for child in item.items))
        if isinstance(item, QuantifiedExpr):
            canonical_name = f"@{len(environment)}"
            domain = (
                normalize(item.binder.domain, environment)
                if item.binder.domain is not None
                else None
            )
            body_environment = (*environment, (item.binder.name.name, canonical_name))
            return QuantifiedExpr(
                quantifier=item.quantifier,
                binder=Binder(name=IdentifierExpr(name=canonical_name), domain=domain),
                body=normalize(item.body, body_environment),
            )
        raise TypeError(f"unsupported expression type {type(item)!r}")

    return normalize(expression, ())


def alpha_equivalent(left: MathExpr, right: MathExpr) -> bool:
    return alpha_normalize_math_expr(left) == alpha_normalize_math_expr(right)


def _source_scopes(
    result_identifier: str,
    symbols: list[Symbol],
    candidates: list[SymbolIntroductionCandidate],
    scopes: list[Scope],
) -> list[ResolvedScope]:
    root = ResolvedScope(
        address=_root_scope_address(result_identifier),
        origin=ScopeOrigin.RESULT,
        parent_status=InferenceStatus.CONFIDENT,
    )
    if scopes:
        relevant_ids = {symbol.scope_identifier for symbol in symbols}
        relevant_ids.update(candidate.scope_identifier for candidate in candidates)
        scope_by_id = {scope.identifier: scope for scope in scopes}
        pending = list(relevant_ids)
        while pending:
            identifier = pending.pop()
            scope = scope_by_id.get(identifier)
            if scope is None or scope.parent_identifier is None:
                continue
            if scope.parent_identifier not in relevant_ids:
                relevant_ids.add(scope.parent_identifier)
                pending.append(scope.parent_identifier)

        resolved = [root]
        for identifier in sorted(relevant_ids):
            scope = scope_by_id.get(identifier)
            if scope is None:
                resolved.append(
                    ResolvedScope(
                        address=_source_scope_address(identifier),
                        origin=ScopeOrigin.SOURCE,
                        source_scope_identifier=identifier,
                    )
                )
                continue
            parent_address = (
                _source_scope_address(scope.parent_identifier)
                if scope.parent_identifier is not None
                else root.address
            )
            resolved.append(
                ResolvedScope(
                    address=_source_scope_address(identifier),
                    origin=ScopeOrigin.SOURCE,
                    parent_address=parent_address,
                    parent_status=InferenceStatus.CONFIDENT,
                    source_scope_identifier=identifier,
                    source_kind=scope.kind,
                    provenance=ResolutionProvenance(source_span=scope.source),
                )
            )
        return resolved

    identifiers = sorted(
        {
            *(symbol.scope_identifier for symbol in symbols),
            *(candidate.scope_identifier for candidate in candidates),
        }
    )
    return [
        root,
        *(
            ResolvedScope(
                address=_source_scope_address(identifier),
                origin=ScopeOrigin.SOURCE,
                source_scope_identifier=identifier,
            )
            for identifier in identifiers
        ),
    ]


def _source_declarations(
    symbols: list[Symbol],
    candidates: list[SymbolIntroductionCandidate],
) -> list[SymbolDeclaration]:
    declarations = [
        SymbolDeclaration(
            address=_source_declaration_address(symbol.identifier),
            name=symbol.name,
            kind=DeclarationKind.SOURCE,
            scope_address=_source_scope_address(symbol.scope_identifier),
            status=InferenceStatus.CONFIDENT,
            role=symbol.role,
            arity=symbol.arity,
            domain_latex=symbol.domain_latex,
            codomain_latex=symbol.codomain_latex,
            source_symbol_identifier=symbol.identifier,
            provenance=ResolutionProvenance(source_span=symbol.introduction_source),
        )
        for symbol in symbols
    ]
    declarations.extend(
        SymbolDeclaration(
            address=_candidate_declaration_address(candidate.identifier),
            name=candidate.name,
            kind=DeclarationKind.SOURCE_CANDIDATE,
            scope_address=_source_scope_address(candidate.scope_identifier),
            status=candidate.status,
            role=candidate.role,
            provenance=ResolutionProvenance(source_span=candidate.source),
        )
        for candidate in candidates
    )
    return declarations


def _matching_uses(
    *,
    name: str,
    owner_span: SourceSpan | None,
    uses: list[SymbolUse],
) -> list[SymbolUse]:
    if owner_span is None:
        return []
    return [use for use in uses if use.name == name and _span_overlaps(use.source, owner_span)]


def _resolve_free_reference(
    *,
    name: str,
    owner_span: SourceSpan | None,
    declarations: list[SymbolDeclaration],
    uses: list[SymbolUse],
) -> tuple[ResolutionStatus, tuple[str, ...]]:
    source_by_identifier = {
        item.source_symbol_identifier: item.address
        for item in declarations
        if item.source_symbol_identifier is not None
    }
    matching_uses = _matching_uses(name=name, owner_span=owner_span, uses=uses)
    if matching_uses:
        resolved_ids = {
            use.resolved_symbol_identifier
            for use in matching_uses
            if use.resolved_symbol_identifier is not None
        }
        unresolved_use = any(use.resolved_symbol_identifier is None for use in matching_uses)
        resolved_addresses = tuple(
            sorted(
                source_by_identifier[identifier]
                for identifier in resolved_ids
                if identifier in source_by_identifier
            )
        )
        if len(resolved_ids) == 1 and len(resolved_addresses) == 1 and not unresolved_use:
            return ResolutionStatus.RESOLVED, resolved_addresses
        if resolved_addresses:
            return ResolutionStatus.AMBIGUOUS, resolved_addresses
        return ResolutionStatus.UNRESOLVED, ()

    lexical_candidates = tuple(
        sorted(
            item.address
            for item in declarations
            if item.name == name and item.kind != DeclarationKind.BINDER
        )
    )
    if lexical_candidates:
        # Even one same-spelling declaration is only a candidate without an exact
        # source-use link. This is the central anti-guessing rule of issue #62.
        return ResolutionStatus.AMBIGUOUS, lexical_candidates
    return ResolutionStatus.UNRESOLVED, ()


def _resolve_expression(
    *,
    proposition: ProofProposition,
    proof: ProofObligationIR,
    declarations: list[SymbolDeclaration],
    uses: list[SymbolUse],
    scopes: list[ResolvedScope],
) -> tuple[list[SymbolDeclaration], list[SymbolReference], list[ResolvedScope]]:
    if proposition.expression is None:
        return declarations, [], scopes

    owner = proposition.address
    source = proof.source(proposition.source_address)
    owner_span = source.source_span
    references: list[SymbolReference] = []
    binder_declarations: list[SymbolDeclaration] = []
    binder_scopes: list[ResolvedScope] = []
    root_scope = _root_scope_address(proof.result_identifier)

    def visit(
        item: MathExpr,
        path: tuple[str, ...],
        environment: tuple[tuple[str, str, str], ...],
        scope_chain: tuple[str, ...],
    ) -> None:
        if isinstance(item, IdentifierExpr):
            for bound_name, declaration_address, _scope_address in reversed(environment):
                if item.name == bound_name:
                    ref = ExpressionRef(owner_address=owner, path=path)
                    references.append(
                        SymbolReference(
                            expression_ref=ref,
                            name=item.name,
                            status=ResolutionStatus.BOUND,
                            declaration_addresses=(declaration_address,),
                            lexical_scope_chain=scope_chain,
                            provenance=ResolutionProvenance(
                                source_address=proposition.source_address,
                                source_span=owner_span,
                                expression_ref=ref,
                            ),
                        )
                    )
                    return
            status, candidates = _resolve_free_reference(
                name=item.name,
                owner_span=owner_span,
                declarations=declarations,
                uses=uses,
            )
            ref = ExpressionRef(owner_address=owner, path=path)
            references.append(
                SymbolReference(
                    expression_ref=ref,
                    name=item.name,
                    status=status,
                    declaration_addresses=candidates,
                    lexical_scope_chain=scope_chain,
                    provenance=ResolutionProvenance(
                        source_address=proposition.source_address,
                        source_span=owner_span,
                        expression_ref=ref,
                    ),
                )
            )
            return
        if isinstance(item, (LiteralExpr, OpaqueExpr)):
            return
        if isinstance(item, ApplyExpr):
            visit(item.function, (*path, "function"), environment, scope_chain)
            for index, argument in enumerate(item.arguments):
                visit(
                    argument,
                    (*path, "arguments", str(index)),
                    environment,
                    scope_chain,
                )
            return
        if isinstance(item, (OperatorExpr, LogicalExpr)):
            for index, argument in enumerate(item.arguments):
                visit(
                    argument,
                    (*path, "arguments", str(index)),
                    environment,
                    scope_chain,
                )
            return
        if isinstance(item, RelationExpr):
            visit(item.left, (*path, "left"), environment, scope_chain)
            visit(item.right, (*path, "right"), environment, scope_chain)
            return
        if isinstance(item, NotExpr):
            visit(item.operand, (*path, "operand"), environment, scope_chain)
            return
        if isinstance(item, (TupleExpr, SetExpr)):
            for index, child in enumerate(item.items):
                visit(child, (*path, "items", str(index)), environment, scope_chain)
            return
        if isinstance(item, QuantifiedExpr):
            binder_path = (*path, "binder", "name")
            domain_path = (*path, "binder", "domain")
            if item.binder.domain is not None:
                visit(item.binder.domain, domain_path, environment, scope_chain)
            scope_address = _binder_scope_address(owner, binder_path)
            declaration_address = _binder_declaration_address(owner, binder_path)
            parent_address = scope_chain[0] if scope_chain else root_scope
            binder_scopes.append(
                ResolvedScope(
                    address=scope_address,
                    origin=ScopeOrigin.BINDER,
                    parent_address=parent_address,
                    parent_status=InferenceStatus.CONFIDENT,
                    provenance=ResolutionProvenance(
                        source_address=proposition.source_address,
                        source_span=owner_span,
                        expression_ref=ExpressionRef(owner_address=owner, path=binder_path),
                    ),
                )
            )
            binder_declarations.append(
                SymbolDeclaration(
                    address=declaration_address,
                    name=item.binder.name.name,
                    kind=DeclarationKind.BINDER,
                    scope_address=scope_address,
                    status=InferenceStatus.CONFIDENT,
                    domain_ref=(
                        ExpressionRef(owner_address=owner, path=domain_path)
                        if item.binder.domain is not None
                        else None
                    ),
                    provenance=ResolutionProvenance(
                        source_address=proposition.source_address,
                        source_span=owner_span,
                        expression_ref=ExpressionRef(owner_address=owner, path=binder_path),
                    ),
                )
            )
            visit(
                item.body,
                (*path, "body"),
                (*environment, (item.binder.name.name, declaration_address, scope_address)),
                (scope_address, *scope_chain),
            )
            return
        raise TypeError(f"unsupported expression type {type(item)!r}")

    visit(proposition.expression, (), (), ())
    return (
        [*declarations, *binder_declarations],
        references,
        [*scopes, *binder_scopes],
    )


def _match_instantiation(
    pattern: MathExpr,
    target: MathExpr,
    *,
    binder_name: str,
    pattern_path: tuple[str, ...] = (),
    target_path: tuple[str, ...] = (),
) -> _InstantiationMatch | None:
    arguments: list[tuple[MathExpr, tuple[str, ...]]] = []

    def match(
        left: MathExpr,
        right: MathExpr,
        left_path: tuple[str, ...],
        right_path: tuple[str, ...],
    ) -> bool:
        if isinstance(left, IdentifierExpr) and left.name == binder_name:
            arguments.append((right, right_path))
            return True
        if type(left) is not type(right):
            return False
        if isinstance(left, IdentifierExpr) and isinstance(right, IdentifierExpr):
            return left == right
        if isinstance(left, LiteralExpr) and isinstance(right, LiteralExpr):
            return left == right
        if isinstance(left, OpaqueExpr) and isinstance(right, OpaqueExpr):
            return left == right
        if isinstance(left, ApplyExpr) and isinstance(right, ApplyExpr):
            return (
                match(
                    left.function,
                    right.function,
                    (*left_path, "function"),
                    (*right_path, "function"),
                )
                and len(left.arguments) == len(right.arguments)
                and all(
                    match(
                        l_arg,
                        r_arg,
                        (*left_path, "arguments", str(index)),
                        (*right_path, "arguments", str(index)),
                    )
                    for index, (l_arg, r_arg) in enumerate(
                        zip(left.arguments, right.arguments, strict=True)
                    )
                )
            )
        if isinstance(left, OperatorExpr) and isinstance(right, OperatorExpr):
            return (
                left.operator == right.operator
                and len(left.arguments) == len(right.arguments)
                and all(
                    match(
                        l_arg,
                        r_arg,
                        (*left_path, "arguments", str(index)),
                        (*right_path, "arguments", str(index)),
                    )
                    for index, (l_arg, r_arg) in enumerate(
                        zip(left.arguments, right.arguments, strict=True)
                    )
                )
            )
        if isinstance(left, RelationExpr) and isinstance(right, RelationExpr):
            return (
                left.operator == right.operator
                and match(left.left, right.left, (*left_path, "left"), (*right_path, "left"))
                and match(left.right, right.right, (*left_path, "right"), (*right_path, "right"))
            )
        if isinstance(left, LogicalExpr) and isinstance(right, LogicalExpr):
            return (
                left.operator == right.operator
                and len(left.arguments) == len(right.arguments)
                and all(
                    match(
                        l_arg,
                        r_arg,
                        (*left_path, "arguments", str(index)),
                        (*right_path, "arguments", str(index)),
                    )
                    for index, (l_arg, r_arg) in enumerate(
                        zip(left.arguments, right.arguments, strict=True)
                    )
                )
            )
        if isinstance(left, NotExpr) and isinstance(right, NotExpr):
            return match(
                left.operand, right.operand, (*left_path, "operand"), (*right_path, "operand")
            )
        if isinstance(left, TupleExpr) and isinstance(right, TupleExpr):
            return len(left.items) == len(right.items) and all(
                match(
                    l_item,
                    r_item,
                    (*left_path, "items", str(index)),
                    (*right_path, "items", str(index)),
                )
                for index, (l_item, r_item) in enumerate(zip(left.items, right.items, strict=True))
            )
        if isinstance(left, SetExpr) and isinstance(right, SetExpr):
            return len(left.items) == len(right.items) and all(
                match(
                    l_item,
                    r_item,
                    (*left_path, "items", str(index)),
                    (*right_path, "items", str(index)),
                )
                for index, (l_item, r_item) in enumerate(zip(left.items, right.items, strict=True))
            )
        # Nested binders require declaration-aware matching. Preserve uncertainty
        # instead of doing lexical substitution through a possible shadowing point.
        if isinstance(left, QuantifiedExpr) and isinstance(right, QuantifiedExpr):
            return False
        return left == right

    if not match(pattern, target, pattern_path, target_path) or not arguments:
        return None
    first_argument, first_path = arguments[0]
    if any(argument != first_argument for argument, _path in arguments[1:]):
        return None
    return _InstantiationMatch(argument=first_argument, argument_path=first_path)


def _match_exact_replacement(
    source: MathExpr,
    target: MathExpr,
    *,
    old: MathExpr,
    new: MathExpr,
    source_path: tuple[str, ...] = (),
    target_path: tuple[str, ...] = (),
) -> _ReplacementMatch | None:
    sites: list[tuple[str, ...]] = []

    def match(
        left: MathExpr,
        right: MathExpr,
        left_path: tuple[str, ...],
        right_path: tuple[str, ...],
    ) -> bool:
        if left == old and right == new:
            sites.append(right_path)
            return True
        if left == right:
            return True
        if type(left) is not type(right):
            return False
        if isinstance(left, ApplyExpr) and isinstance(right, ApplyExpr):
            return (
                match(
                    left.function,
                    right.function,
                    (*left_path, "function"),
                    (*right_path, "function"),
                )
                and len(left.arguments) == len(right.arguments)
                and all(
                    match(
                        l_arg,
                        r_arg,
                        (*left_path, "arguments", str(index)),
                        (*right_path, "arguments", str(index)),
                    )
                    for index, (l_arg, r_arg) in enumerate(
                        zip(left.arguments, right.arguments, strict=True)
                    )
                )
            )
        if isinstance(left, OperatorExpr) and isinstance(right, OperatorExpr):
            return (
                left.operator == right.operator
                and len(left.arguments) == len(right.arguments)
                and all(
                    match(
                        l_arg,
                        r_arg,
                        (*left_path, "arguments", str(index)),
                        (*right_path, "arguments", str(index)),
                    )
                    for index, (l_arg, r_arg) in enumerate(
                        zip(left.arguments, right.arguments, strict=True)
                    )
                )
            )
        if isinstance(left, RelationExpr) and isinstance(right, RelationExpr):
            return (
                left.operator == right.operator
                and match(left.left, right.left, (*left_path, "left"), (*right_path, "left"))
                and match(left.right, right.right, (*left_path, "right"), (*right_path, "right"))
            )
        if isinstance(left, LogicalExpr) and isinstance(right, LogicalExpr):
            return (
                left.operator == right.operator
                and len(left.arguments) == len(right.arguments)
                and all(
                    match(
                        l_arg,
                        r_arg,
                        (*left_path, "arguments", str(index)),
                        (*right_path, "arguments", str(index)),
                    )
                    for index, (l_arg, r_arg) in enumerate(
                        zip(left.arguments, right.arguments, strict=True)
                    )
                )
            )
        if isinstance(left, NotExpr) and isinstance(right, NotExpr):
            return match(
                left.operand, right.operand, (*left_path, "operand"), (*right_path, "operand")
            )
        if isinstance(left, TupleExpr) and isinstance(right, TupleExpr):
            return len(left.items) == len(right.items) and all(
                match(
                    l_item,
                    r_item,
                    (*left_path, "items", str(index)),
                    (*right_path, "items", str(index)),
                )
                for index, (l_item, r_item) in enumerate(zip(left.items, right.items, strict=True))
            )
        if isinstance(left, SetExpr) and isinstance(right, SetExpr):
            return len(left.items) == len(right.items) and all(
                match(
                    l_item,
                    r_item,
                    (*left_path, "items", str(index)),
                    (*right_path, "items", str(index)),
                )
                for index, (l_item, r_item) in enumerate(zip(left.items, right.items, strict=True))
            )
        if isinstance(left, QuantifiedExpr) and isinstance(right, QuantifiedExpr):
            return False
        return False

    if not match(source, target, source_path, target_path) or not sites:
        return None
    return _ReplacementMatch(sites=tuple(sites))


def _provenance_for_ref(proof: ProofObligationIR, ref: ExpressionRef) -> ResolutionProvenance:
    proposition = proof.proposition(ref.owner_address)
    source = proof.source(proposition.source_address)
    return ResolutionProvenance(
        source_address=proposition.source_address,
        source_span=source.source_span,
        expression_ref=ref,
    )


def _instantiation_operations(proof: ProofObligationIR) -> list[InstantiationOperation]:
    operations: list[InstantiationOperation] = []
    for step in proof.steps:
        if step.conclusion not in {item.address for item in proof.propositions}:
            continue
        conclusion = proof.proposition(step.conclusion)
        if conclusion.expression is None:
            continue
        for premise_address in step.premises:
            try:
                premise = proof.proposition(premise_address)
            except KeyError:
                continue
            expression = premise.expression
            if (
                not isinstance(expression, QuantifiedExpr)
                or expression.quantifier != Quantifier.FOR_ALL
            ):
                continue
            match = _match_instantiation(
                expression.body,
                conclusion.expression,
                binder_name=expression.binder.name.name,
                pattern_path=("body",),
            )
            quantified_ref = ExpressionRef(owner_address=premise.address)
            parameter_ref = ExpressionRef(
                owner_address=premise.address,
                path=("binder", "name"),
            )
            conclusion_ref = ExpressionRef(owner_address=conclusion.address)
            argument_ref = (
                ExpressionRef(owner_address=conclusion.address, path=match.argument_path)
                if match is not None
                else None
            )
            status = (
                step.status
                if match is not None and step.status == InferenceStatus.CONFIDENT
                else InferenceStatus.UNRESOLVED
            )
            if match is None and step.rule not in {
                ProofRuleKind.INSTANTIATE,
                ProofRuleKind.APPLY_RESULT,
            }:
                continue
            operations.append(
                InstantiationOperation(
                    address=f"I{len(operations) + 1}",
                    step_address=step.address,
                    quantified_ref=quantified_ref,
                    parameter_ref=parameter_ref,
                    argument_ref=argument_ref,
                    conclusion_ref=conclusion_ref,
                    status=status,
                    provenance=(
                        _provenance_for_ref(proof, quantified_ref),
                        _provenance_for_ref(proof, conclusion_ref),
                    ),
                )
            )
    return operations


def _witness_operations(proof: ProofObligationIR) -> list[WitnessOperation]:
    operations: list[WitnessOperation] = []
    for step in proof.steps:
        try:
            conclusion = proof.proposition(step.conclusion)
        except KeyError:
            continue
        expression = conclusion.expression
        if not isinstance(expression, QuantifiedExpr) or expression.quantifier != Quantifier.EXISTS:
            continue
        existential_ref = ExpressionRef(owner_address=conclusion.address)
        binder_ref = ExpressionRef(
            owner_address=conclusion.address,
            path=("binder", "name"),
        )
        matches: list[tuple[str, _InstantiationMatch]] = []
        for premise_address in step.premises:
            try:
                premise = proof.proposition(premise_address)
            except KeyError:
                continue
            if premise.expression is None:
                continue
            match = _match_instantiation(
                expression.body,
                premise.expression,
                binder_name=expression.binder.name.name,
                pattern_path=("body",),
            )
            if match is not None:
                matches.append((premise.address, match))
        if len(matches) == 1:
            premise_address, match = matches[0]
            witness_ref = ExpressionRef(
                owner_address=premise_address,
                path=match.argument_path,
            )
            evidence_ref = ExpressionRef(owner_address=premise_address)
            status = (
                step.status
                if step.status == InferenceStatus.CONFIDENT
                else InferenceStatus.UNRESOLVED
            )
        else:
            witness_ref = None
            evidence_ref = None
            status = InferenceStatus.UNRESOLVED
            if step.rule != ProofRuleKind.WITNESS_INTRODUCTION:
                continue
        operations.append(
            WitnessOperation(
                address=f"W{len(operations) + 1}",
                step_address=step.address,
                existential_ref=existential_ref,
                binder_ref=binder_ref,
                witness_ref=witness_ref,
                evidence_ref=evidence_ref,
                status=status,
                provenance=(_provenance_for_ref(proof, existential_ref),),
            )
        )
    return operations


def _substitution_operations(proof: ProofObligationIR) -> list[SubstitutionOperation]:
    operations: list[SubstitutionOperation] = []
    for step in proof.steps:
        if step.rule != ProofRuleKind.REWRITE_SUBSTITUTION:
            continue
        try:
            conclusion = proof.proposition(step.conclusion)
        except KeyError:
            continue
        output_ref = ExpressionRef(owner_address=conclusion.address)
        equality_premises: list[tuple[str, RelationExpr]] = []
        input_premises: list[ProofProposition] = []
        for premise_address in step.premises:
            try:
                premise = proof.proposition(premise_address)
            except KeyError:
                continue
            if (
                isinstance(premise.expression, RelationExpr)
                and premise.expression.operator == RelationOperator.EQUAL
            ):
                equality_premises.append((premise.address, premise.expression))
            elif premise.expression is not None:
                input_premises.append(premise)

        confident_match: (
            tuple[
                str,
                RelationExpr,
                ProofProposition,
                bool,
                _ReplacementMatch,
            ]
            | None
        ) = None
        matches: list[tuple[str, RelationExpr, ProofProposition, bool, _ReplacementMatch]] = []
        if conclusion.expression is not None:
            for equality_address, equality in equality_premises:
                for input_proposition in input_premises:
                    input_expression = input_proposition.expression
                    if input_expression is None:
                        continue
                    for reverse in (False, True):
                        old = equality.right if reverse else equality.left
                        new = equality.left if reverse else equality.right
                        replacement = _match_exact_replacement(
                            input_expression,
                            conclusion.expression,
                            old=old,
                            new=new,
                        )
                        if replacement is not None:
                            matches.append(
                                (
                                    equality_address,
                                    equality,
                                    input_proposition,
                                    reverse,
                                    replacement,
                                )
                            )
        if len(matches) == 1:
            confident_match = matches[0]

        if confident_match is None:
            operations.append(
                SubstitutionOperation(
                    address=f"U{len(operations) + 1}",
                    step_address=step.address,
                    output_ref=output_ref,
                    status=(
                        InferenceStatus.AMBIGUOUS
                        if len(matches) > 1
                        else InferenceStatus.UNRESOLVED
                    ),
                    provenance=(_provenance_for_ref(proof, output_ref),),
                )
            )
            continue

        equality_address, _equality, input_proposition, reverse, replacement = confident_match
        equality_ref = ExpressionRef(owner_address=equality_address)
        from_ref = ExpressionRef(
            owner_address=equality_address,
            path=(("right",) if reverse else ("left",)),
        )
        to_ref = ExpressionRef(
            owner_address=equality_address,
            path=(("left",) if reverse else ("right",)),
        )
        input_ref = ExpressionRef(owner_address=input_proposition.address)
        sites = tuple(
            ExpressionRef(owner_address=conclusion.address, path=site) for site in replacement.sites
        )
        operations.append(
            SubstitutionOperation(
                address=f"U{len(operations) + 1}",
                step_address=step.address,
                equality_ref=equality_ref,
                from_ref=from_ref,
                to_ref=to_ref,
                input_ref=input_ref,
                output_ref=output_ref,
                replacement_sites=sites,
                status=(
                    step.status
                    if step.status == InferenceStatus.CONFIDENT
                    else InferenceStatus.UNRESOLVED
                ),
                provenance=(
                    _provenance_for_ref(proof, equality_ref),
                    _provenance_for_ref(proof, input_ref),
                    _provenance_for_ref(proof, output_ref),
                ),
            )
        )
    return operations


def elaborate_symbol_resolution(
    proof: ProofObligationIR,
    *,
    symbols: list[Symbol] | None = None,
    symbol_candidates: list[SymbolIntroductionCandidate] | None = None,
    symbol_uses: list[SymbolUse] | None = None,
    scopes: list[Scope] | None = None,
) -> SymbolResolutionIR:
    """Resolve identities and proof operations without mutating lower IR layers."""

    symbols = list(symbols or [])
    symbol_candidates = list(symbol_candidates or [])
    symbol_uses = list(symbol_uses or [])
    scopes = list(scopes or [])

    resolved_scopes = _source_scopes(
        proof.result_identifier,
        symbols,
        symbol_candidates,
        scopes,
    )
    declarations = _source_declarations(symbols, symbol_candidates)
    references: list[SymbolReference] = []
    for proposition in proof.propositions:
        declarations, proposition_references, resolved_scopes = _resolve_expression(
            proposition=proposition,
            proof=proof,
            declarations=declarations,
            uses=symbol_uses,
            scopes=resolved_scopes,
        )
        references.extend(proposition_references)

    # Deduplicate immutable scope/declaration side tables by stable identity while
    # preserving deterministic first occurrence order.
    scope_by_address = {item.address: item for item in resolved_scopes}
    declaration_by_address = {item.address: item for item in declarations}

    return SymbolResolutionIR(
        result_identifier=proof.result_identifier,
        proof=proof.model_copy(deep=True),
        scopes=[scope_by_address[key] for key in sorted(scope_by_address)],
        declarations=[declaration_by_address[key] for key in sorted(declaration_by_address)],
        references=references,
        instantiations=_instantiation_operations(proof),
        substitutions=_substitution_operations(proof),
        witnesses=_witness_operations(proof),
        source_scope_complete=bool(scopes),
    )


def _relevant_symbol_table_context(
    proof: ProofObligationIR,
    request: SemanticReviewRequest,
    symbol_table: SymbolTable | None,
) -> tuple[list[Symbol], list[SymbolIntroductionCandidate], list[SymbolUse], list[Scope]]:
    symbols = list(request.item.symbols)
    candidates = list(request.item.symbol_candidates)
    if symbol_table is None:
        return symbols, candidates, [], []

    owner_spans = [source.source_span for source in proof.sources if source.source_span is not None]
    uses = [
        use
        for use in symbol_table.uses
        if any(_span_overlaps(use.source, owner_span) for owner_span in owner_spans)
    ]
    selected_symbol_ids = {symbol.identifier for symbol in symbols}
    selected_symbol_ids.update(
        use.resolved_symbol_identifier for use in uses if use.resolved_symbol_identifier is not None
    )
    selected_symbols = [
        symbol for symbol in symbol_table.symbols if symbol.identifier in selected_symbol_ids
    ]
    selected_by_id = {symbol.identifier: symbol for symbol in selected_symbols}
    for symbol in symbols:
        selected_by_id.setdefault(symbol.identifier, symbol)

    scope_ids = {symbol.scope_identifier for symbol in selected_by_id.values()}
    scope_ids.update(use.scope_identifier for use in uses)
    scope_by_id = {scope.identifier: scope for scope in symbol_table.scopes}
    pending = list(scope_ids)
    while pending:
        identifier = pending.pop()
        scope = scope_by_id.get(identifier)
        if scope is None or scope.parent_identifier is None:
            continue
        if scope.parent_identifier not in scope_ids:
            scope_ids.add(scope.parent_identifier)
            pending.append(scope.parent_identifier)
    selected_scopes = [scope for scope in symbol_table.scopes if scope.identifier in scope_ids]
    return (
        sorted(selected_by_id.values(), key=lambda item: item.identifier),
        candidates,
        uses,
        selected_scopes,
    )


def build_symbol_resolution_ir(
    unit: TheoremUnit,
    request: SemanticReviewRequest,
    *,
    symbol_table: SymbolTable | None = None,
) -> SymbolResolutionIR:
    """Build issue-62 IR from the established typed-obligation path.

    Passing the Thorn source ``SymbolTable`` enables exact source-use identity and
    scope-parent recovery. Without it, lexical binders are still exact, while
    source-level same-spelling declarations remain explicit ambiguity candidates.
    """

    proof = build_proof_obligation_ir(unit, request)
    symbols, candidates, uses, scopes = _relevant_symbol_table_context(
        proof,
        request,
        symbol_table,
    )
    return elaborate_symbol_resolution(
        proof,
        symbols=symbols,
        symbol_candidates=candidates,
        symbol_uses=uses,
        scopes=scopes,
    )
