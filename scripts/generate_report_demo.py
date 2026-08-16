from __future__ import annotations

import argparse
from pathlib import Path

from thorn.report_demo import representative_report
from thorn.report_html import write_report_html


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Thorn's synthetic mixed-state report demo."
    )
    parser.add_argument("--output", type=Path, default=Path("thorn-report-demo.html"))
    args = parser.parse_args()
    destination = write_report_html(representative_report(), args.output)
    print(f"Report: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
