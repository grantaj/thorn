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

The 70-case experiment established enough signal to stop the open-ended parser bake-off:

- spaCy collapsed 15 prior-claim conclusion paraphrases to one structural dependency template with zero adversarial collisions;
- six trailing-binder variants collapsed to one template;
- 13 introduction phrasings reduced to three templates;
- result-support language remains structurally confusable with deliberately expository controls.

Stanza was exercised on the same dependency benchmark but did not add enough value to justify maintaining a second production parser. RST/discourse parsing, AMR, CoreNLP, and SRL remain possible research comparators, but their integration cost is not justified for Thorn's current goal.

**Production decision:** use spaCy dependency parsing as the first implementation behind a Thorn-owned `LinguisticFrontend` interface. Preserve support-vs-exposition uncertainty in the IR instead of patching the ambiguity with a larger cue-word dictionary.

## Dependency and CI policy

Nothing in this benchmark is allowed to make default CI depend on an NLP model or a remote service. Core Thorn must remain lightweight, deterministic, paid-call-free, and usable without spaCy.

Production spaCy/model tests belong in a separate heavier CI path introduced with #30. The parser-independent corpus remains the regression oracle and must not be weakened merely to make a parser pass.

## Running the optional comparator

With a candidate parser and its English model already installed locally:

```bash
python research/semantic-parser-bakeoff/run_dependency_bakeoff.py \
  --candidate spacy \
  --output spacy-report.json
```

The harness also retains Stanza as a research comparator. This does not imply a supported production Stanza frontend.
