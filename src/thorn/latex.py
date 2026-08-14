from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from thorn.models import SourceRange, TheoremUnit

_DEFAULT_THEOREM_ENVS = {
    "theorem",
    "lemma",
    "proposition",
    "corollary",
    "claim",
}

_NEWTHEOREM_RE = re.compile(r"\\newtheorem\*?\s*\{([^}]+)\}")
_INCLUDE_RE = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")
_LABEL_RE = re.compile(r"\\label\s*\{([^}]+)\}")
_REF_RE = re.compile(r"\\(?:ref|eqref|autoref|cref|Cref)\s*\{([^}]+)\}")


@dataclass(frozen=True)
class _Block:
    env: str
    title: str | None
    body: str
    start: int
    end: int
    start_line: int
    end_line: int


def _strip_comments(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        escaped = False
        cut = len(line)
        for i, char in enumerate(line):
            if char == "%" and not escaped:
                cut = i
                break
            escaped = not escaped if char == "\\" else False
        out.append(line[:cut] + ("\n" if line.endswith("\n") and cut < len(line) else ""))
    return "".join(out)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _read_project(main: Path) -> dict[Path, str]:
    main = main.resolve()
    pending = [main]
    seen: dict[Path, str] = {}

    while pending:
        path = pending.pop()
        if path in seen:
            continue
        if not path.exists():
            raise FileNotFoundError(path)
        text = path.read_text(encoding="utf-8")
        seen[path] = text
        cleaned = _strip_comments(text)
        for match in _INCLUDE_RE.finditer(cleaned):
            name = match.group(1).strip()
            child = Path(name)
            if child.suffix == "":
                child = child.with_suffix(".tex")
            child = (path.parent / child).resolve()
            if child not in seen:
                pending.append(child)
    return seen


def _theorem_envs(files: dict[Path, str]) -> set[str]:
    envs = set(_DEFAULT_THEOREM_ENVS)
    for text in files.values():
        envs.update(_NEWTHEOREM_RE.findall(_strip_comments(text)))
    return envs


def _find_blocks(text: str, envs: set[str]) -> list[_Block]:
    if not envs:
        return []
    names = "|".join(sorted((re.escape(name) for name in envs), key=len, reverse=True))
    begin_re = re.compile(rf"\\begin\{{(?P<env>{names})\}}(?:\[(?P<title>[^]]*)\])?")
    blocks: list[_Block] = []

    for match in begin_re.finditer(text):
        env = match.group("env")
        end_re = re.compile(rf"\\end\{{{re.escape(env)}\}}")
        end_match = end_re.search(text, match.end())
        if end_match is None:
            continue
        blocks.append(
            _Block(
                env=env,
                title=match.group("title"),
                body=text[match.end() : end_match.start()].strip(),
                start=match.start(),
                end=end_match.end(),
                start_line=_line_number(text, match.start()),
                end_line=_line_number(text, end_match.end()),
            )
        )
    return blocks


def _find_proof_after(text: str, block: _Block, next_block_start: int | None) -> _Block | None:
    upper = next_block_start if next_block_start is not None else len(text)
    # A proof normally follows its result. Keep the association deliberately conservative:
    # no more than 40 source lines and never across another theorem-like block.
    tail = text[block.end:upper]
    proof_re = re.compile(r"\\begin\{proof\}(?:\[(?P<title>[^]]*)\])?")
    match = proof_re.search(tail)
    if match is None:
        return None
    absolute_start = block.end + match.start()
    if _line_number(text, absolute_start) - block.end_line > 40:
        return None
    end_re = re.compile(r"\\end\{proof\}")
    end_match = end_re.search(text, block.end + match.end(), upper)
    if end_match is None:
        return None
    body_start = block.end + match.end()
    return _Block(
        env="proof",
        title=match.group("title"),
        body=text[body_start:end_match.start()].strip(),
        start=absolute_start,
        end=end_match.end(),
        start_line=_line_number(text, absolute_start),
        end_line=_line_number(text, end_match.end()),
    )


def _local_context(text: str, start_line: int, lines: int = 120) -> str:
    source_lines = text.splitlines()
    first = max(0, start_line - lines - 1)
    last = max(0, start_line - 1)
    return "\n".join(source_lines[first:last]).strip()


def extract_units(main_file: str | Path) -> list[TheoremUnit]:
    """Extract theorem-like result/proof units from a LaTeX project.

    This is intentionally a pragmatic parser. It preserves source locations and handles common
    theorem declarations without pretending to interpret arbitrary TeX macro expansion.
    """

    main = Path(main_file).resolve()
    files = _read_project(main)
    envs = _theorem_envs(files)
    units: list[TheoremUnit] = []

    for path, text in files.items():
        blocks = sorted(_find_blocks(text, envs), key=lambda item: item.start)
        for index, block in enumerate(blocks):
            next_start = blocks[index + 1].start if index + 1 < len(blocks) else None
            proof = _find_proof_after(text, block, next_start)
            label_match = _LABEL_RE.search(block.body)
            label = label_match.group(1) if label_match else None
            identifier = label or f"{path.name}:{block.start_line}:{block.env}"
            units.append(
                TheoremUnit(
                    identifier=identifier,
                    environment=block.env,
                    title=block.title,
                    label=label,
                    statement=block.body,
                    proof=proof.body if proof else None,
                    statement_range=SourceRange(
                        file=str(path), start_line=block.start_line, end_line=block.end_line
                    ),
                    proof_range=(
                        SourceRange(
                            file=str(path), start_line=proof.start_line, end_line=proof.end_line
                        )
                        if proof
                        else None
                    ),
                    local_context=_local_context(text, block.start_line),
                )
            )

    units.sort(key=lambda unit: (unit.statement_range.file, unit.statement_range.start_line))

    by_label = {unit.label: unit for unit in units if unit.label}
    enriched: list[TheoremUnit] = []
    for unit in units:
        refs = set(_REF_RE.findall(unit.statement + "\n" + (unit.proof or "")))
        referenced: list[str] = []
        for label in sorted(refs):
            dependency = by_label.get(label)
            if dependency is None or dependency.identifier == unit.identifier:
                continue
            referenced.append(
                f"[{dependency.environment} {dependency.identifier}]\n{dependency.statement}"
            )
        enriched.append(unit.model_copy(update={"referenced_results": referenced}))
    return enriched
