# Frozen live-experiment proposal for issue #101

**Status: proposal only. Do not execute without separate explicit authorization.**

The keyless tranche found one deterministic review-context loss (A2) and left B0/A1/A3 semantically unresolved because their decisive context reaches the production review boundary. A small live phase would answer a distinct question: when the context is faithful, does the current semantic reviewer identify the invariant uniformity/compactness defect, and does A2's impoverished packet produce a materially different result?

## Frozen inputs

Use the exact public files and hashes recorded in `manifest.json`:

| ID | role | review target | initial request fingerprint |
| --- | --- | --- | --- |
| C0 | clean control | `thm:uniform-decay` | `875811944da1e0157b800135bb6a84f488961837168f04c0ae70f5deeef226d1` |
| B0 | defective baseline | `thm:uniform-decay` | `e3e4fb3b3f62ef605c028f27d189d31db8a41ce4455e493e1c7cab00faf2c640` |
| A1 | lemma indirection | `lem:uniformize` | `a7b24f8782586dccec61f0833215abcc9568e77ca7136454dcd6cc5d8fc61b15` |
| A2 | prose-defined uniformity | `thm:uniform-decay` | `037375711aab3e2e976b9adbabf25aa61c0706421a7b98cd36f0827bdc36fd40` |
| A3 | result applicability | `thm:uniform-decay` | `0c8ba6c4a8cbfc2d285384b896e65059f67d296d708f75986deaace3434d22a3` |

Do not tune any source after seeing model output. H1 remains private held-out material and is deliberately excluded from the first authorized live batch.

## Thorn/model/protocol freeze

- Assurance code under test: public Thorn `79dc8b5986b0242240fcc2e5ab0de7437a08a9ff` (post-PR #123 / issue #10). The #101 branch only adds corpus/tests/docs and does not alter the production review architecture.
- Model: `gpt-5.6` (GPT-5.6 Sol alias).
- Model-facing representation: `thorn-proof/1`.
- Review protocol: `thorn-proof-review/2`.
- Semantic prompt version: `proof_language_reviewer_v2`.
- Source rescue: production closed-world `NEED_SOURCE`, at most one bounded rescue round, no manually supplied context beyond advertised addresses.
- Cache: disable cross-case semantic reuse for the experiment or start from an empty cache; record any within-case rescue state normally.

Before sending a request, regenerate it from the frozen source/revision and require the initial request fingerprint to equal the table above. Abort that case on mismatch.

## Request and cost cap

- Maximum cases: 5.
- Maximum provider requests: **10** total (one initial request plus at most one production rescue request per case).
- Aggregate input-token hard guard: **100,000** tokens across all requests. Abort before any request that would exceed it.
- Maximum output tokens: **1,500 per request**.
- Maximum aggregate output: 15,000 tokens.

Before any authorization, recalculate the upper-bound dollar cost from the then-current official provider pricing. The token/request ceilings above remain part of the frozen experimental design; a price change is not permission to expand them.

## Recorded evidence

For every request/response record:

- Thorn commit and dirty-state check;
- model identifier and service tier;
- prompt/protocol/representation versions;
- exact request fingerprint;
- advertised source addresses;
- whether `NEED_SOURCE` was requested and exact returned addresses;
- final semantic findings, category, severity, evidence anchors, and review-state/source-use fields;
- exact input/output/reasoning token accounting and actual cost;
- generated report and whether the finding is understandable and source-navigable to a mathematician.

Preserve provider records in the existing replay format so the experiment becomes exact-replayable without another paid call.

## Discriminating outcomes

The invariant mathematical adjudication is fixed independently of the model.

1. **C0 clean; B0/A1/A3 identify the same compactness/uniformity defect.** This supports the view that the faithful production representation is semantically adequate for these presentation variants; A2 remains an earlier representation/reachability defect (#125).
2. **A1 or A3 misses while B0 is caught despite faithful context.** Classify the earliest failure as layer 4 (packet salience) only if the relevant material is technically present but presentation makes it materially inaccessible; otherwise, with a faithful salient packet, classify as layer 8 model reasoning miss.
3. **A2 is clean/irrelevant/uncertain while B0 is caught.** This is predicted evidence that the already-proven layer-2/5 context loss matters in practice; it does not move the root cause to the model.
4. **C0 receives a material false positive.** This is a paired-control failure and blocks any claim that detecting defective variants is useful.
5. **All defective cases are missed with faithful packets.** This points to a semantic-review/model assurance gap rather than only #125.
6. **A2 is somehow correctly diagnosed from the impoverished packet.** That does not close #125: the result would rely on model inference rather than the source-faithfulness invariant, but it is useful empirical evidence about current reviewer robustness.

No adaptive manuscript change should be made inside the live batch. Any follow-on presentation change becomes a separately frozen experiment with new hashes/fingerprints and separate authorization.
