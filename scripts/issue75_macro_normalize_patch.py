from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match in {path}, found {count}")
    file.write_text(text.replace(old, new), encoding="utf-8")


replace_once(
    "src/thorn/symbol_extract.py",
    '''                definition_operator=macro_match.group("operator"),
''',
    '''                # The source spelling is preserved by provenance; the semantic
                # symbol table records the mechanically recovered operator meaning.
                definition_operator=":=",
''',
)
replace_once(
    "tests/test_proof_ir_context_fidelity.py",
    '''    assert definition.operator == r"\\meaningop"
''',
    '''    assert definition.operator == ":="
''',
)
