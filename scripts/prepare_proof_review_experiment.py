from __future__ import annotations

import argparse
import json
from pathlib import Path

from thorn.proof_review_eval import build_proof_review_inventory
from thorn.spacy_linguistic import LinguisticFrontendUnavailable


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the keyless raw/proof-IR/proof-IR+rescue experiment inventory."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("eval/proof-review-challenge.json"),
    )
    parser.add_argument("--model", default="gpt-5.6")
    parser.add_argument(
        "--structural-only",
        action="store_true",
        help="skip the normal local spaCy frontend; intended only for debugging",
    )
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        inventory = build_proof_review_inventory(
            args.manifest,
            model=args.model,
            structural_only=args.structural_only,
        )
    except LinguisticFrontendUnavailable as exc:
        print(
            "proof-review inventory: local linguistic frontend unavailable: "
            f"{exc}. Install en_core_web_sm or use --structural-only for debugging."
        )
        return 2

    rendered = json.dumps(inventory, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
