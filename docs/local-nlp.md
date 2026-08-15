# Local linguistic analysis

Thorn's local NLP layer exists to recover **plausible grammatical structure**, not to decide mathematical meaning. It is part of the normal user-facing frontend used by `thorn check` and `thorn review`.

The boundary is:

```text
LaTeX frontend
  -> typed reversible mathematical projection
  -> Thorn-owned LinguisticFrontend
  -> spaCy dependency parser
  -> normalized Thorn linguistic relations
  -> ambiguity/evidence-bearing Math IR
```

Thorn owns the mathematical IR, exact source provenance, claims and support edges, uncertainty/evidence, and lint policy. spaCy supplies local tokenization, part-of-speech and dependency structure only. spaCy document/token objects are converted immediately into Thorn types and never appear in the Math IR. Parser evidence is evidence about linguistic structure, not mathematical truth.

## Normal operation

spaCy is a normal Thorn runtime dependency. The small English language model is installed locally:

```bash
pip install -e '.[dev]'
python -m spacy download en_core_web_sm
```

After installation, manuscript analysis is local. Thorn does not call a remote NLP/model service, and `thorn check` needs no `OPENAI_API_KEY`.

Normal checking uses the linguistic frontend:

```bash
thorn check paper.tex
```

For debugging, constrained environments, and lightweight deterministic tests, the explicit degraded path is:

```bash
thorn check paper.tex --structural-only
```

`--structural-only` disables local linguistic parsing. It is deliberately named as a reduced mode rather than being the accidental default.

## Uncertainty contract

A local dependency parse is evidence, not a proof of intent. Thorn records structural candidates with one of:

- `confident`: independent Thorn-owned structural evidence justifies using the relation as a deterministic premise;
- `ambiguous`: a plausible reading is supported, but another reading remains live;
- `unresolved`: Thorn retained the candidate/provenance but could not obtain enough normalized structure to prefer a reading.

Ambiguous and unresolved candidates preserve exact original source spans, nearby raw wording, the reason Thorn proposed the relation, and a normalized dependency path when available. They are deliberately excluded from deterministic proof-support reachability and load-bearing calculations. **Ambiguity by itself is not a lint warning.**

For example, a theorem reference grammatically attached inside a proof sentence can be retained as an ambiguous support candidate even when the sentence may only be expository. Thorn does not patch that uncertainty with a growing list of phrases. A later `thorn review` pass can inspect the small source context and evidence attached to that candidate rather than rediscovering the paper's structure from scratch.

## Regression policy

`research/semantic-parser-bakeoff/cases.json` is the 70-case parser-independent metamorphic/adversarial corpus. The separate `Local NLP contract` workflow installs the real spaCy model and exercises all 70 cases, but its pass/fail contract is behavior Thorn owns:

- typed projection remains reversible and placeholders survive parsing;
- only Thorn-owned normalized structures cross the parser boundary;
- intended paraphrases reach equivalent Thorn relation kinds where justified;
- expository/adversarial controls never become confident mathematical support merely from parser or lexical evidence;
- unclear relations retain ambiguity, evidence, exact provenance, and nearby context;
- ambiguous edges stay out of deterministic support-graph reasoning;
- normal CLI execution actually uses the local linguistic frontend.

Raw dependency-template counts remain useful research diagnostics in the bake-off harness, but they are **not** production invariants: compatible dependency resolution can change those counts without changing the behavior Thorn should promise.

Default CI remains paid-call-free and does not load the language model. Parser-neutral fake frontends and `--structural-only` are used for lightweight tests; the dedicated NLP workflow owns the real model integration contract.

Real-paper regression remains private; the public parser corpus is synthetic.
