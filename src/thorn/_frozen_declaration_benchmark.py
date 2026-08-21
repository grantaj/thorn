"""Frozen pre-#161 declaration recognizer surface for research reproduction only.

These regexes preserve the #160 phrase-baseline measurement. Production
semantic authority must not import this module; Slice D consumes normalized
``ProseDeclarationCandidate`` values instead. The compatibility re-export from
``project_semantic_context`` exists only until the research harness is cleaned
up in Slice E.
"""

from __future__ import annotations

import re

_STYLE_TERM = (
    r"(?:\\[A-Za-z]+\{[^{}]+\}|"
    r"[A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z][A-Za-z0-9-]*){0,3})"
)

_CALLED_RE = re.compile(
    rf"\b(?:is|are|will\s+be|shall\s+be)\s+called\s+"
    rf"(?P<term>{_STYLE_TERM})\s+"
    r"(?:when|if|whenever|provided\s+that)\b",
    re.IGNORECASE,
)
_SAID_TO_BE_RE = re.compile(
    rf"\b(?:is|are)\s+said\s+to\s+be\s+(?P<term>{_STYLE_TERM})\s+"
    r"(?:when|if|whenever|provided\s+that)\b",
    re.IGNORECASE,
)
_WE_SAY_RE = re.compile(
    rf"\bwe\s+say\s+that\b[^.!?\n]{{1,160}}?\b(?:is|are)\s+"
    rf"(?P<term>{_STYLE_TERM})\s+"
    r"(?:when|if|whenever|provided\s+that)\b",
    re.IGNORECASE,
)
_BY_MEAN_RE = re.compile(
    rf"\bby\s+(?:an?\s+)?(?P<term>{_STYLE_TERM})\s+we\s+mean\b",
    re.IGNORECASE,
)
_AMBIENT_RE = re.compile(
    r"(?:^|(?<=[.!?])\s+)"
    r"(?:throughout|in\s+what\s+follows|henceforth|from\s+now\s+on|"
    r"unless\s+otherwise\s+stated|unless\s+specified\s+otherwise)\s*,?\s*"
    r"(?:(?:the|all|every|each)\s+)?"
    r"(?P<term>[A-Za-z][A-Za-z-]*(?:\s+[A-Za-z][A-Za-z-]*){0,5}?)\s+"
    r"(?:is|are|means?|denotes?|refers\s+to)\b",
    re.IGNORECASE | re.MULTILINE,
)

__all__ = [
    "_AMBIENT_RE",
    "_BY_MEAN_RE",
    "_CALLED_RE",
    "_SAID_TO_BE_RE",
    "_WE_SAY_RE",
]
