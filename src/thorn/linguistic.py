from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class LinguisticToken(BaseModel):
    """One parser-normalized token; no backend-specific object crosses this boundary."""

    index: int = Field(ge=0)
    text: str
    lemma: str
    pos: str
    dependency: str
    head_index: int = Field(ge=0)
    sentence_index: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class NormalizedLinguisticRelation(BaseModel):
    """Lexical-free structural relation used as the metamorphic parser contract."""

    source_path: list[str] = Field(default_factory=list)
    target_path: list[str] = Field(default_factory=list)


class LinguisticDocument(BaseModel):
    text: str
    tokens: list[LinguisticToken] = Field(default_factory=list)

    def token(self, index: int) -> LinguisticToken:
        for token in self.tokens:
            if token.index == index:
                return token
        raise KeyError(f"unknown linguistic token index {index}")

    def token_by_text(self, text: str) -> LinguisticToken | None:
        for token in self.tokens:
            if token.text == text:
                return token
        return None

    def root_path_signature(self, index: int) -> list[str]:
        """Return a lexical-free dependency path from a token toward its sentence root."""

        signature: list[str] = []
        seen: set[int] = set()
        current = self.token(index)
        while current.index not in seen:
            seen.add(current.index)
            signature.append(f"{current.pos}:{current.dependency}")
            if current.head_index == current.index:
                break
            try:
                head = self.token(current.head_index)
            except KeyError:
                break
            if head.sentence_index != current.sentence_index:
                break
            current = head
        return signature

    def normalized_relation(
        self,
        source_text: str | None,
        target_text: str | None,
    ) -> NormalizedLinguisticRelation:
        source = self.token_by_text(source_text) if source_text is not None else None
        target = self.token_by_text(target_text) if target_text is not None else None
        return NormalizedLinguisticRelation(
            source_path=(self.root_path_signature(source.index) if source is not None else []),
            target_path=(self.root_path_signature(target.index) if target is not None else []),
        )


class LinguisticFrontend(Protocol):
    """Thorn-owned contract for optional local grammatical analysis."""

    name: str

    def parse(self, text: str) -> LinguisticDocument: ...
