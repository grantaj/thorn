# Issue 213: non-dictionary graph-effect inference evaluation

## Decision

Do **not** promote the evaluated semantic-model path into Thorn production. Keep the current production path as implementation A and stop this research tranche at the admission boundary defined by #213.

The tested dictionary-free NLI route fails for two independent reasons:

1. graph-effect classification is not useful at any tested threshold; and
2. the model emits sentence-pair scores, not exact semantic argument spans, so it cannot ground `bind`, `payload`, or `REQUIRE` endpoints without adding a separate English-to-effect/argument mapping layer.

The second failure alone is sufficient to reject it as a source of canonical graph mutation. Adding a hand-maintained predicate/cue table after NLI would violate the central constraint of #213 rather than solve the problem.

No production dependency, frontend, authority rule, Q/P projection, report path, or default behavior is changed by this tranche.

## Question and boundary

#212 fixed the hypothesis under test as the small labelled graph

```text
G = (V, REQUIRE, bind, payload, visibility, status)
```

with construction operations

```text
DECLARE(v; bind, payload, visibility, status)
REQUIRE(u, v)
```

and with transitive `Closure` derived from `Direct`, not inferred as another primitive relation.

#213 asks whether maintained local semantic tooling can propose these graph effects from source-grounded mathematical prose without merely moving Thorn's English cue dictionary behind a parser.

The evaluated path therefore has only the finite graph-semantic labels `declare`, `require`, `visibility`, and `status`. The NLI hypotheses describe those effects semantically. There is no source-word, lemma, predicate, or phrase lookup table in the experiment.

## Corpus

The experiment reuses all 36 public source-preserving cases from #160 and adds 28 held-out #213 cases. The combined 64-case screen contains 34 cases with at least one positive graph effect and 30 negative cases.

The new held-outs cover:

- direct prerequisite wording around typed `THORNREF*` anchors;
- negation, quotation, attribution, historical mention, rhetorical mention, and stronger-but-unused references;
- local declaration and visibility changes;
- visibility retraction and scope termination;
- dependency status statements;
- deliberately unresolved lookalikes; and
- pressure cases for joint versus alternative support.

The held-out labels are graph effects, not speech-act categories. `Closure` is deliberately absent.

## Evaluated model path

The direct semantic candidate is the local NLI cross-encoder `cross-encoder/nli-deberta-v3-xsmall`, evaluated at exact model revision

```text
a150876415327c80daeff35ca6f68f5ed8cf5c24
```

The measured research environment was:

| Package | Version |
| --- | --- |
| sentence-transformers | 5.7.0 |
| transformers | 5.15.1 |
| torch | 2.13.0 |
| huggingface-hub | 1.28.0 |

