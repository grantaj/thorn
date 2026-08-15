# Local linguistic parser benchmark

Issue: #29

This directory preserves the parser-independent evidence behind Thorn's first local linguistic frontend decision. It is **research/benchmark material**, not a second production NLP stack.

## Architectural boundary

Offline Thorn should extract plausible mathematical structure, not resolve mathematical meaning.

```text
LaTeX source
  -> source-preserving LaTeX frontend
  -> typed reversible projection
       THORNRESULT1
       THORNEQUATION1
       THORNMATH1
       THORNREFERENCE1
  -> Thorn-owned LinguisticFrontend
  -> local dependency parser (spaCy first)
  -> normalized Thorn linguistic relations
  -> ambiguity/evidence-bearing Math IR
```

Thorn owns mathematical types, exact source provenance, claims/support edges, uncertainty/evidence, and lint policy. A linguistic parser supplies general grammatical/dependency structure only. Candidate-parser objects must not leak into Math IR.

## Durable benchmark artifacts

- `cases.json` is a 70-case parser-independent metamorphic/adversarial corpus.
- `src/thorn/semantic_projection.py` projects TeX/math/reference syntax into typed atomic placeholders while retaining exact reverse mappings to source spans.
- `tests/test_semantic_projection.py` checks that projection contract against both current LaTeX frontends.
- `run_dependency_bakeoff.py` is an optional research harness for comparing dependency parsers without making either parser a core Thorn dependency.

The benchmark is intentionally defined in terms of mathematical-prose relations rather than spaCy/Stanza-native dependency labels. Equivalent paraphrases share expected relations; adversarial controls deliberately reuse misleading surface words.

## Evidence and decision

The original successful spaCy 3.8.14 / `en_core_web_sm` 3.8.0 benchmark run over all 70 cases measured:

| task | positive | negative | positive dependency templates | positive/negative collisions |
| --- | ---: | ---: | ---: | ---: |
| definition | 7 | 0 | 4 | 0 |
| introduction | 13 | 0 | 3 | 0 |
| prior claim | 15 | 5 | 5 | 0 |
| result support | 16 | 8 | 11 | 3 |
| trailing binder | 6 | 0 | 1 | 0 |

A previous summary incorrectly described the 15 prior-claim positives as collapsing to one template. The preserved benchmark harness and original CI log show **five** templates with **zero adversarial collisions**. This document records the executable evidence rather than the mistaken summary.

The useful signal is still strong: six trailing-binder variants collapse to one structural template, 13 introduction phrasings reduce to three, and prior-claim paraphrases occupy only five templates without colliding with the five adversarial controls. The deliberately difficult area is result support: 16 positives occupy 11 templates and share three templates with eight expository controls. Thorn should preserve that ambiguity rather than patch it with lexical exceptions.

Stanza was exercised on the same dependency benchmark but did not add enough value to justify maintaining a second production parser. RST/discourse parsing, AMR, CoreNLP, and SRL remain possible research comparators, but their integration cost is not justified for Thorn's current goal.

**Production decision:** use spaCy dependency parsing as the first implementation behind a Thorn-owned `LinguisticFrontend` interface. Preserve support-vs-exposition uncertainty in the IR instead of patching the ambiguity with a larger cue-word dictionary.

## Dependency and CI policy

Nothing in this benchmark is allowed to make default CI depend on an NLP model or a remote service. Core Thorn must remain lightweight, deterministic, paid-call-free, and usable without spaCy.

Production spaCy/model tests belong in a separate heavier CI path introduced with #30. The parser-independent corpus remains the regression oracle and must not be weakened merely to make a parser pass. The heavy contract should reproduce the historical benchmark metrics above; a parser/model change that moves them requires investigation and an intentional benchmark update.

## Running the optional comparator

With a candidate parser and its English model already installed locally:

```bash
python research/semantic-parser-bakeoff/run_dependency_bakeoff.py \
  --candidate spacy \
  --output spacy-report.json
```

The harness also retains Stanza as a research comparator. This does not imply a supported production Stanza frontend.
