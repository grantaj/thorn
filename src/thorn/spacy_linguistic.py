from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from importlib import import_module
from typing import Protocol, cast

from thorn.linguistic import LinguisticDocument, LinguisticToken


class LinguisticFrontendUnavailable(RuntimeError):
    """Raised when an optional local linguistic backend cannot be loaded."""


class _TokenLike(Protocol):
    i: int
    text: str
    lemma_: str
    pos_: str
    dep_: str
    idx: int

    @property
    def head(self) -> _TokenLike: ...


class _SentenceLike(Protocol):
    def __iter__(self) -> Iterator[_TokenLike]: ...


class _DocLike(Protocol):
    @property
    def sents(self) -> Iterable[_SentenceLike]: ...

    def __iter__(self) -> Iterator[_TokenLike]: ...


class _Pipeline(Protocol):
    def __call__(self, text: str) -> _DocLike: ...


_ModelLoader = Callable[[str], _Pipeline]


def _default_loader(model_name: str) -> _Pipeline:
    try:
        spacy = import_module("spacy")
    except ModuleNotFoundError as exc:
        raise LinguisticFrontendUnavailable(
            "spaCy is not installed; install Thorn with the 'nlp' extra"
        ) from exc

    load = getattr(spacy, "load", None)
    if load is None:
        raise LinguisticFrontendUnavailable("installed spaCy package has no load() function")
    try:
        return cast(_Pipeline, load(model_name))
    except OSError as exc:
        raise LinguisticFrontendUnavailable(
            f"spaCy model {model_name!r} is not installed locally"
        ) from exc


class SpacyLinguisticFrontend:
    """Local spaCy adapter that immediately normalizes into Thorn-owned types."""

    name = "spacy"

    def __init__(
        self,
        model_name: str = "en_core_web_sm",
        *,
        loader: _ModelLoader | None = None,
    ) -> None:
        self.model_name = model_name
        self._loader = loader or _default_loader
        self._pipeline: _Pipeline | None = None

    def _model(self) -> _Pipeline:
        if self._pipeline is None:
            self._pipeline = self._loader(self.model_name)
        return self._pipeline

    def parse(self, text: str) -> LinguisticDocument:
        doc = self._model()(text)
        sentence_by_index: dict[int, int] = {}
        for sentence_index, sentence in enumerate(doc.sents):
            for token in sentence:
                sentence_by_index[token.i] = sentence_index

        tokens = [
            LinguisticToken(
                index=token.i,
                text=token.text,
                lemma=token.lemma_,
                pos=token.pos_,
                dependency=token.dep_,
                head_index=token.head.i,
                sentence_index=sentence_by_index.get(token.i, 0),
                start=token.idx,
                end=token.idx + len(token.text),
            )
            for token in doc
        ]
        return LinguisticDocument(text=text, tokens=tokens)
