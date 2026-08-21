# Prose declaration recognition evaluation (#160)

## Decision boundary

This tranche evaluates how Thorn should obtain **grammatical/source evidence** for prose
semantic declarations. It does not change production recognition and it does not delegate
mathematical authority, scope, relevance, certainty, or truth to an NLP parser.

All alternatives consume the same source-preserving linguistic projection. Math/reference
syntax is represented by typed `THORN*` placeholders and every candidate is checked back to
an exact source occurrence. spaCy objects stop at `LinguisticFrontend`; the benchmark sees
only Thorn-owned `LinguisticDocument`/`LinguisticToken` values.

## Corpus

`research/semantic-parser-bakeoff/declaration_cases.json` contains 36 public cases and 21
expected grammatical candidates. It covers:

- named-definition paraphrases across unrelated adjective/noun vocabulary;
- explicit ambient conventions, including a theorem-scope use that need not repeat the noun;
- real LaTeX math fragments mapped reversibly to typed placeholders, including math before
  the declared term so offset fidelity is non-trivial;
- two transitive declaration chains, without asking the parser to decide their semantic edge;
- exposition, history, third-party terminology, quotations, negation, theorem/proof mentions,
  locally scoped conventions, and declaration-shaped non-mathematical descriptions;
- comment/verbatim controls represented by source-length-preserving masked views.

The corpus labels *candidate grammatical evidence*, not mathematical authority. A false
positive is therefore reported as **false-authority risk**: it is a candidate that would be
unsafe to promote mechanically.

## Strategies

1. **Frozen #125 phrase baseline.** The benchmark imports the five production regex families
   unchanged: `called`, `said to be`, `we say`, `by ... we mean`, and ambient-cue syntax.
2. **Dependency structure.** Three small lexical-light structural rules over
   `LinguisticDocument`: conditional predicate, preposed `mean`, and scoped copular subject.
   Broad structural proposals remain explicitly marked ambiguous.
3. **Small hybrid.** The same dependency structure plus two intentionally small lexical guard
   families: definitional-verb lemmas and explicit ambient-scope prefixes. It also rejects
   dependency-visible negation and obvious third-party attribution.

No strategy creates authority. The benchmark does not perform scope resolution, term-use
closure, shadowing, relevance, or truth assessment.

## Evidence

Measurements use the repository's pinned keyless local-NLP path (spaCy 3.8.14 with
`en_core_web_sm` 3.8.0). The frozen phrase baseline itself needs no NLP model.

| strategy | precision | recall | false-authority risk | lexical-challenge recall | provenance failures | transitive cases |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| frozen #125 phrase | 0.812 | 0.619 | 3 | 0.125 | 0 | 1/2 |
| dependency structure | 0.396 | 0.905 | 29 | 0.750 | 0 | 1/2 |
| small hybrid | 0.750 | 0.857 | 6 | 0.625 | 0 | 1/2 |

The phrase recognizer is conservative but lexically brittle: it finds 13/21 expected
candidates and only one eighth of the deliberately held-out lexical variants. Its three
negative-control collisions also show that matching declaration-shaped phrasing is not the
same thing as establishing mathematical authority.

The broad dependency recognizer finds 19/21 expected candidates, but emits 29 false candidates
and marks all 48 proposals structurally ambiguous. Its 0.905 recall is useful as evidence that
dependency structure generalizes across paraphrase, but its 0.396 precision makes it unsuitable
as an authority-like recognizer or as an unguarded candidate boundary.

The small hybrid finds 18/21 expected candidates. Relative to the phrase baseline, recall rises
from 0.619 to 0.857 and lexical-challenge recall rises from 0.125 to 0.625. Relative to broad
dependency structure, false-authority risk falls from 29 candidates to 6. The remaining six
collisions are informative rather than invitations to grow grammar:

- `negative-useful` is first-person declaration-shaped exposition (`We say that balanced maps
  are useful ...`);
- `negative-display-label` and `negative-called-metaphor` are valid passive `called ... when`
  constructions whose subjects are not mathematically authoritative dependencies;
- `negative-quotation` quotes declaration syntax from another paper;
- `named-math-before` and `transitive-hybrid` expose dependency-sensitive term selection and
  therefore produce a wrong candidate while also missing the expected occurrence.

The three hybrid misses are `named-deemed`, `named-math-before`, and `transitive-hybrid`.
`named-deemed` is the deliberate cost of not turning the lexical anchor family into a synonym
list. The other two show that exact candidate identity still needs Thorn-owned provenance and
ambiguity handling even when a parser supplies useful syntax.

All three strategies have zero provenance failures on the corpus. Typed placeholders before
and after declaration terms map back to the exact source occurrence, and source-excluded
comment/verbatim material remains excluded. Neither dependency parsing nor the hybrid improves
the 1/2 transitive-chain score enough to justify moving semantic closure or dependency identity
into NLP.

## Disposition

**Recommend the small hybrid as concrete input to #161, but do not migrate production behavior
in #160.** The evidence rejects both extremes:

- do not grow the #125 phrase grammar to chase paraphrase recall;
- do not treat broad dependency-parser proposals as authoritative declaration candidates.

A #161 consolidation should instead consider a dependency-backed candidate-evidence layer
behind the existing `LinguisticFrontend`, with a deliberately small Thorn-owned guard surface.
Its output must remain non-authoritative evidence carrying exact occurrence provenance and
explicit ambiguity. Thorn continues to decide mathematical authority, relevance, scope,
visibility/shadowing, dependency identity/closure, and truth.

Production #125 behavior remains unchanged by this tranche.

## Hand-written grammar inventory and justification

The evaluation supports keeping only the following bounded hand-written families as possible
#161 inputs:

1. **Definitional-anchor family.** A small lemma category such as `call` / `term` / `say` /
   `mean`, used to guard dependency structure rather than encode sentence templates. The 29
   broad-dependency collisions justify a lexical guard; the `deemed` miss is evidence against
   expanding it into an open-ended synonym grammar.
2. **Ambient-scope anchor family.** A small explicit family for document/section-scoping cues
   such as `throughout`, `in what follows`, `unless stated otherwise`, `for the remainder`, and
   `henceforth`. Generic dependency structure cannot safely distinguish these from local
   exposition, and the eventual scope semantics remain Thorn-owned.
3. **Negation and grammatical-attribution guards.** Structural safety checks for negation and
   obvious third-party attribution. These are bounded grammatical checks, not mathematical
   authority rules.
4. **Source exclusions/projection rules.** Comments, verbatim-like regions, preamble material,
   quotation/source context where available, and typed math/reference placeholders belong at
   the source/projection boundary. They should remain explicit because the linguistic parser
   must never be asked to reconstruct excluded source or provenance.

The following should **not** be preserved as architectural grammar families:

- the four named #125 phrase-regex templates (`called`, `said to be`, `we say`, `by ... we
  mean`) as independently growing patterns;
- custom singular/plural term morphology as a substitute for mature linguistic lemmatization;
- broad dependency structure as an authority decision;
- lexical lists intended to decide whether a declaration is mathematically relevant or true.

If #161 adopts a parser-backed candidate layer, exact surface text and occurrence provenance
must still be retained even where mature linguistic lemmatization is used for matching.
