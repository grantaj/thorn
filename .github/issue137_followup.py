from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected follow-up patch context missing in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/thorn/providers/openai.py",
    '''        if not isinstance(parsed, ProofReviewModelResponse):
            raise RuntimeError("proof-language reviewer returned the wrong structured result")
        return parsed
''',
    '''        if not isinstance(parsed, ProofReviewModelResponse):
            raise RuntimeError("proof-language reviewer returned the wrong structured result")
        return ProofReviewModelResponse.model_validate(parsed.model_dump(mode="python"))
''',
)

replace(
    "tests/test_rejected_replay.py",
    '''class _FakeResponses:
    def __init__(self, output: ProofReviewModelResponse) -> None:
        self.output = output

    def parse(self, **kwargs: object) -> SimpleNamespace:
        del kwargs
        return SimpleNamespace(
            output_parsed=self.output,
            usage=SimpleNamespace(input_tokens=10, output_tokens=2, total_tokens=12),
        )
''',
    '''class _FakeResponses:
    def __init__(self, output: ProofReviewModelResponse) -> None:
        self.output = output

    def parse(self, **kwargs: object) -> SimpleNamespace:
        del kwargs
        return SimpleNamespace(
            output_parsed=self.output,
            usage=SimpleNamespace(input_tokens=10, output_tokens=2, total_tokens=12),
        )

    def create(self, **kwargs: object) -> SimpleNamespace:
        del kwargs
        return SimpleNamespace(
            output_text=self.output.model_dump_json(),
            usage=SimpleNamespace(input_tokens=10, output_tokens=2, total_tokens=12),
        )
''',
)
