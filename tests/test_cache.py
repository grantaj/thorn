from pathlib import Path

from thorn.cache import AuditCache
from thorn.models import SourceRange, TheoremUnit, UnitAudit


def test_cache_round_trip(tmp_path: Path) -> None:
    unit = TheoremUnit(
        identifier="thm:x",
        environment="theorem",
        label="thm:x",
        statement="X.",
        proof="Proof.",
        statement_range=SourceRange(file="main.tex", start_line=1, end_line=3),
    )
    cache = AuditCache(tmp_path)
    key = cache.key(unit, "model", "prompt", True)
    cache.put(key, UnitAudit(unit=unit))
    loaded = cache.get(key)
    assert loaded is not None
    assert loaded.unit.identifier == "thm:x"
