"""Run the existing #162 contract unchanged with Tree-sitter as a backend."""

import pytest


def pytest_configure() -> None:
    import thorn.frontends
    from thorn.frontends.tree_sitter import TreeSitterLatexFrontend

    # The #162 tests import RegexLatexFrontend during collection. Replacing that
    # one factory before collection makes the exact existing contract exercise
    # Tree-sitter while leaving the ordinary production/default test matrix
    # untouched. Pylatexenc remains the second differential configuration.
    thorn.frontends.RegexLatexFrontend = TreeSitterLatexFrontend


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Keep the evaluated grammar's one normative project gap explicit.

    tree-sitter-latex collapses ``\\input{{chapter}`` to undifferentiated
    parser error evidence, so the adapter cannot identify an include boundary
    without rescanning raw LaTeX. #158 explicitly forbids adding that parallel
    parser. A strict xfail records the #162 contract miss and will fail if the
    grammar later recovers enough structure for this case to pass.
    """

    from thorn.frontends.tree_sitter import TreeSitterLatexFrontend

    for item in items:
        callspec = getattr(item, "callspec", None)
        if callspec is None:
            continue
        if getattr(item, "originalname", None) != (
            "test_malformed_direct_include_is_exact_project_partiality_not_guessed_order"
        ):
            continue
        frontend_factory = callspec.params.get("frontend_factory")
        malformed = callspec.params.get("malformed")
        if frontend_factory is TreeSitterLatexFrontend and malformed == r"\input{{chapter}":
            item.add_marker(
                pytest.mark.xfail(
                    strict=True,
                    reason=(
                        "tree-sitter-latex loses command identity for this malformed "
                        "include; recovering it would require forbidden raw-source scanning"
                    ),
                )
            )
