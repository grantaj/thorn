# Semantic parser bake-off

Issue: #29

This experiment tests a fragile part of Thorn's offline architecture: recovering linguistic relationships between mathematical objects without turning the project into an ever-growing dictionary of English cue phrases.

## Principle

Thorn should own **mathematical types and provenance**, not reimplement general NLP.

The intended boundary is:

```text
LaTeX source
  -> source-preserving LaTeX frontend
  -> typed projection
       THORNRESULT1
       THORNEQUATION1
       THORNMATH1
       THORNREFERENCE1
  -> mature local linguistic/semantic parser
  -> normalized linguistic relations
  -> Thorn mathematical IR
```

The typed projection prevents a general English parser from having to understand TeX syntax. Every placeholder maps exactly back to the original source span. The NLP component is then evaluated only on the linguistic relation between those atomic mathematical objects.

## Ground truth

`cases.json` is parser-independent. It specifies semantic tasks such as:

- a result reference genuinely supports a claim;
- a result reference is merely expository and must **not** become support;
- one claim is presented as a consequence of a previous claim;
- a mathematical object is introduced, defined, or used as a trailing binder.

Equivalent paraphrases share the same expected relation. Adversarial controls deliberately contain misleading lexical overlap such as `so far`, `by the way`, `by contrast`, and expository references.

The benchmark must never define correctness in terms of a candidate parser's native tree labels.

## Candidate layers

The experiment is intentionally broader than a single parser API.

### Dependency parsing

- **spaCy**: lightweight Python/production baseline; MIT.
- **Stanza**: Universal Dependencies neural parser; Apache-2.0.

`run_dependency_bakeoff.py` measures how much pure dependency structure compresses the paraphrase problem without using predicate words in its signatures. In particular it reports the number of distinct structural templates required within each positive paraphrase family and whether positive templates collide with adversarial negatives.

A high template ratio is evidence that dependency parsing alone does not normalize enough semantics; it is not an invitation to add more Thorn-specific phrase rules.

### Discourse parsing

RST/PDTB-style discourse parsing is especially relevant to proof structure because it explicitly models relations such as cause, result, background, elaboration, contrast, and evidence-like connections between discourse units. IUDEX/DMRST is a current local candidate and should be evaluated against the cross-claim cases.

### Semantic role / semantic graph parsing

SRL and AMR are comparators for predicate-argument normalization. They should have to demonstrate useful paraphrase invariance and acceptable CPU/model cost before being considered production dependencies.

CoreNLP Natural Logic/OpenIE remains a useful research comparator, but its GPL licensing makes it unattractive as an embedded dependency if Thorn later has proprietary distributed components.

## Dependency policy

No candidate parser is a normal Thorn dependency during this experiment. Default CI remains small, deterministic, keyless, and model-free. Candidate packages and model downloads run only in the dedicated bake-off workflow.

The eventual recommendation must consider:

1. paraphrase invariance;
2. adversarial false positives;
3. source/provenance recoverability;
4. parser disagreement visibility;
5. CPU runtime and cold start;
6. model/download size;
7. packaging and licensing.

The goal is not to find the cleverest regex replacement. It is to determine the lightest mature linguistic layer that materially strengthens Thorn's mathematical IR.
