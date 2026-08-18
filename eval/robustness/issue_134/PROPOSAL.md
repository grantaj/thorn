# Issue #134 pre-#125 A1/A2/A3 semantic-review baseline

## Status

**Frozen keylessly; live execution is not authorized by this document or by issue #134 itself.**

This experiment preserves the remaining issue #101 robustness measurements after the
two deterministic protocol/state repairs exposed by the first live attempts (#128
and #132), while deliberately staying before the source-context/canonical
representation change owned by #125.

The scientific purpose is sequencing. A2 has a known deterministic pre-#125
representation/source-reachability defect, but the production reviewer's behavior
on that impoverished packet is still useful evidence. Once #125 changes that
boundary, the same observation can no longer be recovered cleanly.

## Frozen assurance state

- Experiment ID: `issue-134-pre-125`
- Manifest: `eval/robustness/issue_134/manifest.json`
- Thorn assurance revision: `9201b33f73b84debf088548859d360be6a350585`
- Frozen `src/thorn` tree: `17b4af51d42e6c2268fff8279d5ed0edc895939c`
- Included repairs: #128 and #132
- Model: `gpt-5.6`
- Representation: `thorn-proof/1`
- Review protocol: `thorn-proof-review/2`
- Prompt: `proof_language_reviewer_v2`
- Prompt SHA-256:
  `6e69e97744b8667c06eb936aec931289050c1bbc691aa39c82780d8cecf05258`
- Source rescue: allowed once, at most 8 advertised addresses
- Implicit provider retries: zero
- Cases: exactly A1, A2, A3

C0 and B0 are intentionally not part of this continuation. Their accepted live
observations are already preserved by the issue #101 programme and are not to be
resampled merely for matrix completeness.

## Initial-input continuity

The A1/A2/A3 manuscript bytes, target identifiers, review target for A1, and
initial provider-request fingerprints are inherited exactly from
`eval/robustness/issue_101/manifest_post128.json`.

The keyless preflight reconstructs each initial request on the post-#132 tree and
requires the exact inherited fingerprint:

| Case | Initial request fingerprint |
| --- | --- |
| A1 | `a7b24f8782586dccec61f0833215abcc9568e77ca7136454dcd6cc5d8fc61b15` |
| A2 | `037375711aab3e2e976b9adbabf25aa61c0706421a7b98cd36f0827bdc36fd40` |
| A3 | `0c8ba6c4a8cbfc2d285384b896e65059f67d296d708f75986deaace3434d22a3` |

A mismatch is a stop condition, not an invitation to update the fingerprint.
That would indicate that the production semantic input changed between freezes and
must be explained before any paid continuation.

## Cases

### A1 — lemma indirection

Source:
`eval/robustness/issue_101/variant_lemma_indirection.tex`

Review target: `lem:uniformize`.

Question: with faithful context available, does review still identify the
uniformity/compactness defect when the decisive bad step is moved into an upstream
lemma? A miss must be classified at the earliest boundary rather than immediately
being called a model failure.

### A2 — prose-defined uniformity

Source:
`eval/robustness/issue_101/variant_prose_uniformity.tex`

The known pre-#125 condition is part of the experimental interpretation:
authoritative prose defining the relevant property and ambient domain is not
faithfully represented/reachable at the semantic-review boundary. #125 owns that
defect.

The live question is narrower: what does the current production reviewer actually
do with that impoverished packet? A clean result, irrelevant concern, unresolved
state, accidental correct diagnosis, or false finding are all measurements. None
would erase the independently established #125 fidelity defect.

### A3 — result applicability

Source:
`eval/robustness/issue_101/variant_result_applicability.tex`

Question: when the relevant context is faithful/reachable, does review detect that
a correct mathematical principle is used outside its hypotheses/domain?

## Frozen live bounds

A later separately authorized live run must use the checked-in runner without
widening these limits after observing output:

- at most 3 cases;
- at most 6 provider requests total;
- one initial request plus at most one bounded rescue request per case;
- aggregate input-token hard ceiling: 100,000;
- maximum output tokens per request: 4,096;
- aggregate output-token allowance: 24,576;
- at most 8 advertised source addresses in the single rescue request;
- zero implicit SDK retries;
- exact recording of every accepted provider exchange;
- immediate exact keyless replay;
- HTML report generation for each completed live and replay case.

Using the reference provider prices already recorded by Thorn on 2026-08-18
($5/M input, $30/M output), the absolute token-ceiling cost is $1.23728. This is
only a reference bound: official pricing must be checked again immediately before
any paid execution.

The input guard is applied before every actual request using cumulative
provider-reported input usage plus a conservative upper bound for the exact next
canonical request envelope. The full hypothetical two-turn stress bound is
diagnostic only; the runner does not reserve unseen rescue traffic in advance.

## Stop conditions

Stop before any provider call if:

1. `HEAD:src/thorn` differs from the frozen post-#132/pre-#125 tree;
2. any frozen manuscript SHA-256 differs;
3. any reconstructed initial request differs from the inherited post-#128
   fingerprint;
4. the production model, representation, protocol, prompt bytes, source-rescue
   contract, or output cap differs from the manifest;
5. the next request would exceed a request/token bound.

During execution, stop rather than adapt if a case would require another rescue,
the provider omits required usage accounting, or replay cannot consume the exact
recording keylessly.

Do not edit A1/A2/A3 after seeing model output and continue to call the result this
experiment. Do not inject manual source context. Do not special-case A2.

## Evidence capture

For each case, preserve:

- every exact provider request and response;
- request fingerprints and turn stages;
- model token usage;
- requested and actually rescued source addresses;
- final findings/dispositions;
- browsable HTML report;
- immediate replay result.

Afterward, independently adjudicate the mathematics and assign the earliest
applicable failure boundary from #134/#101:

1. source/extraction loss;
2. canonical representation/context loss;
3. proof-structure/scope loss;
4. rendering/salience loss;
5. source-reachability loss;
6. review-protocol/state loss;
7. model reasoning miss over demonstrably faithful context;
8. Lean/formalisation boundary issue;
9. report/UX concealment.

Do not patch a later layer to compensate for a demonstrated earlier fidelity
failure.

## Authorization boundary

The checked-in workflow exposes the same explicit `confirm_live` gate used by the
earlier robustness work, but merging this freeze does **not** authorize setting it.

Before a live dispatch:

1. this freeze/preflight must be merged and green;
2. issue #125 must still be unimplemented in the assurance tree;
3. official provider pricing must be checked;
4. the A1/A2/A3 live continuation must receive a separate explicit authorization.

After the pre-#125 live evidence is preserved and adjudicated, #125 may proceed.
The post-#125 A2 measurement, plus at least one independent held-out
prose-definition/ambient-convention case, must be a new freeze rather than a
mutation of this experiment.
