from __future__ import annotations

from collections.abc import Callable

from thorn.linguistic import LinguisticFrontend

LinguisticFrontendFactory = Callable[[], LinguisticFrontend]


def select_linguistic_frontend(
    *,
    structural_only: bool,
    injected: LinguisticFrontend | None = None,
    factory: LinguisticFrontendFactory,
) -> LinguisticFrontend | None:
    """Select Thorn's normal local linguistic frontend or an explicit degraded path.

    Production callers pass ``SpacyLinguisticFrontend`` as ``factory``. Tests may
    inject a parser-neutral fake implementing Thorn's ``LinguisticFrontend``
    protocol without downloading a spaCy model.
    """

    if structural_only:
        return None
    if injected is not None:
        return injected
    return factory()
