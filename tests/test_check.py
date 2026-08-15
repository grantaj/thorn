from pathlib import Path

from thorn.check import CheckCategory, check_project
from thorn.latex import extract_project


def _categories(path: Path) -> list[CheckCategory]:
    return [finding.category for finding in check_project(extract_project(path))]


def test_dependency_checks_cover_duplicates_ambiguity_missing_and_cycles(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\begin{lemma}\label{lem:dup}
First duplicate.
\end{lemma}
\begin{lemma}\label{lem:dup}
Second duplicate.
\end{lemma}
\begin{lemma}\label{lem:a}
A.
\end{lemma}
\begin{proof}
By Lemma~\ref{lem:b}.
\end{proof}
\begin{lemma}\label{lem:b}
B.
\end{lemma}
\begin{proof}
By Lemma~\ref{lem:a}.
\end{proof}
\begin{theorem}\label{thm:target}
A target theorem.
\end{theorem}
\begin{proof}
Use Lemma~\ref{lem:dup} and Lemma~\ref{lem:missing}.
\end{proof}
""",
        encoding="utf-8",
    )

    findings = check_project(extract_project(tex))
    categories = {finding.category for finding in findings}

    assert CheckCategory.DUPLICATE_LABEL in categories
    assert CheckCategory.AMBIGUOUS_REFERENCE in categories
    assert CheckCategory.MISSING_REFERENCE in categories
    assert CheckCategory.CIRCULAR_DEPENDENCY in categories
    assert all(finding.source.file == str(tex.resolve()) for finding in findings)


def test_existing_non_result_label_is_not_reported_missing(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\newtheorem{theorem}{Theorem}
\begin{theorem}\label{thm:ok}
The identity is useful.
\end{theorem}
\begin{proof}
\begin{equation}\label{eq:identity}
1=1.
\end{equation}
Equation~\eqref{eq:identity} proves the claim.
\end{proof}
""",
        encoding="utf-8",
    )

    assert CheckCategory.MISSING_REFERENCE not in _categories(tex)


def test_unresolved_use_before_later_declaration_stays_ir_only(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\newtheorem{theorem}{Theorem}
\begin{theorem}\label{thm:order}
First $q>0$. Let $q$ be real. Then $q>1$.
\end{theorem}
""",
        encoding="utf-8",
    )

    project = extract_project(tex)
    unresolved = [
        use
        for use in project.symbol_table.uses
        if use.name == "q" and use.resolved_symbol_identifier is None
    ]
    assert unresolved
    assert check_project(project) == []


def test_local_quantifier_same_name_outside_scope_stays_ir_only(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\newtheorem{theorem}{Theorem}
\begin{theorem}\label{thm:scope}
Let $X$ be a set. We have $\forall z\in X,\ z=z$. Then $z=z$.
\end{theorem}
""",
        encoding="utf-8",
    )

    project = extract_project(tex)
    unresolved = [
        use
        for use in project.symbol_table.uses
        if use.name == "z" and use.resolved_symbol_identifier is None
    ]
    assert unresolved
    assert check_project(project) == []


def test_trailing_quantifier_is_not_use_before_introduction(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\newtheorem{theorem}{Theorem}
\begin{theorem}\label{thm:trailing}
Let $f:X\to\mathbb R$ be bounded. There is $M>0$ with
\[
  f(x)\le M
\]
for every $x\in X$.
\end{theorem}
""",
        encoding="utf-8",
    )

    assert check_project(extract_project(tex)) == []


def test_incompatible_explicit_roles_are_reported_but_callable_roles_are_compatible(
    tmp_path: Path,
) -> None:
    bad = tmp_path / "bad.tex"
    bad.write_text(
        r"""\newtheorem{theorem}{Theorem}
\begin{theorem}\label{thm:roles}
For $f>0$, suppose the estimate holds. Let $f:X\to Y$ be continuous.
\end{theorem}
""",
        encoding="utf-8",
    )
    assert CheckCategory.ROLE_CONFLICT in _categories(bad)

    clean = tmp_path / "clean.tex"
    clean.write_text(
        r"""\newtheorem{theorem}{Theorem}
\begin{theorem}\label{thm:callable}
Let $f:X\to Y$ be continuous. Define $f(x)=x$.
\end{theorem}
""",
        encoding="utf-8",
    )
    assert CheckCategory.ROLE_CONFLICT not in _categories(clean)


def test_clean_structural_control_has_no_findings(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\begin{lemma}\label{lem:base}
Let $x$ be real. Then $x=x$.
\end{lemma}
\begin{theorem}\label{thm:clean}
Let $f:X\to Y$ be continuous.
\end{theorem}
\begin{proof}
By Lemma~\ref{lem:base}, the claim follows. For $n\in\mathbb N$, let $n=n$.
\end{proof}
""",
        encoding="utf-8",
    )

    assert check_project(extract_project(tex)) == []
