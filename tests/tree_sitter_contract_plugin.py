"""Run the existing #162 contract unchanged with Tree-sitter as a backend."""


def pytest_configure() -> None:
    import thorn.frontends
    from thorn.frontends.tree_sitter import TreeSitterLatexFrontend

    # The #162 tests import RegexLatexFrontend during collection. Replacing that
    # one factory before collection makes the exact existing contract exercise
    # Tree-sitter while leaving the ordinary production/default test matrix
    # untouched. Pylatexenc remains the second differential configuration.
    thorn.frontends.RegexLatexFrontend = TreeSitterLatexFrontend
