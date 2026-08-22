# Prose declaration recognition evaluation and production disposition

This document records the #160 comparison and the resulting #161 production decision.
The problem is grammatical/source evidence for prose declarations; mathematical
authority, scope, relevance, dependency identity and truth remain Thorn-owned.

## #160 comparison

All evaluated strategies consumed the same reversible linguistic projection and produced
source-addressable Thorn-owned candidates. The public corpus contains named-definition
paraphrases, ambient conventions, inline-math placeholders, transitive declaration
chains, exposition/history/quotation/negation controls, and excluded comment/verbatim
source.

The measured keyless local-NLP result was:

| strategy | precision | recall | false-candidate risk | lexical-challenge recall | provenance failures |
| --- | ---: | ---: | ---: | ---: | ---: |
| frozen #125 phrase baseline | 0.812 | 0.619 | 3 | 0.125 | 0 |
| broad dependency structure | 0.396 | 0.905 | 29 | 0.750 | 0 |
| small hybrid | 0.750 | 0.857 | 6 | 0.625 | 0 |

The phrase baseline was conservative but lexically brittle. Broad dependency structure
recovered more paraphrases but proposed far too many unsafe candidates. The small hybrid
provided the best architectural tradeoff: dependency-backed grammatical evidence with a
small lexical/scope guard surface.

The three held-out hybrid misses were intentionally not converted into a request for a
larger synonym grammar. In particular, missing `deemed` is evidence that the anchor list
must remain bounded rather than becoming a hand-maintained English thesaurus.

## #161 production disposition

Slices C and D implemented the #160 recommendation.

Production now uses `collect_project_prose_declarations()` and
`propose_linguistic_declarations()` behind `LinguisticFrontend`. The output is
`ProseDeclarationInventory` / `ProseDeclarationCandidate`: exact, ambiguous,
non-authoritative grammatical evidence. Slice D then moved prose mathematical authority
to a separate Thorn-owned policy consuming those candidates plus normalized source and
workspace facts.

The old five-family #125 phrase recognizer is **not** a production authority path. Its
regex constants survive only in `src/thorn/_frozen_declaration_benchmark.py` so the
research comparison remains reproducible.

Structural-only mode reports `ProseDeclarationCapability.REDUCED`; it does not silently
fall back to the old phrase recognizer.

## Production candidate grammar

The retained hand-written surface is deliberately small:

1. **Named-definition lemma anchors:** `call`, `term`, `say`, `mean`.
2. **Conditional structure:** bounded cues such as `if`, `when`, `whenever`,
   `provided` combined with normalized dependency evidence.
3. **Ambient-scope prefixes:** `throughout`, `in what follows`, `henceforth`,
   `unless stated otherwise`, `unless specified otherwise`, `for the remainder`.
4. **Safety guards:** bounded negation, passive/subject, and first-person/attribution
   checks.

This is candidate grammar only. It does not decide whether the subject is mathematical,
whether the statement is authoritative, or whether it is relevant to a theorem.

## Exact provenance and payload boundary

Each production candidate retains:

- exact declared term source;
- exact containing sentence source;
- exact proposed defining-payload source;
- normalized structural evidence and dependency path;
- explicit ambiguous status.

The payload span is an important #167 boundary. The authority layer can determine that a
declaration-shaped sentence lacks substantive defining content without reconstructing
English phrase grammar. A truncated or empty payload therefore stays non-authoritative.

## What was deliberately removed

The production architecture no longer relies on:

- independently growing `called`, `said to be`, `we say`, `by ... we mean`, and ambient
  phrase regex templates;
- bespoke singular/plural term variants as generic English morphology;
- broad dependency proposals as authority decisions;
- lexical lists intended to decide mathematical relevance or truth.

The frozen #125 benchmark is research-only and must not be imported into the production
authority path.

## Remaining ownership

`LinguisticFrontend` owns normalized grammatical evidence. The candidate layer owns only
its bounded grammatical proposal policy. Thorn's mathematical layer still owns:

- authority promotion;
- substantive-payload checks;
- project occurrence, scope, visibility and shadowing;
- materiality and actual use;
- semantic dependency identity and transitive closure;
- ambiguity policy and truth-independent assurance boundaries.

This separation is the production outcome of #160/#161, not a future migration plan.
