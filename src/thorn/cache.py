from __future__ import annotations

import hashlib
from pathlib import Path

from thorn.models import TheoremUnit, UnitAudit


class AuditCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    @staticmethod
    def key(unit: TheoremUnit, model: str, prompt_version: str, defender: bool) -> str:
        payload = "\n".join(
            [
                unit.model_dump_json(),
                model,
                prompt_version,
                f"defender={defender}",
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> UnitAudit | None:
        path = self.root / f"{key}.json"
        if not path.exists():
            return None
        return UnitAudit.model_validate_json(path.read_text(encoding="utf-8"))

    def put(self, key: str, value: UnitAudit) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{key}.json"
        path.write_text(value.model_dump_json(indent=2), encoding="utf-8")
