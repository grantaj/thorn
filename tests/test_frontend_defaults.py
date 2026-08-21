from thorn.frontends import (
    DEFAULT_FRONTEND_NAME,
    PREFERRED_FRONTEND_NAME,
    get_default_frontend,
    get_frontend,
)


def test_frontend_default_and_preferred_backend_are_distinct_explicit_choices() -> None:
    assert DEFAULT_FRONTEND_NAME == "regex"
    assert PREFERRED_FRONTEND_NAME == "tree-sitter"
    assert get_default_frontend().name == DEFAULT_FRONTEND_NAME
    assert get_frontend("current").name == DEFAULT_FRONTEND_NAME
