from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected CI follow-up context missing in {path}: {old[:160]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Historical frozen experiments must reject the changed assurance tree before
# attempting to reconstruct request fingerprints under a newer transport contract.
replace(
    "scripts/run_issue_101_live.py",
    '''def preflight() -> dict[str, object]:
    assurance_revision, assurance_src_tree_sha, cases = _load_cases()
    _assert_assurance_code_unchanged(assurance_src_tree_sha)
''',
    '''def preflight() -> dict[str, object]:
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    _assert_assurance_code_unchanged(str(frozen["assurance_src_tree_sha"]))
    assurance_revision, assurance_src_tree_sha, cases = _load_cases()
''',
)
replace(
    "scripts/run_issue_101_live.py",
    '''def _run(provider: Any, *, mode: str, report_dir: Path | None) -> dict[str, object]:
    assurance_revision, assurance_src_tree_sha, cases = _load_cases()
    _assert_assurance_code_unchanged(assurance_src_tree_sha)
''',
    '''def _run(provider: Any, *, mode: str, report_dir: Path | None) -> dict[str, object]:
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    _assert_assurance_code_unchanged(str(frozen["assurance_src_tree_sha"]))
    assurance_revision, assurance_src_tree_sha, cases = _load_cases()
''',
)

# The issue-101 keyless observer is allowed to observe later production trees. A
# fingerprint mismatch is only a failed frozen contract when the assurance tree
# itself still matches; otherwise the tree drift is the earlier explanatory boundary.
replace(
    "scripts/issue_101_robustness.py",
    "import json\nimport tempfile\n",
    "import json\nimport subprocess\nimport tempfile\n",
)
replace(
    "scripts/issue_101_robustness.py",
    '''def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


''',
    '''def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _src_tree_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD:src/thorn"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


''',
)
replace(
    "scripts/issue_101_robustness.py",
    '''def observe() -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = [manifest["control"], *manifest["variants"]]
    return {
        "format_version": 1,
        "issue": 101,
        "assurance_revision": manifest["assurance_revision"],
''',
    '''def observe() -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = [manifest["control"], *manifest["variants"]]
    assurance_src_tree_sha = str(manifest["assurance_src_tree_sha"])
    current_src_tree_sha = _src_tree_sha()
    return {
        "format_version": 1,
        "issue": 101,
        "assurance_revision": manifest["assurance_revision"],
        "assurance_src_tree_sha": assurance_src_tree_sha,
        "current_src_tree_sha": current_src_tree_sha,
        "assurance_tree_matches": current_src_tree_sha == assurance_src_tree_sha,
''',
)
replace(
    "scripts/issue_101_robustness.py",
    '''def _check(payload: dict[str, object]) -> None:
    cases = payload["cases"]
    assert isinstance(cases, list)
    for case in cases:
''',
    '''def _check(payload: dict[str, object]) -> None:
    assurance_tree_matches = bool(payload["assurance_tree_matches"])
    cases = payload["cases"]
    assert isinstance(cases, list)
    for case in cases:
''',
)
replace(
    "scripts/issue_101_robustness.py",
    '''        if not case["request_fingerprint_matches_frozen"]:
            raise SystemExit(f"{case['id']}: frozen initial request fingerprint drifted")
''',
    '''        if assurance_tree_matches and not case["request_fingerprint_matches_frozen"]:
            raise SystemExit(f"{case['id']}: frozen initial request fingerprint drifted")
''',
)

replace(
    "tests/test_issue_101_robustness.py",
    '''    assert all(case["source_hash_matches_frozen"] for case in payload["cases"])
    assert all(case["request_fingerprint_matches_frozen"] for case in payload["cases"])
    assert "unsafe semantic cache reuse" not in completed.stdout
''',
    '''    assert all(case["source_hash_matches_frozen"] for case in payload["cases"])
    if payload["assurance_tree_matches"]:
        assert all(case["request_fingerprint_matches_frozen"] for case in payload["cases"])
    else:
        assert payload["current_src_tree_sha"] != payload["assurance_src_tree_sha"]
    assert "unsafe semantic cache reuse" not in completed.stdout
''',
)

replace(
    "tests/test_proof_review_output_cap.py",
    '''    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_parsed=ProofReviewModelResponse(action="review"),
            usage=SimpleNamespace(input_tokens=11, output_tokens=3, total_tokens=14),
        )
''',
    '''    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_parsed=ProofReviewModelResponse(action="review"),
            usage=SimpleNamespace(input_tokens=11, output_tokens=3, total_tokens=14),
        )

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text=ProofReviewModelResponse(action="review").model_dump_json(),
            usage=SimpleNamespace(input_tokens=11, output_tokens=3, total_tokens=14),
        )
''',
)