The workflow ran with `OPENAI_API_KEY` empty. There were no provider/model API calls. Hugging Face was used only to fetch the model snapshot before local execution. A second run with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` reproduced the records and metrics exactly from the cached snapshot.

The semantic hypotheses and threshold grid were fixed before examining the output. After the strongly negative result, the hypotheses were **not** tuned against the same corpus. Rewording them repeatedly until the held-outs improve would turn the experiment into another manually optimized English recognition layer and would weaken the evidence.

## Baseline A: #160 declaration recognition

The frozen #160 measurements were re-run in the same workflow and reproduced exactly:

| Strategy | Precision | Recall | False-authority candidates | Lexical challenge recall | Provenance failures |
| --- | ---: | ---: | ---: | ---: | ---: |
| phrase/regex baseline | 0.812 | 0.619 | 3 | 0.125 | 0 |
| broad dependency structure | 0.396 | 0.905 | 29 | 0.750 | 0 |
| small hybrid | 0.750 | 0.857 | 6 | 0.625 | 0 |

Those numbers remain useful context rather than a directly equivalent score: #160 measures declaration candidates, whereas #213 asks the harder question of graph effects across declarations, prerequisites, visibility, and status.

## Effect inference result

For each sentence the NLI model scored all four graph-effect hypotheses independently. Thresholds were swept without selecting a post-hoc optimum.

| Entailment threshold | Effect precision | Effect recall | FP effects | FN effects | Unsafe negative cases | Negative false-authority rate | Lexical exact accuracy |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.50 | 0.111 | 0.070 | 24 | 40 | 7 | 0.233 | 0.050 |
| 0.60 | 0.167 | 0.070 | 15 | 40 | 5 | 0.167 | 0.050 |
| 0.70 | 0.091 | 0.023 | 10 | 42 | 4 | 0.133 | 0.000 |
| 0.80 | 0.000 | 0.000 | 4 | 43 | 2 | 0.067 | 0.000 |
| 0.90 | 0.000 | 0.000 | 1 | 43 | 1 | 0.033 | 0.000 |
| 0.95 | 1.000* | 0.000 | 0 | 43 | 0 | 0.000 | 0.000 |

`*` The apparent precision at 0.95 is vacuous: the model predicts no positive effect at all.

At threshold 0.50 the per-effect true positives were:

- `declare`: 0/24;
- `require`: 2/7;
- `visibility`: 1/10; and
- `status`: 0/2.

Raising the threshold reduces false authority only by eliminating the already sparse true positives. There is no operating point that approaches the #160 baseline's safety/usefulness tradeoff, let alone one that justifies a new production model stack.

Representative false-authority failures are also graphically material rather than cosmetic. For example, `negative-ref-stronger-direct` says that a stronger referenced result is *not* the proof being used, yet it remains a false positive through threshold 0.90. If admitted as `REQUIRE`, that error would change `Direct`, dependency provenance expectations, and downstream bounded review/source-rescue reachability.

## Argument and provenance grounding

Effect inference was measured separately from exact grounding, as required by #213.

The experiment retains exact source text and the reversible typed projection already used by the #160 corpus. That establishes where a sentence and its `THORNREF*`/`THORNMATH*` anchors came from; it does **not** tell Thorn which anchor fills which graph-semantic role.

The NLI cross-encoder returns no argument spans. Across the 34 positive-effect cases:

```text
model argument spans returned                       0
positive cases with exact semantic argument roles  0 / 34
semantic argument-grounding rate                   0.0
```

Consequently a candidate B graph cannot be constructed faithfully from these predictions. Doing so would require a second mechanism that maps English predicate/argument structure to `bind`, `payload`, and prerequisite endpoints. #160 already showed that generic dependency structure alone leaves precisely that policy in Thorn-owned lexical/structural rules.

This is a deliberate admission failure, not an omitted A/B test. Fabricating graph nodes or edges from “all typed placeholders in the sentence” would make the Q comparison meaningless and would weaken P by pretending to know relation provenance that the model did not supply.

## Q/P and downstream comparison

The #212 migration boundary requires both semantic equality under Q and faithful assurance correspondence under P before a replacement may become authoritative.

For this candidate:

- **A** is the current production semantic-dependency path;
- **B** reaches only non-authoritative sentence-level effect scores;
- B does not reach canonical `DECLARE`/`REQUIRE` mutation because exact arguments are unavailable;
- therefore no B semantic snapshot is admitted for `A ==Q B`;
- no P correspondence is claimed for graph relations that B cannot ground; and
- report/review behavior remains A's behavior unchanged.

This is the safe result. Forcing B across the boundary by hand-wiring typed references to predicted effects would be exactly the hidden cue/argument policy that #213 forbids.

## Pressure on the minimal calculus

The held-outs also exercise the counterexample families recorded in #212.

**Scope termination and retraction.** These remain legitimate pressure on the fixed `visibility` algebra. The evaluated model did not recover the retraction effect, so it provides no evidence for either extending or validating the calculus.

**Joint versus alternative support.** A flat pair of `REQUIRE` edges cannot by itself distinguish “both A and B are required” from “either A or B suffices.” #212 already excludes alternative sufficient-proof sets from current Q because Thorn asks for dependencies of the argument actually presented. The held-outs therefore preserve this as a future calculus witness rather than expanding the current primitive relation vocabulary.

**Status.** Both positive status held-outs were missed at every threshold that retained any useful recall. There is no evidence here for promoting a model-derived status mutation.

**Closure.** No model label exists for transitive closure. It remains derived from `Direct` as required by #212.

Nothing in this experiment justifies widening `G` or adding a new primitive semantic edge.

## Runtime, package cost, and offline feasibility

On the GitHub Ubuntu 24.04 / Python 3.11.16 runner, the first 256-pair run measured:

```text
inference                         3.263 s
total including snapshot/load   19.139 s
maximum RSS                  1,695,460 KiB
```

The cached offline replay measured:

```text
inference                         3.203 s
total including model load       3.955 s
maximum RSS                  1,276,512 KiB
```

The exact offline replay passed. Local/offline use is therefore technically feasible once the model is cached.

The research script's `snapshot_download` fetched the complete published repository at the pinned revision, measuring 2,268,597,330 bytes. That includes auxiliary published exports and is not a claim about the smallest possible deployment footprint. Because the semantic result already fails the safety/usefulness and grounding gates, this tranche deliberately stops rather than optimizing download/package layout for a model that should not enter production.

The Python stack also adds Sentence Transformers, Transformers, Torch, SciPy/scikit-learn and their transitive dependencies. No production dependency is added.

## Disposition

**Reject this NLI route for production graph mutation and stop #213 without adding a replacement semantic dependency.**

The evidence is stronger than “the score could be better”:

- there is no useful threshold operating point;
- false authority is substantial whenever recall is nonzero;
- `DECLARE`, the most common positive effect, has zero true positives;
- the model supplies no exact semantic argument grounding;
- admitting it would require the forbidden handwritten mapping layer; and
- the added runtime/package footprint has no compensating semantic benefit.

The current production path therefore remains authoritative. The graph-effect corpus and pinned research runner are retained as a regression/evaluation asset for a future genuinely semantic candidate. Any future candidate should be evaluated against the same admission rule: direct graph-effect improvement is not enough unless exact source-grounded arguments can cross Q and P without recreating a lexical dictionary.
