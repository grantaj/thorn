from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "issue_101_redteam.py"


def test_issue_101_keyless_redteam_observer_runs_without_provider_credentials(
    tmp_path: Path,
) -> None:
    output = tmp_path / "observations.json"
    env = dict(os.environ)
    env["OPENAI_API_KEY"] = ""
    completed = subprocess.run(
        [sys.executable, str(_SCRIPT), "--check", "--output", str(output)],
        cwd=_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["issue"] == 101
    assert payload["semantic_adjudication"].startswith("not performed")
    assert len(payload["cases"]) == 5
    assert all(case["source_hash_matches_frozen"] for case in payload["cases"])
    assert "unsafe semantic cache reuse" not in completed.stdout
