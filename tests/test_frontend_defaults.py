from thorn.frontends import DEFAULT_FRONTEND_NAME, get_default_frontend, get_frontend


def test_frontend_default_is_one_explicit_runtime_choice() -> None:
    assert DEFAULT_FRONTEND_NAME == "regex"
    assert get_default_frontend().name == DEFAULT_FRONTEND_NAME
    assert get_frontend("current").name == DEFAULT_FRONTEND_NAME
