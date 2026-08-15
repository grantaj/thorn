from pathlib import Path

from thorn.frontend import (
    FrontendArgument,
    FrontendEnvironment,
    FrontendFile,
    FrontendMacro,
    ParsedProject,
    SourceSpan,
)
from thorn.latex import extract_project


def _line_column(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    column = offset + 1 if last_newline < 0 else offset - last_newline
    return line, column


def _span(path: Path, text: str, start: int, end: int) -> SourceSpan:
    start_line, start_column = _line_column(text, start)
    end_line, end_column = _line_column(text, end)
    return SourceSpan(
        file=str(path.resolve()),
        start_offset=start,
        end_offset=end,
        start_line=start_line,
        start_column=start_column,
        end_line=end_line,
        end_column=end_column,
    )


def _argument(path: Path, text: str, raw: str, value: str, start: int) -> FrontendArgument:
    end = start + len(raw)
    return FrontendArgument(
        raw=raw,
        value=value,
        span=_span(path, text, start, end),
    )


def _macro(
    path: Path,
    text: str,
    *,
    name: str,
    raw: str,
    argument_raw: str,
    argument_value: str,
    start: int,
) -> FrontendMacro:
    argument_start = start + raw.index(argument_raw)
    return FrontendMacro(
        name=name,
        raw=raw,
        span=_span(path, text, start, start + len(raw)),
        arguments=[_argument(path, text, argument_raw, argument_value, argument_start)],
    )


class StubFrontend:
    """Independent frontend used to prove Thorn consumes only the contract."""

    name = "stub"

    def __init__(self, project: ParsedProject) -> None:
        self.project = project

    def parse_project(self, main_file: str | Path) -> ParsedProject:
        assert Path(main_file).resolve() == Path(self.project.main_file)
        return self.project


def test_injected_frontend_is_authoritative_and_preserves_disagreement(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    source = (
        "\\begin{lemma}\\label{lem:raw}\\label{lem:stub}A\\end{lemma}\n"
        "\\begin{theorem}\\label{thm:raw}\\label{thm:stub}B\\end{theorem}\n"
        "\\begin{proof}\\ref{lem:raw}\\ref{lem:stub}\\end{proof}\n"
    )
    tex.write_text(source, encoding="utf-8")

    lemma_start = source.index(r"\begin{lemma}")
    lemma_body_start = source.index(r"\label{lem:raw}", lemma_start)
    lemma_end_start = source.index(r"\end{lemma}", lemma_body_start)
    lemma_end = lemma_end_start + len(r"\end{lemma}")

    theorem_start = source.index(r"\begin{theorem}")
    theorem_body_start = source.index(r"\label{thm:raw}", theorem_start)
    theorem_end_start = source.index(r"\end{theorem}", theorem_body_start)
    theorem_end = theorem_end_start + len(r"\end{theorem}")

    proof_start = source.index(r"\begin{proof}")
    proof_body_start = source.index(r"\ref{lem:raw}", proof_start)
    proof_end_start = source.index(r"\end{proof}", proof_body_start)
    proof_end = proof_end_start + len(r"\end{proof}")

    lemma_stub_start = source.index(r"\label{lem:stub}")
    theorem_stub_start = source.index(r"\label{thm:stub}")
    ref_stub_start = source.index(r"\ref{lem:stub}")

    # The source deliberately contains earlier labels/references that the regex
    # compatibility backend would see. This independent frontend reports only
    # the later ones. Thorn must honor these normalized facts rather than
    # reaching back into raw source with backend-specific parsing assumptions.
    macros = [
        _macro(
            tex,
            source,
            name="label",
            raw=r"\label{lem:stub}",
            argument_raw="{lem:stub}",
            argument_value="lem:stub",
            start=lemma_stub_start,
        ),
        _macro(
            tex,
            source,
            name="label",
            raw=r"\label{thm:stub}",
            argument_raw="{thm:stub}",
            argument_value="thm:stub",
            start=theorem_stub_start,
        ),
        _macro(
            tex,
            source,
            name="ref",
            raw=r"\ref{lem:stub}",
            argument_raw="{lem:stub}",
            argument_value="lem:stub",
            start=ref_stub_start,
        ),
    ]
    environments = [
        FrontendEnvironment(
            name="lemma",
            raw=source[lemma_start:lemma_end],
            span=_span(tex, source, lemma_start, lemma_end),
            body_span=_span(tex, source, lemma_body_start, lemma_end_start),
        ),
        FrontendEnvironment(
            name="theorem",
            raw=source[theorem_start:theorem_end],
            span=_span(tex, source, theorem_start, theorem_end),
            body_span=_span(tex, source, theorem_body_start, theorem_end_start),
        ),
        FrontendEnvironment(
            name="proof",
            raw=source[proof_start:proof_end],
            span=_span(tex, source, proof_start, proof_end),
            body_span=_span(tex, source, proof_body_start, proof_end_start),
        ),
    ]
    frontend_project = ParsedProject(
        main_file=str(tex.resolve()),
        files=[
            FrontendFile(
                path=str(tex.resolve()),
                raw=source,
                macros=macros,
                environments=environments,
            )
        ],
    )

    project = extract_project(tex, frontend=StubFrontend(frontend_project))
    graph = project.dependency_graph

    assert [unit.identifier for unit in project.units] == ["lem:stub", "thm:stub"]
    assert graph.direct_dependency_ids("thm:stub") == ["lem:stub"]
    assert len(graph.edges) == 1
    assert graph.edges[0].target_label == "lem:stub"
    assert graph.edges[0].source.start_line == 3
    assert graph.edges[0].source.file == str(tex.resolve())


def test_injected_frontend_can_report_no_theorems_even_when_raw_source_has_one(
    tmp_path: Path,
) -> None:
    tex = tmp_path / "main.tex"
    source = r"\begin{theorem}\label{thm:raw}Raw theorem.\end{theorem}"
    tex.write_text(source, encoding="utf-8")

    frontend_project = ParsedProject(
        main_file=str(tex.resolve()),
        files=[FrontendFile(path=str(tex.resolve()), raw=source)],
    )

    project = extract_project(tex, frontend=StubFrontend(frontend_project))

    assert project.units == []
    assert project.dependency_graph.nodes == []
    assert project.dependency_graph.edges == []
