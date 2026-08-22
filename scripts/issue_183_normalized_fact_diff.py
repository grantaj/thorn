from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from declaration_contract_frontend import DeclarationContractFrontend
from thorn.frontends import RegexLatexFrontend
from thorn.frontends.tree_sitter import TreeSitterLatexFrontend
from thorn.latex import extract_project
from thorn.review_workflow import prepare_proof_review
from thorn.source_projection import build_linguistic_projection

ROOT = Path(__file__).resolve().parents[1]
A2_SOURCE = ROOT / "eval" / "robustness" / "issue_101" / "variant_prose_uniformity.tex"


def _span_tuple(span) -> tuple[int, int]:
    return span.start_offset, span.end_offset


def _show_file_facts(label: str, frontend, path: Path, needle: str) -> None:
    parsed = frontend.parse_project(path)
    file = parsed.files[0]
    start = file.raw.index(needle)
    end = min(len(file.raw), start + 500)
    projection = build_linguistic_projection(file)

    print(f"\n=== {label}: normalized facts around {needle!r} ===")
    print("diagnostics:", [(d.kind.value, d.message) for d in parsed.diagnostics])
    print("projection:", repr(projection.text[max(0, start - 120) : end]))
    print(
        "macros:",
        [
            (
                macro.name,
                _span_tuple(macro.span),
                macro.raw,
                [(arg.value, arg.optional, _span_tuple(arg.span)) for arg in macro.arguments],
            )
            for macro in file.macros
            if macro.span.start_offset < end and start - 120 < macro.span.end_offset
        ],
    )
    print(
        "math:",
        [
            (item.delimiter, _span_tuple(item.span), item.raw)
            for item in file.math
            if item.span.start_offset < end and start - 120 < item.span.end_offset
        ],
    )
    print(
        "regions:",
        [
            (region.kind.value, _span_tuple(region.span), region.span.text(file.raw))
            for region in file.regions
            if region.span.start_offset < end and start - 120 < region.span.end_offset
        ],
    )


def _show_a2(label: str, frontend) -> None:
    _show_file_facts(label, frontend, A2_SOURCE, "will be called")
    project = extract_project(
        A2_SOURCE,
        frontend=frontend,
        linguistic_frontend=DeclarationContractFrontend(),
    )
    print(f"{label} prose candidates:")
    for candidate in project.prose_declarations.candidates:
        if candidate.term.casefold() in {"stable", "observation window"}:
            print(
                candidate.role.value,
                candidate.term,
                _span_tuple(candidate.source),
                candidate.source.text(A2_SOURCE.read_text(encoding="utf-8")),
                _span_tuple(candidate.payload_source) if candidate.payload_source else None,
            )
    print(
        f"{label} semantic symbols:",
        [
            (symbol.name, symbol.result_identifier, symbol.introduction_kind.value)
            for symbol in project.symbol_table.symbols
            if symbol.name.casefold() in {"stable", "observation window"}
        ],
    )
    prepared = prepare_proof_review(project, project.unit("thm:uniform-decay"))
    print(
        f"{label} review sources:",
        [
            (source.address, source.text)
            for source in prepared.document.sources
            if "stable" in source.text.casefold() or "observation window" in source.text.casefold()
        ],
    )


def _macro_case(path: Path) -> None:
    path.write_text(
        r"""\documentclass{article}
\usepackage{amsthm}
\newcommand{\meaningop}{\stackrel{\text{\tiny def}}{=}}
\newcommand{\noteop}{\stackrel{\text{\tiny note}}{=}}
\newtheorem{proposition}{Proposition}
\begin{document}
\begin{equation}
A_{\tau} \meaningop F(\tau^2)
\end{equation}
\begin{equation}
B_{\tau} \noteop G(\tau^2)
\end{equation}
\begin{proposition}\label{prop:main}
$A_\tau$ has property $Q$.
\end{proposition}
\begin{proof}
\[
Q(A_\tau)
\]
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )


def _show_macro_case(label: str, frontend, path: Path) -> None:
    parsed = frontend.parse_project(path)
    file = parsed.files[0]
    print(f"\n=== {label}: local definitional macro normalized facts ===")
    print("diagnostics:", [(d.kind.value, d.message) for d in parsed.diagnostics])
    print(
        "command definitions:",
        [
            (
                macro.name,
                macro.raw,
                [(arg.value, arg.optional, _span_tuple(arg.span)) for arg in macro.arguments],
                _span_tuple(macro.span),
            )
            for macro in file.macros
            if macro.name in {"newcommand", "renewcommand", "providecommand"}
        ],
    )
    print(
        "math:",
        [(item.delimiter, item.raw, _span_tuple(item.span)) for item in file.math],
    )
    project = extract_project(path, frontend=frontend)
    print(
        "project symbols:",
        [
            (symbol.name, symbol.result_identifier, symbol.raw_introduction)
            for symbol in project.symbol_table.symbols
            if symbol.result_identifier is None
        ],
    )
    print(
        "project definitions:",
        [
            (definition.operator, definition.expression_latex, definition.raw)
            for definition in project.symbol_table.definitions
            if next(
                (
                    symbol.result_identifier
                    for symbol in project.symbol_table.symbols
                    if symbol.identifier == definition.symbol_identifier
                ),
                "missing",
            )
            is None
        ],
    )


def main() -> None:
    frontends = (
        ("regex", RegexLatexFrontend()),
        ("tree-sitter", TreeSitterLatexFrontend()),
    )
    for label, frontend in frontends:
        _show_a2(label, frontend)

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "macro-definition.tex"
        _macro_case(path)
        for label, frontend in frontends:
            _show_macro_case(label, frontend, path)


if __name__ == "__main__":
    main()
