# Local linguistic analysis

Thorn's local NLP layer recovers **plausible grammatical evidence**. It does not decide
mathematical meaning, authority, scope, relevance, dependency identity, or truth.

After #161 the normal source-to-linguistic path is:

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
normalized support/symbol/declaration candidates
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

Every downstream linguistic candidate can therefore map its term, sentence, evidence,
and relevant payload back to exact original `SourceSpan` provenance. The linguistic
parser is never asked to rediscover LaTeX comments, math delimiters, or source offsets.
If the frontend cannot establish complete trustworthy source regions, the projection is
partial and declaration authority fails closed.

## Production prose-declaration candidate boundary

#160 compared the frozen phrase recognizer, broad dependency proposals and a deliberately
small hybrid. #161 Slice C productionized the useful part of that hybrid behind
`LinguisticFrontend`; Slice D moved mathematical authority onto its normalized output.

`collect_project_prose_declarations()` produces a `ProseDeclarationInventory` whose
capability is one of:

- `complete`: candidate evidence is available over complete reversible source facts;
- `reduced`: no `LinguisticFrontend` is configured, so prose declaration candidates are
  unavailable;
- `partial`: source/projection evidence is incomplete and cannot safely support
  declaration authority.

Each `ProseDeclarationCandidate` is explicitly non-authoritative and carries:

- role (`definition` or `ambient`);
- exact declared-term source;
- exact source sentence;
- exact proposed defining-payload source;
- normalized structural evidence and dependency-path evidence;
- `InferenceStatus.AMBIGUOUS`.

The exact payload span is important. It lets Thorn apply the #167 substantive-definition
rule without rebuilding English grammar in the authority layer: declaration-shaped
syntax with no substantive defining complement remains evidence only.

## Bounded hand-written grammar

The production candidate layer deliberately keeps a small guard surface rather than a
phrase-template grammar.

Named-definition proposals use normalized dependency structure plus the bounded lemma
family:

```text
call, term, say, mean
```

Conditional forms use a bounded structural cue family such as:

```text
if, when, whenever, provided
```

Ambient-scope proposals use explicit prefixes:

```text
throughout
in what follows
henceforth
unless stated otherwise
unless specified otherwise
for the remainder
```

The layer also applies bounded grammatical safety guards for negation, passive/subject
shape and obvious first-person/attribution structure.

These anchors exist because #160 showed that broad dependency structure had much higher
candidate recall but unacceptable false-candidate risk. They **do not** encode
mathematical relevance or authority. The deliberate `deemed` miss in the #160 corpus is
evidence against expanding this into an open-ended synonym list.

The retired five-family #125 phrase templates and bespoke singular/plural term morphology
are not production authority machinery. Their frozen regex constants survive only in
`_frozen_declaration_benchmark.py` so the #160 research comparison remains reproducible.

## Authority is a separate Thorn decision

A grammatical proposal is not a definition merely because spaCy or the bounded hybrid
recognized its shape.

The authority layer separately requires trustworthy source/workspace facts, complete
candidate capability, substantive defining content, valid visibility/shadowing at the
specific project occurrence, and actual mathematical use/relevance. Ambiguous evidence
stays ambiguous until Thorn-owned policy has sufficient independent facts to promote a
canonical declaration.

No NLP layer decides:

- whether a statement is mathematically authoritative;
- whether it is load-bearing;
- its project scope or shadowing behavior;
- transitive dependency closure;
- whether a theorem is true.

## Structural-only capability

With no linguistic frontend, `ProseDeclarationInventory` is `REDUCED`. Structured
LaTeX/result semantics continue to work, but prose declaration authority is unavailable.
There is no fallback to the old unconditional phrase recognizer.

Tests that require prose authority therefore advertise/use an NLP-capable contract
configuration. This is intentional capability honesty: a lighter mode must not pretend
to have recovered grammatical evidence it never computed.

## Other linguistic evidence

The local frontend also supports non-authoritative support and symbol candidates. It can
help Thorn notice plausible variable introductions, qualifiers, grammatical attachments,
or references. Those candidates carry exact provenance and uncertainty and do not become
confident mathematical support merely because a dependency parse exists.

When stronger independent evidence justifies a mathematical operation, canonical Proof
IR records the mathematical operation—not a spaCy dependency path. Parser-native
vocabulary must not shape canonical Proof IR or Lean output.

## Uncertainty contract

Linguistic evidence may be `confident`, `ambiguous`, or `unresolved` according to the
specific downstream contract. Ambiguous and unresolved candidates retain exact original
source, nearby wording and normalized structural evidence. They are not correctness
defects by themselves.

This is also a no-confidence-laundering rule: an uncertain linguistic proposal does not
become more certain merely because a later layer renders it in compact IR, a review
request, or a formal-looking syntax.

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
- exact declaration-candidate term/source/payload provenance;
- candidate ambiguity remaining non-authoritative;
- normal CLI linguistic execution;
- structural-only reduced capability;
- keyless targeted-preflight compatibility;
- downstream Proof IR independence from parser-native vocabulary.

Raw dependency-template counts remain research diagnostics rather than production
invariants. Real-paper regression remains private; the public corpus is synthetic.
