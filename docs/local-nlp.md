# Optional local linguistic analysis

Thorn's local NLP layer exists to recover **plausible grammatical structure**, not to decide mathematical meaning.

The boundary is:

```text
LaTeX frontend
  -> typed reversible mathematical projection
  -> Thorn-owned LinguisticFrontend
  -> spaCy dependency parser
  -> normalized Thorn linguistic relations
  -> ambiguity/evidence-bearing Math IR
```

Thorn owns the mathematical IR, exact source provenance, claims and support edges, uncertainty/evidence, and lint policy. spaCy supplies local tokenization, part-of-speech and dependency structure only. spaCy document/token objects are converted immediately into Thorn types and never appear in the Math IR.

## Core-only operation

The NLP layer is optional. Normal development and `thorn check` do not install or load spaCy:

```bash
pip install -e '.[dev]'
```

To experiment with local linguistic extraction, install the extra and an English spaCy model:

```bash
pip install -e '.[dev,nlp]'
python -m spacy download en_core_web_sm
```

Model installation may use the network once. Analysis itself loads the installed model locally and makes no API or model-service calls.

## Uncertainty contract

A local dependency parse is evidence, not a proof of intent. Thorn records structural candidates with one of:

- `confident`: independent structural evidence justifies using the relation as a deterministic premise;
- `ambiguous`: a plausible reading is supported, but another reading remains live;
- `unresolved`: Thorn retained the candidate/provenance but could not obtain enough normalized structure to prefer a reading.

Ambiguous and unresolved candidates preserve exact original source spans, nearby raw wording, the reason Thorn proposed the relation, and a lexical-free normalized dependency path when available. They are deliberately excluded from deterministic proof-support reachability/load-bearing calculations. **Ambiguity by itself is not a lint warning.**

For example, a theorem reference grammatically attached inside a proof sentence can be retained as an ambiguous support candidate even when the sentence may only be expository. Thorn does not patch that uncertainty with a growing list of phrases. A later `thorn review` pass can inspect the small source context and evidence attached to that candidate rather than rediscovering the paper's structure from scratch.

## Regression policy

`research/semantic-parser-bakeoff/cases.json` is the parser-independent metamorphic/adversarial oracle. The separate `Local NLP contract` workflow installs spaCy and checks the structural equivalences established in #29. Default CI remains lightweight, deterministic, paid-call-free, and independent of NLP models.

Real-paper regression remains private; the public parser corpus is synthetic.
