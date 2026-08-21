from __future__ import annotations

from collections.abc import Iterable

from thorn.frontend import FrontendFile, FrontendRegion, FrontendRegionKind

_ENVIRONMENT_KINDS = {
    "comment": FrontendRegionKind.COMMENT,
    "verbatim": FrontendRegionKind.VERBATIM,
    "verbatim*": FrontendRegionKind.VERBATIM,
    "lstlisting": FrontendRegionKind.LISTING,
    "minted": FrontendRegionKind.MINTED,
    "asy": FrontendRegionKind.OPAQUE,
    "asydef": FrontendRegionKind.OPAQUE,
    "pycode": FrontendRegionKind.OPAQUE,
    "luacode": FrontendRegionKind.OPAQUE,
    "luacode*": FrontendRegionKind.OPAQUE,
    "sagesilent": FrontendRegionKind.OPAQUE,
    "sageblock": FrontendRegionKind.OPAQUE,
}


def _merge_intervals(intervals: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def build_frontend_regions(
    file: FrontendFile,
    *,
    explicit_regions: Iterable[FrontendRegion] = (),
) -> list[FrontendRegion]:
    """Combine parser-owned normalized facts into complete source-role coverage.

    This function performs no TeX scanning. Adapters supply parser-owned comment
    or raw-code spans; the shared compositor only combines those spans with
    normalized environment, macro, and math facts.
    """

    document = next(
        (
            environment
            for environment in file.environments
            if environment.name.casefold() == "document"
        ),
        None,
    )
    body_start = document.body_span.start_offset if document is not None else 0
    body_end = document.body_span.end_offset if document is not None else len(file.raw)

    regions: list[FrontendRegion] = []
    if body_start > 0:
        regions.append(
            FrontendRegion(
                kind=FrontendRegionKind.PREAMBLE,
                span=file.span(0, body_start),
            )
        )
    if body_end < len(file.raw):
        regions.append(
            FrontendRegion(
                kind=FrontendRegionKind.NON_DOCUMENT,
                span=file.span(body_end, len(file.raw)),
            )
        )

    for region in explicit_regions:
        if body_start <= region.span.start_offset and region.span.end_offset <= body_end:
            regions.append(region)

    for environment in file.environments:
        kind = _ENVIRONMENT_KINDS.get(environment.name.casefold())
        if kind is None:
            continue
        if body_start <= environment.span.start_offset and environment.span.end_offset <= body_end:
            regions.append(FrontendRegion(kind=kind, span=environment.span))

    for math in file.math:
        if body_start <= math.span.start_offset and math.span.end_offset <= body_end:
            regions.append(FrontendRegion(kind=FrontendRegionKind.MATH, span=math.span))

    unique: dict[tuple[FrontendRegionKind, int, int], FrontendRegion] = {}
    for region in regions:
        key = (region.kind, region.span.start_offset, region.span.end_offset)
        unique[key] = region
    regions = list(unique.values())

    excluded = [
        (region.span.start_offset, region.span.end_offset)
        for region in regions
        if region.kind
        in {
            FrontendRegionKind.COMMENT,
            FrontendRegionKind.VERBATIM,
            FrontendRegionKind.LISTING,
            FrontendRegionKind.MINTED,
            FrontendRegionKind.OPAQUE,
            FrontendRegionKind.MATH,
        }
    ]
    excluded.extend(
        (macro.span.start_offset, macro.span.end_offset)
        for macro in file.macros
        if body_start <= macro.span.start_offset and macro.span.end_offset <= body_end
    )

    cursor = body_start
    for start, end in _merge_intervals(excluded):
        start = max(start, body_start)
        end = min(end, body_end)
        if cursor < start:
            regions.append(
                FrontendRegion(
                    kind=FrontendRegionKind.DOCUMENT_TEXT,
                    span=file.span(cursor, start),
                )
            )
        cursor = max(cursor, end)
    if cursor < body_end:
        regions.append(
            FrontendRegion(
                kind=FrontendRegionKind.DOCUMENT_TEXT,
                span=file.span(cursor, body_end),
            )
        )

    regions.sort(key=lambda region: (region.span.start_offset, region.kind.value))
    return regions
