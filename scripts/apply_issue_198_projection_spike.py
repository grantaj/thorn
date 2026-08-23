from __future__ import annotations

from pathlib import Path


PATH = Path("src/thorn/source_projection.py")


def _replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"projection spike expected one match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = PATH.read_text(encoding="utf-8")

    placeholder = '''def _placeholder(characters: list[str], start: int, end: int, marker: str) -> None:\n    _mask(characters, start, end)\n    for index in range(max(0, start), min(len(characters), end)):\n        if characters[index] != "\\n":\n            characters[index] = marker\n            break\n'''
    helpers = placeholder + '''\n\ndef _preserve_math_sentence_terminator(\n    characters: list[str], file: FrontendFile, source: SourceSpan\n) -> None:\n    """Spike only: keep parser-contained terminal punctuation visible to NLP."""\n\n    raw = source.text(file.raw)\n    if not LinguisticProjection._math_ends_sentence(raw):\n        return\n    for index in range(source.end_offset - 1, source.start_offset - 1, -1):\n        if file.raw[index] in ".!?":\n            characters[index] = file.raw[index]\n            return\n\n\ndef _lexicalize_macro_syntax(characters: list[str], macro: FrontendMacro) -> None:\n    """Spike only: expose parser-owned command/argument content without TeX punctuation.\n\n    The command name is deliberately retained.  This does not assert that an\n    arbitrary macro is semantically transparent; it tests only whether raw TeX\n    punctuation at the linguistic boundary is causing the observed token damage.\n    """\n\n    if macro.span.start_offset < macro.span.end_offset:\n        _mask(characters, macro.span.start_offset, macro.span.start_offset + 1)\n    for argument in macro.arguments:\n        if argument.span.end_offset - argument.span.start_offset < 2:\n            continue\n        _mask(characters, argument.span.start_offset, argument.span.start_offset + 1)\n        _mask(characters, argument.span.end_offset - 1, argument.span.end_offset)\n'''
    text = _replace_once(text, placeholder, helpers)

    text = _replace_once(
        text,
        '''            _placeholder(characters, region.span.start_offset, region.span.end_offset, "∎")\n            tokens.append(ProjectionToken(kind=ProjectionTokenKind.MATH, source=region.span))\n''',
        '''            _placeholder(characters, region.span.start_offset, region.span.end_offset, "∎")\n            _preserve_math_sentence_terminator(characters, file, region.span)\n            tokens.append(ProjectionToken(kind=ProjectionTokenKind.MATH, source=region.span))\n''',
    )

    text = _replace_once(
        text,
        '''    for macro in file.macros:\n        if macro.name not in _REFERENCE_MACROS:\n            continue\n        if _inside_ineligible_region(file, macro.span.start_offset, macro.span.end_offset):\n            continue\n        _placeholder(characters, macro.span.start_offset, macro.span.end_offset, "↗")\n''',
        '''    for macro in file.macros:\n        if _inside_ineligible_region(file, macro.span.start_offset, macro.span.end_offset):\n            continue\n        if macro.name not in _REFERENCE_MACROS:\n            _lexicalize_macro_syntax(characters, macro)\n            continue\n        _placeholder(characters, macro.span.start_offset, macro.span.end_offset, "↗")\n''',
    )

    PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
