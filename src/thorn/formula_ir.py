from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field


class ExprLoweringStatus(StrEnum):
    """How completely Thorn mechanically lowered a mathematical payload."""

    FULL = "full"
    PARTIAL = "partial"
    OPAQUE = "opaque"


class RelationOperator(StrEnum):
    EQUAL = "="
    NOT_EQUAL = "≠"
    LESS_THAN = "<"
    LESS_EQUAL = "≤"
    GREATER_THAN = ">"
    GREATER_EQUAL = "≥"
    MEMBER = "∈"
    NOT_MEMBER = "∉"
    SUBSET = "⊂"
    SUBSET_EQUAL = "⊆"


class LogicalOperator(StrEnum):
    AND = "∧"
    OR = "∨"
    IMPLIES = "⇒"
    IFF = "⇔"


class Quantifier(StrEnum):
    FOR_ALL = "∀"
    EXISTS = "∃"


class _ExprModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class IdentifierExpr(_ExprModel):
    kind: Literal["identifier"] = "identifier"
    name: str


class LiteralExpr(_ExprModel):
    kind: Literal["literal"] = "literal"
    value: str


class OpaqueExpr(_ExprModel):
    """A mathematical fragment Thorn intentionally did not guess how to lower."""

    kind: Literal["opaque"] = "opaque"
    text: str
    reason: str = "unsupported_syntax"


class ApplyExpr(_ExprModel):
    kind: Literal["apply"] = "apply"
    function: MathExpr
    arguments: tuple[MathExpr, ...]


class OperatorExpr(_ExprModel):
    kind: Literal["operator"] = "operator"
    operator: str
    arguments: tuple[MathExpr, ...]


class RelationExpr(_ExprModel):
    kind: Literal["relation"] = "relation"
    operator: RelationOperator
    left: MathExpr
    right: MathExpr


class LogicalExpr(_ExprModel):
    kind: Literal["logical"] = "logical"
    operator: LogicalOperator
    arguments: tuple[MathExpr, ...]


class NotExpr(_ExprModel):
    kind: Literal["not"] = "not"
    operand: MathExpr


class TupleExpr(_ExprModel):
    kind: Literal["tuple"] = "tuple"
    items: tuple[MathExpr, ...]


class SetExpr(_ExprModel):
    kind: Literal["set"] = "set"
    items: tuple[MathExpr, ...]


class Binder(_ExprModel):
    name: IdentifierExpr
    domain: MathExpr | None = None


class QuantifiedExpr(_ExprModel):
    kind: Literal["quantified"] = "quantified"
    quantifier: Quantifier
    binder: Binder
    body: MathExpr


MathExpr: TypeAlias = Annotated[
    IdentifierExpr
    | LiteralExpr
    | OpaqueExpr
    | ApplyExpr
    | OperatorExpr
    | RelationExpr
    | LogicalExpr
    | NotExpr
    | TupleExpr
    | SetExpr
    | QuantifiedExpr,
    Field(discriminator="kind"),
]

for _model in (
    ApplyExpr,
    OperatorExpr,
    RelationExpr,
    LogicalExpr,
    NotExpr,
    TupleExpr,
    SetExpr,
    Binder,
    QuantifiedExpr,
):
    _model.model_rebuild(_types_namespace={"MathExpr": MathExpr})


