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
   Ambiguous structural proposals remain explicitly marked.
3. **Small hybrid.** The same dependency structure plus two intentionally small lexical guard
   families: definitional-verb lemmas and explicit ambient-scope prefixes. It also rejects
   dependency-visible negation/third-person `say`/active third-party `call` evidence.

No strategy creates authority. The benchmark does not perform scope resolution, term-use
closure, shadowing, or truth assessment.

## Evidence

The frozen phrase baseline can be run without an NLP model and currently scores 13/21
expected candidates, with 3 negative-control collisions: precision 0.812, recall 0.619,
lexical-challenge recall 0.125, zero provenance failures, and 1/2 transitive cases exposing
both declaration candidates.

The dependency and hybrid figures are intentionally produced by the existing heavier local
NLP CI path against pinned spaCy 3.8.14 + `en_core_web_sm`, rather than by a checked-in model
or a provider call. The final measured table is recorded below after that keyless run.

<!-- ISSUE160_METRICS_START -->
| strategy | precision | recall | false-authority risk | lexical-challenge recall | provenance failures | transitive cases |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| frozen #125 phrase | 0.812 | 0.619 | 3 | 0.125 | 0 | 1/2 |
| dependency structure | pending CI measurement | pending | pending | pending | pending | pending |
| small hybrid | pending CI measurement | pending | pending | pending | pending | pending |
<!-- ISSUE160_METRICS_END -->

## Hand-written grammar inventory and disposition

The evaluation is specifically intended to reduce handwritten phrase grammar, not move it.
The current production inventory and proposed #161 disposition are:

- **`called` / `said to be` / `we say` / `by ... we mean` phrase families:** do **not** grow
  these. If the hybrid evidence holds, #161 should replace them behind the existing boundary
  with dependency evidence plus the minimal definitional-anchor family.
- **Ambient convention cues:** retain one small explicit family. “Throughout”, “unless stated
  otherwise”, and section-wide language assert document scope; dependency structure alone
  cannot safely distinguish that from local exposition. Thorn must still own the resulting
  scope semantics.
- **Negation / grammatical subject guards:** retain as structural safety checks, not lexical
  mathematical grammar. They prevent obvious evidence inversion/third-party attribution.
- **Custom singular/plural term morphology in #125:** do not treat it as durable grammar.
  Mature linguistic lemmatization is a better candidate for #161, while Thorn keeps exact
  surface occurrences and identity/provenance.
- **Source exclusions (comments, verbatim, preamble):** retain at the source frontend/project
  fact layer. These are source-structure responsibilities, not linguistic grammar.

The migration itself is out of scope here. #160 should leave #161 a measured candidate
boundary and a finite grammar inventory, while production #125 behavior remains unchanged.
