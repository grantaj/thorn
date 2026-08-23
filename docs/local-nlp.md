# Local linguistic analysis

Thorn's local NLP layer recovers **source-mapped grammatical observations**. It does not
decide mathematical meaning, authority, scope, relevance, dependency identity, or truth.

The post-#207 production path is:

```text
LatexFrontend / FrontendRegion facts
        |
        v
reversible LinguisticProjection
        |  typed math/reference placeholders + exact source mapping
        v
LinguisticFrontend
        |  Thorn-owned LinguisticDocument / LinguisticToken
        v
source-mapped statements + bounded support uncertainty
        |
        +--> advisory context / review retrieval
        |
        v
Thorn mathematical authority and elaboration policy
        |
        v
Symbol IR / canonical Proof IR
        |
        +--> thorn-proof/1 / bounded review
        `--> Lean handoff
```

spaCy supplies local tokenization, part-of-speech, lemmas and dependency structure.
spaCy objects are converted immediately into Thorn-owned types and never become
canonical mathematical semantics.

## Normal operation

spaCy is a normal Thorn runtime dependency. The small English model is installed
locally:

```bash
pip install -e '.[dev]'
python -m spacy download en_core_web_sm
```

Normal keyless commands use the linguistic frontend:

```bash
thorn analyze paper.tex
thorn ir paper.tex --format json
```

For constrained environments and intentionally reduced deterministic testing:

```bash
thorn analyze paper.tex --structural-only
```

`--structural-only` disables local linguistic parsing. It is an explicit reduced
capability mode, not a silent substitute for the normal path.

## Reversible source projection

`build_linguistic_projection()` consumes normalized source-region facts from
`LatexFrontend`. Comments, preamble/non-document material and opaque/verbatim source are
excluded before linguistic parsing. Math and reference syntax is represented with typed,
offset-preserving placeholders.

Linguistic observations map back to exact original `SourceSpan` provenance. The
linguistic parser is never asked to rediscover LaTeX comments, math delimiters, or source
offsets. If the frontend cannot establish complete trustworthy source regions, the
projection is partial and downstream use fails closed.

## Source-mapped statements and advisory context

`collect_project_linguistic_statements()` is the production prose substrate. It records
exact source statements, their scope and normalized linguistic segmentation without
promoting their content to mathematical authority.

Those statements may be ranked into bounded advisory context for review. The ranking
layer can decide which already-source-mapped statements are useful to show, but it does
not turn them into definitions, symbols, dependencies, or proof facts. #204-#207 tested
and removed the older production prose-declaration interpretation path while preserving
this source-addressable substrate.

## No generic linguistic symbol interpretation

Local NLP is not a symbol extractor. In particular, declaration-shaped prose such as
"Fix $x\in X$" remains exact reviewable source, but a dependency parse does not create a
`SymbolIntroductionCandidate` or otherwise modify deterministic `SymbolTable` state.
Issue #203 removed that generic interpretation after a bounded ablation showed that the
source evidence survives independently.

Explicit mathematical declarations, scope, visibility, shadowing, symbol resolution and
project occurrence semantics remain Thorn-owned. They are derived from the normalized
source/workspace facts and the deliberately bounded mathematical authority layer, not
from generic English morphology.

## Support uncertainty

The local frontend may still contribute bounded grammatical evidence when Thorn is
classifying already-identified proof-support structure. Such evidence remains explicit
uncertainty; it does not invent support edges or promote unsupported prose into
mathematical authority.

When stronger independent evidence justifies a mathematical operation, canonical Proof
IR records the mathematical operation—not a spaCy dependency path. Parser-native
vocabulary must not shape canonical Proof IR or Lean output.

## Authority is a separate Thorn decision

No NLP layer decides:

- whether a statement is mathematically authoritative;
- whether it introduces a mathematical symbol;
- whether it is load-bearing;
- its project scope or shadowing behavior;
- transitive dependency closure;
- whether a theorem is true.

This is also a no-confidence-laundering rule: an uncertain linguistic observation does
not become more certain merely because a later layer renders it in compact IR, a review
request, or a formal-looking syntax.

## Structural-only capability

With no linguistic frontend, structured LaTeX/result, workspace, symbol and dependency
semantics continue to work. Source-mapped linguistic statements and linguistic
uncertainty are unavailable. There is no fallback handwritten English parser.

Tests that require Local NLP therefore configure it explicitly. A lighter mode must not
pretend to have recovered grammatical observations it never computed.

## Relationship to model review

Local NLP is not the provider/model layer. It is local deterministic preprocessing.
Model-backed review happens downstream over canonical Thorn state and the stable
`thorn-proof/1` projection. Normal review is result-level; the targeted uncertainty
selector survives only as an explicit `thorn-eval` diagnostic/evaluation view.

Provider adapters never receive spaCy objects and never use NLP to select mathematical
authority.

## Relationship to Lean

The Lean handoff may use only mathematical structure Thorn has mechanically recovered.
Linguistically plausible but unresolved content remains an explicit unsupported/hole
boundary rather than being guessed into compilable proof code.

## Regression policy

`research/semantic-parser-bakeoff/` contains the public parser-independent
metamorphic/adversarial corpus. The Local NLP workflow installs the real spaCy model and
checks Thorn-owned behavior, including:

- reversible typed source projection;
- no parser-native object leakage;
- exact source-mapped statement provenance;
- linguistic observations remaining non-authoritative;
- normal CLI linguistic execution;
- structural-only reduced capability;
- keyless targeted-preflight compatibility;
- downstream Proof IR independence from parser-native vocabulary.

Historical declaration-recognizer comparisons remain research evidence rather than
production invariants. Real-paper regression remains private; the public corpus is
synthetic.