class ExpressionLowering(BaseModel):
    """A canonical expression plus an explicit completeness judgement."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expression: MathExpr
    status: ExprLoweringStatus
    source_text: str


_MATH_DELIMITER_RE = re.compile(
    r"(?s)(\$\$.*?\$\$|\\\[.*?\\\]|\\\(.*?\\\)|(?<!\$)\$(?!\$).*?(?<!\\)\$)"
)
_LABEL_RE = re.compile(r"\\label\s*\{[^{}]*\}")
_COMMAND_WITH_TEXT_RE = re.compile(r"\\(?:mathrm|operatorname)\s*\{([^{}]+)\}")

_LATEX_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\\mathbb\s*\{R\}", "R"),
    (r"\\mathbb\s*\{N\}", "N"),
    (r"\\mathbb\s*\{Z\}", "Z"),
    (r"\\mathbb\s*\{Q\}", "Q"),
    (r"\\mathbb\s*\{C\}", "C"),
    (r"\\Leftrightarrow(?![A-Za-z])", "⇔"),
    (r"\\Longleftrightarrow(?![A-Za-z])", "⇔"),
    (r"\\Rightarrow(?![A-Za-z])", "⇒"),
    (r"\\Longrightarrow(?![A-Za-z])", "⇒"),
    (r"\\implies(?![A-Za-z])", "⇒"),
    (r"\\iff(?![A-Za-z])", "⇔"),
    (r"\\wedge(?![A-Za-z])", "∧"),
    (r"\\land(?![A-Za-z])", "∧"),
    (r"\\vee(?![A-Za-z])", "∨"),
    (r"\\lor(?![A-Za-z])", "∨"),
    (r"\\lnot(?![A-Za-z])", "¬"),
    (r"\\neg(?![A-Za-z])", "¬"),
    (r"\\notin(?![A-Za-z])", "∉"),
    (r"\\in(?![A-Za-z])", "∈"),
    (r"\\neq(?![A-Za-z])", "≠"),
    (r"\\ne(?![A-Za-z])", "≠"),
    (r"\\leq(?![A-Za-z])", "≤"),
    (r"\\le(?![A-Za-z])", "≤"),
    (r"\\geq(?![A-Za-z])", "≥"),
    (r"\\ge(?![A-Za-z])", "≥"),
    (r"\\subseteq(?![A-Za-z])", "⊆"),
    (r"\\subset(?![A-Za-z])", "⊂"),
    (r"\\forall(?![A-Za-z])", "∀"),
    (r"\\exists(?![A-Za-z])", "∃"),
    (r"\\cdot(?![A-Za-z])", "*"),
    (r"\\times(?![A-Za-z])", "*"),
)

_SIMPLE_COMMANDS: tuple[str, ...] = ("sin", "cos", "tan", "exp", "log", "ln", "det")
_DOMAIN_WORDS: dict[str, str] = {
    "real": "R",
    "reals": "R",
    "integer": "Z",
    "integers": "Z",
    "natural": "N",
    "naturals": "N",
}


def _strip_math_delimiters(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("$$") and stripped.endswith("$$"):
        return stripped[2:-2]
    if stripped.startswith("\\[") and stripped.endswith("\\]"):
        return stripped[2:-2]
    if stripped.startswith("\\(") and stripped.endswith("\\)"):
        return stripped[2:-2]
    if stripped.startswith("$") and stripped.endswith("$"):
        return stripped[1:-1]
    return stripped


def normalize_formula_source(text: str) -> str:
    """Normalize syntax spellings only; do not invent mathematical structure."""

    value = _LABEL_RE.sub("", text).replace("~", " ")

    def unwrap_math(match: re.Match[str]) -> str:
        return _strip_math_delimiters(match.group(0))

    value = _MATH_DELIMITER_RE.sub(unwrap_math, value)
    value = _COMMAND_WITH_TEXT_RE.sub(r"\1", value)
    value = value.replace(r"\left", "").replace(r"\right", "")
    for command in _SIMPLE_COMMANDS:
        value = re.sub(rf"\\{command}(?![A-Za-z])", command, value)
    for pattern, replacement in _LATEX_REPLACEMENTS:
        value = re.sub(pattern, replacement, value)
    value = re.sub(r"\\(?:,|;|!|quad|qquad)(?![A-Za-z])", " ", value)
    value = " ".join(value.strip().split())
    return value.rstrip(". ;")


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    text: str
    start: int
    end: int


_TOKEN_RE = re.compile(
    r"(?P<SPACE>\s+)"
    r"|(?P<NUMBER>\d+(?:\.\d+)?)"
    r"|(?P<OP>⇔|⇒|≤|≥|≠|∉|⊆|⊂|∈|=|<|>|¬|∧|∨|\+|-|\*|/|\^)"
    r"|(?P<PUNCT>[(){}\[\],:])"
    r"|(?P<IDENT>[^\W\d]\w*)",
    flags=re.UNICODE,
)


class _ParseError(ValueError):
    pass


def _tokens(text: str) -> list[_Token]:
    result: list[_Token] = []
    position = 0
    while position < len(text):
        match = _TOKEN_RE.match(text, position)
        if match is None:
            raise _ParseError(f"unsupported token at offset {position}")
        kind = match.lastgroup
        assert kind is not None
        if kind != "SPACE":
            result.append(
                _Token(
                    kind=kind,
                    text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                )
            )
        position = match.end()
    return result


_RELATIONS: dict[str, RelationOperator] = {
    "=": RelationOperator.EQUAL,
    "≠": RelationOperator.NOT_EQUAL,
    "<": RelationOperator.LESS_THAN,
    "≤": RelationOperator.LESS_EQUAL,
    ">": RelationOperator.GREATER_THAN,
    "≥": RelationOperator.GREATER_EQUAL,
    "∈": RelationOperator.MEMBER,
    "∉": RelationOperator.NOT_MEMBER,
    "⊂": RelationOperator.SUBSET,
    "⊆": RelationOperator.SUBSET_EQUAL,
}
_LOGICAL: dict[str, LogicalOperator] = {
    "∧": LogicalOperator.AND,
    "∨": LogicalOperator.OR,
    "⇒": LogicalOperator.IMPLIES,
    "⇔": LogicalOperator.IFF,
}
_PRECEDENCE: dict[str, int] = {
    "⇔": 1,
    "⇒": 2,
    "∨": 3,
    "∧": 4,
    **{operator: 5 for operator in _RELATIONS},
    "+": 6,
    "-": 6,
    "*": 7,
    "/": 7,
    "^": 8,
}
_RIGHT_ASSOCIATIVE = {"⇒", "^"}


class _Parser:
    def __init__(self, text: str) -> None:
        self.tokens = _tokens(text)
        self.index = 0

    def parse(self) -> MathExpr:
        if not self.tokens:
            raise _ParseError("empty expression")
        expression = self._expression(0)
        if self.index != len(self.tokens):
            raise _ParseError(f"unconsumed token {self.tokens[self.index].text!r}")
        return expression

    def _peek(self) -> _Token | None:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def _take(self) -> _Token:
        token = self._peek()
        if token is None:
            raise _ParseError("unexpected end of expression")
        self.index += 1
        return token

    def _accept(self, text: str) -> bool:
        token = self._peek()
        if token is None or token.text != text:
            return False
        self.index += 1
        return True

    def _expect(self, text: str) -> None:
        if not self._accept(text):
            raise _ParseError(f"expected {text!r}")

    def _expression(self, minimum_precedence: int) -> MathExpr:
        left = self._unary()
        while True:
            token = self._peek()
            if token is None or token.text not in _PRECEDENCE:
                break
            precedence = _PRECEDENCE[token.text]
            if precedence < minimum_precedence:
                break
            operator = self._take().text
            if operator in _RELATIONS and isinstance(left, RelationExpr):
                raise _ParseError("chained relations are not lowered")
            next_minimum = (
                precedence if operator in _RIGHT_ASSOCIATIVE else precedence + 1
            )
            right = self._expression(next_minimum)
            left = _combine(operator, left, right)
        return left

    def _unary(self) -> MathExpr:
        if self._accept("¬"):
            return NotExpr(operand=self._unary())
        if self._accept("-"):
            return OperatorExpr(operator="-", arguments=(self._unary(),))
        expression = self._primary()
        while self._accept("("):
            arguments: list[MathExpr] = []
            if not self._accept(")"):
                while True:
                    arguments.append(self._expression(0))
                    if self._accept(")"):
                        break
                    self._expect(",")
            expression = ApplyExpr(function=expression, arguments=tuple(arguments))
        return expression

    def _primary(self) -> MathExpr:
        token = self._take()
        if token.kind == "NUMBER":
            return LiteralExpr(value=token.text)
        if token.kind == "IDENT":
            return IdentifierExpr(name=token.text)
        if token.text == "(":
            first = self._expression(0)
            if self._accept(","):
                tuple_items = [first]
                while True:
                    tuple_items.append(self._expression(0))
                    if self._accept(")"):
                        break
                    self._expect(",")
                return TupleExpr(items=tuple(tuple_items))
            self._expect(")")
            return first
        if token.text == "{":
            set_items: list[MathExpr] = []
            if not self._accept("}"):
                while True:
                    set_items.append(self._expression(0))
                    if self._accept("}"):
                        break
                    self._expect(",")
            return SetExpr(items=tuple(set_items))
        raise _ParseError(f"unexpected token {token.text!r}")


def _combine(operator: str, left: MathExpr, right: MathExpr) -> MathExpr:
    relation = _RELATIONS.get(operator)
    if relation is not None:
        return RelationExpr(operator=relation, left=left, right=right)
    logical = _LOGICAL.get(operator)
    if logical is not None:
        if logical in {LogicalOperator.AND, LogicalOperator.OR}:
            arguments: list[MathExpr] = []
            if isinstance(left, LogicalExpr) and left.operator == logical:
                arguments.extend(left.arguments)
            else:
                arguments.append(left)
            if isinstance(right, LogicalExpr) and right.operator == logical:
                arguments.extend(right.arguments)
            else:
                arguments.append(right)
            return LogicalExpr(operator=logical, arguments=tuple(arguments))
        return LogicalExpr(operator=logical, arguments=(left, right))
    return OperatorExpr(operator=operator, arguments=(left, right))


def _top_level_word_split(
    text: str,
    phrases: tuple[str, ...],
) -> tuple[str, str, str] | None:
    lower = text.lower()
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char in "({[":
            depth += 1
        elif char in ")}]":
            depth = max(0, depth - 1)
        if depth == 0:
            for phrase in phrases:
                if not lower.startswith(phrase, index):
                    continue
                before_ok = index == 0 or not lower[index - 1].isalnum()
                after = index + len(phrase)
                after_ok = after == len(text) or not lower[after].isalnum()
                if before_ok and after_ok:
                    left = text[:index].strip(" ,")
                    right = text[after:].strip(" ,")
                    if left and right:
                        return left, phrase, right
        index += 1
    return None


def _lower_recursive(text: str) -> MathExpr:
    value = text.strip().rstrip(". ;")
    if not value:
        raise _ParseError("empty expression")

    quantifier = _lower_quantifier(value)
    if quantifier is not None:
        return quantifier

    if value.lower().startswith("if "):
        split = _top_level_word_split(value[3:].strip(), ("then",))
        if split is not None:
            antecedent, _, consequent = split
            return LogicalExpr(
                operator=LogicalOperator.IMPLIES,
                arguments=(_lower_or_opaque(antecedent), _lower_or_opaque(consequent)),
            )

    word_operators: tuple[tuple[tuple[str, ...], LogicalOperator], ...] = (
        (("if and only if", "iff"), LogicalOperator.IFF),
        (("implies",), LogicalOperator.IMPLIES),
        (("or",), LogicalOperator.OR),
        (("and",), LogicalOperator.AND),
    )
    for phrases, logical_operator in word_operators:
        split = _top_level_word_split(value, phrases)
        if split is None:
            continue
        left, _, right = split
        return _combine(
            logical_operator.value,
            _lower_or_opaque(left),
            _lower_or_opaque(right),
        )

    relation_phrases: tuple[tuple[tuple[str, ...], RelationOperator], ...] = (
        (("is less than or equal to", "is at most"), RelationOperator.LESS_EQUAL),
        (("is greater than or equal to", "is at least"), RelationOperator.GREATER_EQUAL),
        (("is a proper subset of",), RelationOperator.SUBSET),
        (("is a subset of",), RelationOperator.SUBSET_EQUAL),
        (("is not equal to", "does not equal"), RelationOperator.NOT_EQUAL),
        (("is equal to", "equals"), RelationOperator.EQUAL),
        (("does not belong to", "is not in"), RelationOperator.NOT_MEMBER),
        (("belongs to", "is in"), RelationOperator.MEMBER),
        (("is less than",), RelationOperator.LESS_THAN),
        (("is greater than",), RelationOperator.GREATER_THAN),
    )
    for phrases, relation_operator in relation_phrases:
        split = _top_level_word_split(value, phrases)
        if split is None:
            continue
        left, _, right = split
        return RelationExpr(
            operator=relation_operator,
            left=_lower_or_opaque(left),
            right=_lower_or_opaque(right),
        )

    if value.lower().startswith("not "):
        return NotExpr(operand=_lower_or_opaque(value[4:]))

    return _Parser(value).parse()


def _lower_or_opaque(text: str) -> MathExpr:
    try:
        return _lower_recursive(text)
    except _ParseError:
        return OpaqueExpr(text=text.strip())


def _domain_text(domain_word: str | None, explicit_domain: str | None) -> str | None:
    if explicit_domain is not None:
        return explicit_domain
    if domain_word is None:
        return None
    return _DOMAIN_WORDS.get(domain_word.lower())


def _lower_quantifier(text: str) -> QuantifiedExpr | None:
    english = re.fullmatch(
        r"(?is)(?:for all|for every|for each)\s+"
        r"(?:(real|reals|integer|integers|natural|naturals)\s+)?"
        r"([A-Za-z][A-Za-z0-9_]*)"
        r"(?:\s+(?:in|belonging to)\s+([^,]+))?\s*,\s*(.+)",
        text,
    )
    if english is not None:
        domain_word, name, explicit_domain, body = english.groups()
        domain_text = _domain_text(domain_word, explicit_domain)
        domain = _lower_or_opaque(domain_text) if domain_text else None
        return QuantifiedExpr(
            quantifier=Quantifier.FOR_ALL,
            binder=Binder(name=IdentifierExpr(name=name), domain=domain),
            body=_lower_or_opaque(body),
        )

    exists_english = re.fullmatch(
        r"(?is)there exists\s+"
        r"(?:(?:an?|some)\s+)?"
        r"(?:(real|reals|integer|integers|natural|naturals)\s+)?"
        r"([A-Za-z][A-Za-z0-9_]*)"
        r"(?:\s+(?:in|belonging to)\s+([^,]+))?\s*"
        r"(?:,|such that|with)\s*(.+)",
        text,
    )
    if exists_english is not None:
        domain_word, name, explicit_domain, body = exists_english.groups()
        domain_text = _domain_text(domain_word, explicit_domain)
        domain = _lower_or_opaque(domain_text) if domain_text else None
        return QuantifiedExpr(
            quantifier=Quantifier.EXISTS,
            binder=Binder(name=IdentifierExpr(name=name), domain=domain),
            body=_lower_or_opaque(body),
        )

    symbolic = re.fullmatch(
        r"(?s)([∀∃])\s*([A-Za-z][A-Za-z0-9_]*)"
        r"(?:\s*(?:∈|:)\s*([^,.]+))?\s*[,\.]\s*(.+)",
        text,
    )
    if symbolic is None:
        return None
    quantifier_text, name, domain_text, body = symbolic.groups()
    domain = _lower_or_opaque(domain_text) if domain_text else None
    return QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL if quantifier_text == "∀" else Quantifier.EXISTS,
        binder=Binder(name=IdentifierExpr(name=name), domain=domain),
        body=_lower_or_opaque(body),
    )


def contains_opaque(expression: MathExpr) -> bool:
    return any(isinstance(item, OpaqueExpr) for item in walk_math_expr(expression))


def walk_math_expr(expression: MathExpr) -> tuple[MathExpr, ...]:
    """Return a deterministic pre-order traversal of a canonical expression tree."""

    items: list[MathExpr] = []

    def visit(item: MathExpr) -> None:
        items.append(item)
        if isinstance(item, ApplyExpr):
            visit(item.function)
            for argument in item.arguments:
                visit(argument)
        elif isinstance(item, OperatorExpr):
            for argument in item.arguments:
                visit(argument)
        elif isinstance(item, RelationExpr):
            visit(item.left)
            visit(item.right)
        elif isinstance(item, LogicalExpr):
            for argument in item.arguments:
                visit(argument)
        elif isinstance(item, NotExpr):
            visit(item.operand)
        elif isinstance(item, (TupleExpr, SetExpr)):
            for child in item.items:
                visit(child)
        elif isinstance(item, QuantifiedExpr):
            visit(item.binder.name)
            if item.binder.domain is not None:
                visit(item.binder.domain)
            visit(item.body)

    visit(expression)
    return tuple(items)


def lower_math_expression(text: str) -> ExpressionLowering:
    """Partially elaborate a bounded mathematical expression without guessing."""

    normalized = normalize_formula_source(text)
    try:
        expression = _lower_recursive(normalized)
    except _ParseError:
        expression = OpaqueExpr(
            text=normalized or text.strip(),
            reason="unsupported_syntax",
        )
        status = ExprLoweringStatus.OPAQUE
    else:
        status = (
            ExprLoweringStatus.PARTIAL
            if contains_opaque(expression)
            else ExprLoweringStatus.FULL
        )
    return ExpressionLowering(
        expression=expression,
        status=status,
        source_text=text,
    )


def _precedence(expression: MathExpr) -> int:
    if isinstance(expression, LogicalExpr):
        return _PRECEDENCE[expression.operator.value]
    if isinstance(expression, RelationExpr):
        return 5
    if isinstance(expression, OperatorExpr):
        if len(expression.arguments) == 1:
            return 9
        return _PRECEDENCE.get(expression.operator, 9)
    if isinstance(expression, NotExpr):
        return 9
    if isinstance(expression, QuantifiedExpr):
        return 0
    return 10


def _render_child(expression: MathExpr, parent_precedence: int) -> str:
    rendered = render_math_expr(expression)
    if _precedence(expression) < parent_precedence:
        return f"({rendered})"
    return rendered


def render_math_expr(expression: MathExpr) -> str:
    """Render canonical expression structure deterministically for diagnostics/tests."""

    if isinstance(expression, IdentifierExpr):
        return expression.name
    if isinstance(expression, LiteralExpr):
        return expression.value
    if isinstance(expression, OpaqueExpr):
        return f"?{{{expression.text}}}"
    if isinstance(expression, ApplyExpr):
        arguments = ",".join(
            render_math_expr(argument) for argument in expression.arguments
        )
        return f"{_render_child(expression.function, 10)}({arguments})"
    if isinstance(expression, OperatorExpr):
        if len(expression.arguments) == 1:
            return f"{expression.operator}{_render_child(expression.arguments[0], 9)}"
        precedence = _PRECEDENCE.get(expression.operator, 9)
        return expression.operator.join(
            _render_child(argument, precedence) for argument in expression.arguments
        )
    if isinstance(expression, RelationExpr):
        return (
            f"{_render_child(expression.left, 5)}{expression.operator.value}"
            f"{_render_child(expression.right, 5)}"
        )
    if isinstance(expression, LogicalExpr):
        precedence = _PRECEDENCE[expression.operator.value]
        return expression.operator.value.join(
            _render_child(argument, precedence) for argument in expression.arguments
        )
    if isinstance(expression, NotExpr):
        return f"¬{_render_child(expression.operand, 9)}"
    if isinstance(expression, TupleExpr):
        return "(" + ",".join(render_math_expr(item) for item in expression.items) + ")"
    if isinstance(expression, SetExpr):
        return "{" + ",".join(render_math_expr(item) for item in expression.items) + "}"
    if isinstance(expression, QuantifiedExpr):
        binder = expression.binder.name.name
        if expression.binder.domain is not None:
            binder += f"∈{render_math_expr(expression.binder.domain)}"
        body = render_math_expr(expression.body)
        if isinstance(expression.body, LogicalExpr):
            body = f"({body})"
        return f"{expression.quantifier.value}{binder}.{body}"
    raise TypeError(f"unsupported MathExpr node {type(expression)!r}")
