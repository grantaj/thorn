# Issue #101 variation journal

Assurance revision under evaluation: `79dc8b5986b0242240fcc2e5ab0de7437a08a9ff` (current `main` immediately after PR #123 / issue #10).

Independent adjudication is frozen in `ADJUDICATION.md`. Unless stated otherwise, every defective record retains the same counterexample: for `epsilon=1/2`, any proposed uniform integer `N` is defeated by `x_N=(3/4)^(1/N)`.

No paid/live model call was made. When faithful review context survives but semantic reasoning has not been run, the semantic outcome is recorded as `ambiguous` rather than inferred from a stand-in response.

## C0 — matched clean control

- **Parent:** none.
- **Source:** `clean_control.tex`.
- **SHA-256:** `d5beef31dad9fe8478a2d819f498ce7bfafaab23f2f4dfa9d017e43eb160429f`.
- **Mathematics:** fixes `0<rho<1`, works on the compact interval `[0,rho]`; the finite-subcover argument is valid and `x^n <= rho^n -> 0` uniformly.
- **Freeze:** committed together with B0 in `18bfa5e313f6de187af9da49b8cb430c442c0792`, before adaptive variants.
- **Deterministic diagnostics:** none.
- **Dependencies:** `thm:uniform-decay -> lem:pointwise`.
- **`thorn-proof/1`:** fingerprint `9558939e5cfdfdf64151c46329b58b17242bfc2e5dd8bf581f3313c716979d0d`; 33 lines; 21 held source handles.
- **Source reachability:** the domain `I_\rho=[0,\rho]` is in the initial packet; the load-bearing `compact interval` proof source is recoverable through advertised handle `P2`.
- **Initial live-request fingerprint:** `875811944da1e0157b800135bb6a84f488961837168f04c0ae70f5deeef226d1` (`gpt-5.6`, protocol v2 proposal only).
- **Lean:** `unsupported`; not mechanically checkable. This does not adjudicate the mathematics.
- **Report/visualizer:** result identity present in both generated artifacts. No semantic finding was fabricated for UX testing.
- **Outcome:** clean control; semantic review not run.

## B0 — defective baseline

- **Parent:** none.
- **Source:** `baseline.tex`.
- **SHA-256:** `cea3e0ea215fb7c6cb3d7823ad747f251605e41f823b26bd18529a8d0d7bbf45`.
- **Invariant defect:** false uniform convergence on `[0,1)`; the proof treats boundedness as enough for a finite subcover.
- **Independent adjudication:** `[0,1)` is noncompact. The frozen counterexample defeats every candidate `N`.
- **Variation family:** baseline ordinary mathematical prose.
- **Variation hypothesis:** establish which deterministic review boundaries carry the actual compactness/uniformity distinction before changing presentation.
- **Concise diff from control:** remove the fixed margin `rho<1`, replace `[0,rho]` by `[0,1)`, and incorrectly describe boundedness as enough for finite subcover selection.
- **Deterministic diagnostics:** none; this is intentionally a semantic mathematical defect.
- **Dependencies:** `thm:uniform-decay -> lem:pointwise`.
- **Canonical/Proof-IR observation:** target scope includes the domain and proof; the decisive proof sentence remains source-backed.
- **`thorn-proof/1`:** fingerprint `b2b9b7aa1ae5476a2a3159d20e7c2655beb83652fa11eab2ec5f0f80a9bd47bd`; 33 lines; 21 held source handles.
- **Source handles:** `I=[0,1)` is rendered at `D1`; the bad `bounded interval` sentence is not literal packet text but is reachable through advertised `P2` (also held as `E2`).
- **Initial live-request fingerprint:** `e3e4fb3b3f62ef605c028f27d189d31db8a41ce4455e493e1c7cab00faf2c640`.
- **Lean:** `unsupported`; not causal to the review result.
- **Report behavior:** target identity survives in report and graph. Keyless work cannot claim the concern is user-visible without a semantic finding.
- **Earliest failed boundary:** none observed before model reasoning.
- **Outcome:** **ambiguous keylessly**. The decisive information reaches or is reachable from the production review boundary.

## A1 — lemma indirection

- **Parent:** B0.
- **Source:** `variant_lemma_indirection.tex`.
- **SHA-256:** `36f1da32d992f02c74093deeb55158a4b1e5716965282449da77adcacd6df2ff`.
- **Invariant defect:** unchanged; the same counterexample invalidates the claimed uniform estimate.
- **Independent adjudication:** the new `Finite uniformization` lemma is itself false because `[0,1)` is not compact.
- **Variation family:** lemma indirection / proof decomposition.
- **Variation hypothesis:** move the false finite-subcover step upstream so the main theorem appears to be a routine application of a named lemma.
- **Concise manuscript diff:** the pointwise argument becomes `Local attenuation`; the finite-subcover step is isolated in `lem:uniformize`; the main theorem only cites that lemma.
- **Deterministic diagnostics:** none.
- **Dependency observation:** production reviews theorem-like units separately. The defect-carrying review target is therefore `lem:uniformize`, with direct dependency `lem:local`; looking only at the downstream theorem would be an invalid measurement.
- **`thorn-proof/1` at defect carrier:** fingerprint `815b0baf1afb58021f79822358c54228c658563239545f38c4a20240e5df58ae`; 10 lines; 6 held source handles.
- **Source handles:** the domain is rendered/reachable at `D1`; the false `bounded interval` finite-subcover sentence is reachable through advertised `P1`.
- **Initial live-request fingerprint:** `a7b24f8782586dccec61f0833215abcc9568e77ca7136454dcd6cc5d8fc61b15`.
- **Lean:** `unsupported`.
- **Report behavior:** the defect-carrying lemma identity survives in the generated report and graph.
- **Earliest failed boundary:** none observed before model reasoning.
- **Outcome:** **ambiguous keylessly; per-result review structure preserves the defect at the representation/dependency layers**.

## A2 — prose-defined uniformity and distant ambient convention

- **Parent:** B0.
- **Source:** `variant_prose_uniformity.tex`.
- **SHA-256:** `8621964954aadd7d85c6b6310d782be5073360e5f1a7ffb30a95e393d3795eff`.
- **Invariant defect:** unchanged. `stable` is explicitly defined to require one stage independent of observation point on the window `[0,1)`, so the frozen counterexample still refutes the theorem.
- **Independent adjudication:** the proof still extracts a finite subcover from a merely bounded, noncompact window.
- **Variation family:** prose quantifier + distant local convention.
- **Variation hypothesis:** move the proposition's uniform quantifier and domain semantics into ordinary mathematical prose, then use the defined word `stable` in the theorem statement.
- **Concise manuscript diff:** replace the theorem's explicit quantified inequality by a named property whose load-bearing definition and observation window are stated earlier in prose/source context.
- **Deterministic diagnostics:** none.
- **Dependencies:** `thm:uniform-decay -> lem:local-decay`.
- **Canonical/Proof-IR observation:** extraction retains the paper, but target-level semantic representation fails to bind the named predicate to its authoritative prose definition/ambient domain.
- **`thorn-proof/1`:** fingerprint `88682b10f138cb46450e10b3d075f575a0715d1db9cd0c095a0b8eb90c26d622`; only 6 lines and 3 held source handles.
- **Advertised/required source handles:** advertised addresses are exactly `P1,R1,T0`. Neither the domain fragment `0\leq x<1` nor the load-bearing definition fragment `depending on the tolerance but not` appears in the initial packet, exists among the held target sources, or is advertised for `NEED_SOURCE`. The closed-world contract is internally consistent, so rescue cannot ask for the missing semantics.
- **Initial live-request fingerprint:** `037375711aab3e2e976b9adbabf25aa61c0706421a7b98cd36f0827bdc36fd40`.
- **Lean:** `unsupported`; not causal.
- **Report behavior:** theorem identity survives, but the actual proposition-defining context has already been lost upstream. A report cannot explain a concern that the review state cannot represent/reach; this is not reclassified as a layer-10 bug.
- **Earliest failed boundary:** **2 — canonical representation/context loss**, causing downstream **5 — source-reachability/rescue loss**.
- **Outcome:** **deterministic robustness counterexample / assurance-context loss**. No claim is made about what a fresh model would guess from the impoverished packet.
- **Preservation/follow-up:** exact source preserved before any repair; generalized public follow-up issue #125 opened; reduced expected-failure regression `tests/test_issue_125_prose_definition_reachability.py` added. No architecture fix is hidden in #101.

## A3 — result applicability

- **Parent:** B0.
- **Source:** `variant_result_applicability.tex`.
- **SHA-256:** `f53d7c5eed1f0145406c3c4dda50680a852b14c2c4cd3705c17940ec5f27f403`.
- **Invariant defect:** unchanged; `[0,1)` remains noncompact and the uniform estimate remains false.
- **Independent adjudication:** the stated finite-cover principle is correct for compact intervals; the proof applies it to a bounded half-open interval outside its hypothesis.
- **Variation family:** result application / applicability mismatch.
- **Variation hypothesis:** make the false step resemble an ordinary application of a correctly stated standard theorem while preserving the missing precondition.
- **Concise manuscript diff:** state the finite-cover principle separately, then refer to it by name in the proof while retaining only boundedness of the actual domain.
- **Deterministic diagnostics:** none.
- **Dependencies:** `thm:uniform-decay -> lem:pointwise-neighbourhood`.
- **Canonical/Proof-IR observation:** both actual domain and the cited principle survive review preparation.
- **`thorn-proof/1`:** fingerprint `f6de18bf12a1137b3cb74f250ce36b4a2de85aaa257866f40bb4894c5fa08def`; 17 lines; 11 held source handles.
- **Source handles:** `I=[0,1)` is rendered at `D1`; `finite-cover principle` is rendered and source-backed at `P1/E1`.
- **Initial live-request fingerprint:** `0c8ba6c4a8cbfc2d285384b896e65059f67d296d708f75986deaace3434d22a3`.
- **Lean:** `unsupported`.
- **Report behavior:** target identity survives in report/graph; semantic visibility awaits an authorized model/replay result.
- **Earliest failed boundary:** none observed before model reasoning.
- **Outcome:** **ambiguous keylessly**; the theorem/domain mismatch remains available to review.

## H1 — private held-out nested-exhaustion variant

- **Storage:** `grantaj/thorn-private`; public CI has no dependency on it.
- **Source SHA-256:** `6316d514298687360c019369176647d48fe3910028ade238c052cedd5fb05772`.
- **Parent:** B0.
- **Invariant defect:** unchanged and independently checked with the same frozen counterexample.
- **Variation family:** local-to-global / nested exhaustion.
- **Variation hypothesis:** make every fixed compact subwindow estimate correct, then illegitimately promote the family of parameter-dependent uniform indices to one index on the increasing union.
- **Public disclosure:** source text remains held out. A private keyless observer is pinned to assurance revision `79dc8b...`.
- **Outcome:** held-out manuscript preserved; no semantic model call. Private workflow execution is not required for public CI and is not treated as evidence unless a reproducible run is available.

## Incremental review / #10 cache variation lane

All cache scenarios begin with a completed deterministic stand-in review only to populate the real production cache. The stand-in semantic content is irrelevant; the observation is solely whether the second state is reused or rechecked.

### K1 — source edit that canonicalizes to the same packet

- **Variation:** local wording `for each` -> `for every` in B0 while retaining the defect.
- **Packet relation:** initial `thorn-proof/1` fingerprint unchanged.
- **Cache decision:** `rechecked`, reason `recheck_local_ir_changed`.
- **Outcome:** protected by cache invariant; no stale semantic reuse.

### K2 — relevant upstream proof edit with stable target packet

- **Variation:** wording change inside A1's upstream false uniformization proof while target theorem packet remains unchanged.
- **Packet relation:** target initial packet unchanged.
- **Cache decision:** `rechecked`, reason `recheck_upstream_dependency_changed`.
- **Outcome:** protected by cache invariant; upstream content fingerprint prevents stale reuse.

### K3 — dependency-edge identity/topology change

- **Variation:** rename the upstream lemma/reference label while retaining the same defective mathematics.
- **Cache decision:** `rechecked`, reason `recheck_dependency_edge_changed`.
- **Outcome:** protected by cache invariant.

### K4 — nearby exposition edit

- **Variation:** add an expository paragraph that changes no mathematical claim.
- **Packet relation:** initial target packet unchanged.
- **Cache decision:** `rechecked`, reason `recheck_upstream_dependency_changed`.
- **Outcome:** safe but conservative over-invalidation. This is an efficiency observation, not an assurance failure.

No unsafe `cache_hit_*`/reuse was found in the #101 keyless lane.

## Keyless CI evidence

Before the terminology/path cleanup, PR #124 CI completed with:

- `435 passed, 1 skipped, 1 xfailed` (the xfail is the preserved #125 desired invariant);
- the keyless issue-101 observer successful with `OPENAI_API_KEY=""`;
- all 64 public eval cases validating and all 56 deterministic-analysis cases passing;
- `ruff check .` successful;
- `mypy src` successful;
- no provider requests in the observer.

The renamed observer remains in ordinary public CI so source hashes, frozen request fingerprints, source-contract consistency, result identity, and cache safety regressions stay reproducible without private material or paid calls.
