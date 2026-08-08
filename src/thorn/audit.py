from __future__ import annotations

from pathlib import Path

from thorn.cache import AuditCache
from thorn.models import (
    AuditFinding,
    DefenseItem,
    DefenseVerdict,
    TheoremUnit,
    UnitAudit,
)
from thorn.providers.base import AuditProvider

PROMPT_VERSION = "2026-08-08.1"


def audit_unit(
    unit: TheoremUnit,
    provider: AuditProvider,
    *,
    use_defender: bool = True,
    cache: AuditCache | None = None,
) -> UnitAudit:
    cache_key = AuditCache.key(unit, provider.model, PROMPT_VERSION, use_defender)
    if cache is not None:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached.model_copy(update={"cached": True})

    attack = provider.attack(unit)
    findings = attack.findings
    if not findings:
        result = UnitAudit(unit=unit, findings=[])
        if cache is not None:
            cache.put(cache_key, result)
        return result

    if use_defender:
        defense = provider.defend(unit, findings)
        verdicts = {item.finding_id: item for item in defense.verdicts}
    else:
        verdicts = {
            item.id: DefenseItem(
                finding_id=item.id,
                verdict=DefenseVerdict.SURVIVES,
                explanation="Defender pass disabled.",
                confidence=item.confidence,
            )
            for item in findings
        }

    source = unit.proof_range or unit.statement_range
    final: list[AuditFinding] = []
    for candidate in findings:
        verdict = verdicts.get(candidate.id)
        if verdict is None:
            verdict = DefenseItem(
                finding_id=candidate.id,
                verdict=DefenseVerdict.UNCERTAIN,
                explanation="Defender omitted this finding.",
                confidence=0.0,
            )
        if verdict.verdict == DefenseVerdict.DISMISSED:
            continue
        final.append(
            AuditFinding(
                unit_id=unit.identifier,
                rule=candidate.rule,
                category=candidate.category,
                severity=candidate.severity,
                title=candidate.title,
                explanation=candidate.explanation,
                evidence=candidate.evidence,
                counterexample=candidate.counterexample,
                attacker_confidence=candidate.confidence,
                defender_verdict=verdict.verdict,
                defender_explanation=verdict.explanation,
                defender_confidence=verdict.confidence,
                source=source,
            )
        )

    result = UnitAudit(unit=unit, findings=final)
    if cache is not None:
        cache.put(cache_key, result)
    return result


def default_cache(path: str | Path = ".thorn/cache") -> AuditCache:
    return AuditCache(Path(path))
