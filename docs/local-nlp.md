# Local linguistic analysis

Thorn's local NLP layer exists to recover **plausible grammatical evidence**, not to decide mathematical meaning. It is part of the normal frontend used to build rich Math IR for `thorn analyze`, `thorn ir`, and downstream elaboration/review work.

The boundary is:

```text
LaTeX frontend
  -> typed reversible mathematical projection
  -> Thorn-owned LinguisticFrontend
  -> spaCy dependency parser
  -> normalized Thorn linguistic relations
  -> ambiguity/evidence-bearing Math IR
  -> partial mathematical elaboration
  -> canonical typed Proof IR
```

Thorn owns the mathematical IR, exact source provenance, claims and support edges, uncertainty/evidence, elaboration policy, canonical Proof IR, and diagnostic policy. spaCy supplies local tokenization, part-of-speech and dependency structure only.

spaCy document/token objects are converted immediately into Thorn types and never become canonical mathematical semantics. Parser evidence is evidence about linguistic structure, not mathematical truth.

## Architectural role

The local NLP layer is an **evidence producer for partial elaboration**.

It can help Thorn notice that prose plausibly introduces a variable, attaches a qualifier, names a reason, or links one claim to another. It should not force those candidates into mathematical certainty.

When stronger independent evidence lets Thorn recover a mathematical operation safely, canonical Proof IR should encode that operation structurally. For example, a linguistic cue may help identify a candidate witness-introduction phrase, but the canonical representation should eventually contain a witness operation with symbol identity, obligation, and provenance—not a spaCy dependency path.

This is an important anti-regression boundary: do not make the canonical Proof IR parser-shaped merely because local NLP was useful in discovering the source relation.

## Normal operation

spaCy is a normal Thorn runtime dependency. The small English language model is installed locally:

```bash
pip install -e '.[dev]'
python -m spacy download en_core_web_sm
```

After installation, frontend analysis is local. `thorn analyze` and `thorn ir` require no API key.

```bash
thorn analyze paper.tex
thorn ir paper.tex --format json
```

For debugging, constrained environments, and lightweight deterministic tests, the explicit reduced path is:

```bash
thorn analyze paper.tex --structural-only
```

`--structural-only` disables local linguistic parsing. It is deliberately named as a reduced mode rather than being the accidental default.

## Uncertainty contract

A local dependency parse is evidence, not a proof of intent. Thorn records structural candidates with one of:

- `confident`: independent Thorn-owned structural evidence justifies using the relation as a deterministic premise;
- `ambiguous`: a plausible reading is supported, but another reading remains live;
- `unresolved`: Thorn retained the candidate/provenance but could not obtain enough normalized structure to prefer a reading.

Ambiguous and unresolved candidates preserve exact original source spans, nearby raw wording, the reason Thorn proposed the relation, and a normalized dependency path when available. They are deliberately excluded from deterministic proof-support reachability and load-bearing calculations. **Ambiguity by itself is not a diagnostic.**

For example, a theorem reference grammatically attached inside a proof sentence can be retained as an ambiguous support candidate even when the sentence may only be expository. Later elaboration or AI review can inspect that evidence rather than rediscovering the paper's structure from scratch.

The same principle applies to canonical Proof IR: if linguistic evidence is insufficient to establish a binding, proof rule, or semantic operation, keep the uncertainty explicit rather than guessing merely to obtain a more formal-looking graph.

## Relationship to AI

Local NLP is not the AI layer.

It runs locally and deterministically and contributes evidence to Thorn-owned structures. Model-backed semantic reasoning happens downstream, after Thorn has extracted and, where possible, elaborated the mathematical structure.

The intended long-term interface to an LLM is therefore not a dump of spaCy relations. It is a compact deterministic projection of canonical Proof IR, with bounded source-on-demand for unresolved material.

## Regression policy

`research/semantic-parser-bakeoff/cases.json` is the parser-independent metamorphic/adversarial corpus. The separate `Local NLP contract` workflow installs the real spaCy model and exercises it, but the pass/fail contract is behavior Thorn owns:

- typed projection remains reversible and placeholders survive parsing;
- only Thorn-owned normalized structures cross the parser boundary;
- intended paraphrases reach equivalent Thorn relation kinds where justified;
- expository/adversarial controls never become confident mathematical support merely from parser or lexical evidence;
- unclear relations retain ambiguity, evidence, exact provenance, and nearby context;
- ambiguous edges stay out of deterministic support-graph reasoning;
- normal CLI execution actually uses the local linguistic frontend;
- downstream Proof IR must not depend on parser-native vocabulary or object identity.

Raw dependency-template counts remain useful research diagnostics, but they are not production invariants. Real-paper regression remains private; the public parser corpus is synthetic.
