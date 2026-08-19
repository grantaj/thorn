# A3 post-provider-audit pre-#125 result

Issue: #134

This document preserves the completed A3 scientific observation after the provider-boundary audit (#145/#146), the canonical execution-contract work (#147), the Structured Outputs subset repair (#149/#150), and a successful two-profile provider-readiness canary.

A1 and A2 are not resampled here. Their accepted pre-#125 observations remain the measurements already preserved under #134. Issue #125 was still unimplemented when this A3 observation was made.

## Frozen experiment

The scientific manifest is `a3_post146_manifest.json`.

- experiment: `issue-134-a3-post146-pre125-20260819`
- production revision: `f9696daf6ca828f2a25b7d4d921513e057d4e125`
- production `src/thorn` tree: `9143b4063cd42269370fd365e315473655989583`
- model: `gpt-5.6`
- representation: `thorn-proof/1`
- protocol: `thorn-proof-review/2`
- prompt: `proof_language_reviewer_v2`
- provider runtime: Python 3.11.16, OpenAI 3.3.0, Pydantic 2.13.4, exact packaged provider lock
- source: `eval/robustness/issue_101/variant_result_applicability.tex`
- source SHA-256: `f53d7c5eed1f0145406c3c4dda50680a852b14c2c4cd3705c17940ec5f27f403`
- target: `thm:uniform-decay`
- initial execution fingerprint: `996dbae0c3d2b86f33c00b099612c0be9e9792556b7d3a35667fdff9b803ccbf`
- max provider attempts: 2
- max aggregate input tokens: 40,000
- max output tokens/request: 4096
- max aggregate output tokens: 8192
- provider retries: 0

The manifest itself never authorizes paid execution. The separate one-shot authorization claim is preserved in `a3_post146_paid_claim.json`.

## Provider readiness prerequisite

The freeze was constructed only after successful provider-readiness run `32232914558`.

- readiness artifact: `9357906140`
- readiness artifact digest: `sha256:94869b989954b922c69398e544f31f6ac3f7486efe6bbed3569d5d21ec10e9cb`
- readiness `live.json` SHA-256: `a1de222ac38133c05d638a9329c5652949380bea88497f1749c03b4862f20767`
- readiness status: `live-success`
- profiles exercised: initial plus rescue
- attempts/responses/generations: 2 / 2 / 2
- retries: 0
- replay: verified keylessly

The canonical manifest builder re-verified that this readiness evidence covered A3's scientific transport contract before allowing the freeze.

## Scientific execution

The authorized A3 run was GitHub Actions run `32246878348`, job `96049224526`.

Artifact:

- artifact ID: `9362936368`
- artifact name: `issue-134-a3-authorized-32246878348`
- artifact digest: `sha256:077d5ad92f156395c99ac2f0a0672c4d504500b9d1d8c71dd26d5fc8f3a2fdd8`

The run used exactly one provider request. No source rescue was required.

Usage:

- provider attempts: 1
- responses received: 1
- known model generations: 1
- input tokens: 1,904
- output tokens: 643
- total tokens: 2,547
- retries: 0

At the official standard GPT-5.6 Sol prices checked immediately before execution ($5/M input, $30/M output), this is $0.02881 USD before any cached-input discount.

## Model result

Thorn returned one final error finding:

> **The asserted uniform bound on [0,1) is false.**

The reviewer gave the explicit counterexample: fix `epsilon = 1/2`; for every proposed `N >= 1`, choose `x` with `(1/2)^(1/N) < x < 1` and take `n=N`. Then `x in [0,1)` but `x^n > 1/2`, contradicting the claimed uniform bound.

The finding also identified the intended applicability defect rather than merely observing that the theorem is false: the local point-dependent bounds cannot be promoted to one uniform `N`, and the indicated finite-cover step cannot justify the promotion because `[0,1)` is not compact. Thus the principle stated for compact intervals is being used outside its hypotheses.

The recorded finding was:

- ID: `F1`
- category: `counterexample`
- severity: `error`
- confidence: `0.99`
- evidence cited: `D1`, `T0`, `R1`, and `P1/U3`

Although the machine category is `counterexample`, the explanation explicitly diagnoses the result-applicability/hypothesis failure that A3 was designed to test.

## Independent mathematical adjudication

**A3 is a successful detection.**

The source states the finite-cover principle only for a compact interval, then applies it to the bounded but noncompact interval `I=[0,1)`. That application is invalid. The theorem itself is also false, and the reviewer's counterexample is correct.

The model-facing packet contains the load-bearing domain `I=[0,1)`, the local pointwise-neighbourhood result, the finite-cover dependency, the attempted maximum construction, and the uniform target. The reviewer therefore had enough faithful context to identify the defect without source rescue.

There is no failed earlier review boundary to assign for this observation: provider transport, structured response validation, representation, and replay all completed successfully. The semantic reviewer correctly identified the mathematical defect over the supplied context.

## Replay

Immediate replay over the accepted recording completed successfully and made no provider request:

- replay status: `completed`
- replay provider attempts: 0
- replay hits: 1
- replay input/output tokens: 0 / 0
- replay finding: exactly the same `F1`

The accepted exchange fingerprint is `996dbae0c3d2b86f33c00b099612c0be9e9792556b7d3a35667fdff9b803ccbf`.

## Pre-#125 baseline conclusion

The remaining #134 pre-#125 baseline is now complete:

- A1: defect detected despite lemma indirection; preserved prior measurement.
- A2: bounded reviewer correctly left the material question unresolved because the authoritative prose definition/domain is absent from the pre-#125 review boundary; earliest owning defect remains #125.
- A3: defect detected on faithful/reachable context; this run.

This completes the measurement that was intentionally blocking implementation of #125. Any post-#125 A2 measurement must be a new freeze and should include the planned independent held-out prose-definition/ambient-convention case rather than being treated as continuation of this baseline.
