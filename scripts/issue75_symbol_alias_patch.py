from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match in {path}, found {count}")
    file.write_text(text.replace(old, new), encoding="utf-8")


replace_once(
    "src/thorn/symbols.py",
    '''from __future__ import annotations

from enum import StrEnum
''',
    '''from __future__ import annotations

import re
from enum import StrEnum
''',
)

replace_once(
    "src/thorn/symbols.py",
    '''class ScopeKind(StrEnum):
''',
    '''_ATOMIC_BRACED_SUBSCRIPT_RE = re.compile(
    r"^(?P<base>(?:\\\\[A-Za-z]+|[A-Za-z]))_\\{(?P<sub>\\\\[A-Za-z]+|[A-Za-z0-9]+)\\}$"
)


def canonical_symbol_name(name: str) -> str:
    """Canonicalize only mechanically equivalent simple LaTeX symbol spellings."""

    match = _ATOMIC_BRACED_SUBSCRIPT_RE.match(name)
    if match is None:
        return name
    return f"{match.group('base')}_{match.group('sub')}"


class ScopeKind(StrEnum):
''',
)

replace_once(
    "src/thorn/symbols.py",
    '''    def resolve(
        self,
        name: str,
        scope_identifier: str,
        source: SourceSpan,
    ) -> Symbol | None:
        for symbol in self.visible_symbols(scope_identifier, source):
            if symbol.name == name:
                return symbol
        return None
''',
    '''    def resolve(
        self,
        name: str,
        scope_identifier: str,
        source: SourceSpan,
    ) -> Symbol | None:
        canonical_name = canonical_symbol_name(name)
        for symbol in self.visible_symbols(scope_identifier, source):
            if canonical_symbol_name(symbol.name) == canonical_name:
                return symbol
        return None
''',
)

replace_once(
    "src/thorn/symbol_extract.py",
    '''    SymbolUse,
)
''',
    '''    SymbolUse,
    canonical_symbol_name,
)
''',
)

replace_once(
    "src/thorn/symbol_extract.py",
    '''    identifier = _symbol_id(scope_identifier, candidate.name, symbol_source)
    symbol = Symbol(
        identifier=identifier,
        name=candidate.name,
''',
    '''    canonical_name = canonical_symbol_name(candidate.name)
    identifier = _symbol_id(scope_identifier, canonical_name, symbol_source)
    symbol = Symbol(
        identifier=identifier,
        name=canonical_name,
''',
)

replace_once(
    "src/thorn/symbol_extract.py",
    '''def _symbol_occurrences(content: str, name: str) -> list[tuple[int, int]]:
    escaped = re.escape(name)
    if name.startswith("\\\\"):
        pattern = re.compile(rf"{escaped}(?![A-Za-z])")
    else:
        pattern = re.compile(rf"(?<![A-Za-z]){escaped}(?![A-Za-z])")
    return [(match.start(), match.end()) for match in pattern.finditer(content)]
''',
    '''def _symbol_occurrences(content: str, name: str) -> list[tuple[int, int]]:
    canonical = canonical_symbol_name(name)
    subscript = re.match(
        r"^(?P<base>(?:\\\\[A-Za-z]+|[A-Za-z]))_(?P<sub>\\\\[A-Za-z]+|[A-Za-z0-9]+)$",
        canonical,
    )
    if subscript is not None:
        base = re.escape(subscript.group("base"))
        sub = re.escape(subscript.group("sub"))
        spelling = rf"{base}_(?:{sub}|\\{{{sub}\\}})"
    else:
        spelling = re.escape(canonical)
    if canonical.startswith("\\\\"):
        pattern = re.compile(rf"{spelling}(?![A-Za-z])")
    else:
        pattern = re.compile(rf"(?<![A-Za-z]){spelling}(?![A-Za-z])")
    return [(match.start(), match.end()) for match in pattern.finditer(content)]
''',
)

# Strengthen the project-definition regression so declaration and use deliberately
# use the two equivalent simple-subscript spellings from the real paper.
test_path = Path("tests/test_proof_ir_context_fidelity.py")
test = test_path.read_text(encoding="utf-8")
test = test.replace(
    r'''A_\tau \stackrel{{{{\scriptstyle\text{{\tiny def}}}}}}{{{{=}}}} {definition}.
''',
    r'''A_{{\tau}} \stackrel{{{{\scriptstyle\text{{\tiny def}}}}}}{{{{=}}}} {definition}.
''',
)
test = test.replace(
    '    assert r"A_\\tau" in rescue.text\n',
    '    assert r"A_{\\tau}" in rescue.text\n',
)
test_path.write_text(test, encoding="utf-8")
