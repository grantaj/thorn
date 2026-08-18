from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_issue_101_live_preflight_is_keyless_and_bounded(tmp_path: Path) -> None:
    output = tmp_path / "preflight.json"
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = ""
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_issue_101_live.py",
            "--preflight",
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, (
        f"issue-101 preflight failed\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["mode"] == "preflight"
    assert payload["model"] == "gpt-5.6"
    assert len(payload["cases"]) == 5
    limits = payload["limits"]
    assert limits["max_provider_requests"] == 10
    assert limits["max_input_tokens"] == 100_000
    assert limits["max_output_tokens_per_request"] == 4096
    assert limits["max_output_tokens"] == 40_960
    assert limits["all_initial_requests_input_upper_bound"] <= 100_000
    assert limits["hypothetical_all_maximal_two_turn_input_upper_bound"] > 100_000
    assert "before each actual request" in limits["input_guard"]
    assert all(
        case["initial_input_token_upper_bound"] <= limits["max_input_tokens"]
        for case in payload["cases"]
    )
    assert all(len(case["initial_request_fingerprint"]) == 64 for case in payload["cases"])
