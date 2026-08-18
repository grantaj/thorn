# Issue #134 pre-#125 live result

## Status

**The separately authorized live run executed once and stopped at a preserved deterministic protocol/transport boundary during A3. Do not resample A1 or A2.**

Run metadata:

- experiment: `issue-134-pre-125`
- authorized execution branch: `agent/issue-134-live-authorized`
- exact authorized trigger SHA: `28feb52af0095995c00610ef8e6ceafdfdb5ab03`
- GitHub Actions run: `32179788278`
- preflight job: `95849867546` — success
- live job: `95850015987` — failure at the A3 initial response parse boundary
- live artifact: `9340382800`, `issue-134-live-32179788278`
- artifact SHA-256: `27f751572666788c6f911f4e8d71f9756367682b14750c246a2441285051092d`
- frozen assurance revision: `9201b33f73b84debf088548859d360be6a350585`
- frozen `src/thorn` tree: `17b4af51d42e6c2268fff8279d5ed0edc895939c`
- model: `gpt-5.6`
- representation: `thorn-proof/1`
- protocol: `thorn-proof-review/2`
- source rescue: allowed once, at most 8 addresses
- implicit provider retries: zero

The user explicitly authorized the paid A1/A2/A3 continuation after the freeze was merged. Immediately before the run, the official provider price for the frozen `gpt-5.6` alias was re-checked as $5/M input and $30/M output, matching the manifest.

The temporary execution trigger was disarmed immediately after the single dispatch. No retry or resampling has been performed.

## Preflight

The keyless preflight succeeded before any live job began. It reconstructed the exact inherited initial request identities on the frozen post-#132/pre-#125 assurance tree:

| Case | Initial request fingerprint | Conservative initial input upper bound |
| --- | --- | ---: |
| A1 | `a7b24f8782586dccec61f0833215abcc9568e77ca7136454dcd6cc5d8fc61b15` | 9,874 |
| A2 | `037375711aab3e2e976b9adbabf25aa61c0706421a7b98cd36f0827bdc36fd40` | 9,366 |
| A3 | `0c8ba6c4a8cbfc2d285384b896e65059f67d296d708f75986deaace3434d22a3` | 10,221 |

All three matched the post-#128 predecessor fingerprints. The aggregate initial bound was 29,461 tokens and the diagnostic all-cases maximal two-turn bound was 79,084, both inside the frozen 100,000-token aggregate ceiling.

`live_authorized: false` in the preflight JSON is intentional: preflight itself never grants authorization. Authorization was recorded separately before the live trigger.

## A1 — lemma indirection

### Live behavior

A1 completed on its initial request with no source rescue.

Provider usage:

- requests: 1
- input tokens: 1,694
- output tokens: 650
- total tokens: 2,344

The reviewer emitted one error finding: **“The claimed uniform exponent on `I=[0,1)` does not exist.”** It correctly identified that the local pointwise-neighbourhood result does not justify the finite-uniformization lemma: `[0,1)` is not compact, so boundedness does not supply a finite subcover. It also gave an explicit counterexample to any proposed uniform exponent.

### Independent mathematical adjudication

**Correct catch.** The manuscript's upstream lemma says that the neighbourhoods form an open cover of the bounded interval `I=[0,1)`, “so finitely many cover `I`.” That implication is false. Boundedness alone does not imply compactness, and `[0,1)` is not compact. Consequently `x^n -> 0` is not uniform on `[0,1)`.

A direct witness is available for every proposed `N`: with `epsilon = 1/2`, choose an `x<1` sufficiently close to 1 so that `x^N > 1/2`.

### Boundary classification

No failed Thorn boundary is needed for this observation. With the bad step moved into an upstream lemma, semantic review still found the invariant compactness/uniformity defect.

This is positive robustness evidence for lemma indirection.

## A2 — prose-defined uniformity

### Live behavior

A2 used the single permitted source-rescue turn.

Initial request usage:

- requests: 1
- input tokens: 1,458
- output tokens: 267
- total tokens: 1,725

The initial response did not invent a defect. It created review item `RV1` asking what the paper's prose property “stable” means and whether the recovered pointwise convergence result is sufficient, and requested source `P1,T0`.

The bounded rescue expanded this to the relevant prerequisite/source set `R1,P1,T0` and completed successfully.

Rescue request usage:

- requests: 1
- input tokens: 1,853
- output tokens: 260
- total tokens: 2,113

The final response emitted **no mathematical finding** and dispositioned `RV1` as `unresolved`. Its explanation was that the supplied source still established only the pointwise-decay result and the assertion that this is “precisely stability”; the authoritative definition of stability remained absent. It therefore declined to infer either that pointwise convergence suffices or that a stronger uniform condition is required.

### Independent mathematical adjudication

This is the correct conservative behavior for the **known impoverished pre-#125 packet**. The authoritative prose definition and ambient convention needed to interpret the theorem are not faithfully represented or reachable through the current closed-world source contract. The reviewer used the available rescue mechanism and then left the question unresolved rather than converting missing semantic context into a false defect.

This observation does **not** weaken issue #125. The deterministic fidelity defect exists independently of the model response.

### Boundary classification

Earliest failed boundary: **2. canonical representation/context loss**.

The downstream inability to rescue the definition is also a source-reachability manifestation (boundary 5), but the earliest owning failure is that the theorem's authoritative prose semantics never become faithfully represented at the semantic-review boundary. Issue #125 remains the owner.

## A3 — result applicability

### Mathematical ground truth

The manuscript states the finite-cover principle correctly: every open cover of a **compact** interval admits a finite subcover. The proof then applies it to `I=[0,1)`, calling `I` merely bounded. This is outside the stated hypothesis: `[0,1)` is not compact. The theorem's uniform conclusion is false.

Thus the intended mathematical defect is a result-applicability/hypothesis mismatch at the finite-cover step.

### Live behavior and preserved stop

A3 reached its initial provider request, but Thorn did not obtain an accepted `ProofReviewModelResponse`.

The provider returned structured JSON that was accepted far enough by the provider structured-output layer to be passed into Thorn's Pydantic response model, but Pydantic rejected it with:

`Value error, review responses must not request source`

The observed object had `action = "review"` while also carrying source addresses. This violates Thorn's cross-field protocol rule.

The failure occurred inside `OpenAI.responses.parse()` before `OpenAIProvider._record_usage()` and before the recording wrapper received a parsed response. The exact rejected request was preserved, but the recording contains:

- `response: null`
- rejection kind: `provider_failure`
- exception type: `ValidationError`
- `validator_replayable: false`
- zero recorded usage for this exchange

The live workflow stopped immediately. The replay step did not run because the live step failed. This is intentional fail-closed behavior; no manuscript, protocol, bound, or context was adapted after seeing output.

### Boundary classification

Earliest failed boundary: **6. review-protocol/state loss**, specifically the structured-output/transport contract and failure-evidence boundary.

The current initial response JSON Schema permits combinations that the post-parse Pydantic model validator rejects. In particular, the schema exposes `action: review | need_source` and source-address fields without encoding the action-dependent valid-state union. Therefore a response may satisfy the provider-facing schema yet fail Thorn's hidden cross-field rule after transport.

A second evidence-capture problem is exposed at the same boundary: because SDK parsing raises before the provider wrapper records the response, provider-reported token usage and the exact raw invalid response are lost from Thorn's durable recording.

This run therefore does **not** provide a valid semantic-review measurement of A3 model reasoning. It provides a deterministic protocol/transport witness that must be repaired keylessly before a newly frozen A3 retry.

## Usage and cost accounting

Accepted/recorded provider usage before the A3 parse failure:

- requests: 3
- input tokens: 5,005
- output tokens: 1,177
- known total tokens: 6,182

At the checked standard rates, those recorded exchanges cost exactly **$0.060335**.

One additional A3 provider request was made, so the run attempted exactly **4 provider requests** in total. Its exact usage is unavailable because of the transport/evidence-capture defect above. Using the frozen conservative A3 initial-input upper bound (10,221) and the 4,096 output cap gives a conservative additional standard-price upper bound of $0.173985. Therefore the whole stopped run is bounded above by **$0.234320** at the checked rates. This is a bound, not an exact bill.

The frozen experiment ceiling of six requests / 100,000 input / 24,576 output was never approached.

## Scientific interpretation

The pre-#125 continuation produced useful evidence without resampling earlier cases:

- **A1:** success — the invariant mathematical defect survives lemma indirection and is correctly detected.
- **A2:** informative conservative result — the reviewer recognizes that the missing prose semantics prevent adjudication and leaves the question unresolved; the earliest deterministic failure remains the #125 representation/context boundary.
- **A3:** deterministic stop — no valid semantic result should be claimed because the provider-facing structured-output schema and Thorn's post-parse protocol validator admit different state spaces.

The run must not be treated as a reason to rerun A1 or A2. Their observations are accepted and should be replayed from their recordings where needed.

## Next sequencing

1. Preserve this exact stopped-run witness and its accepted recordings.
2. Repair the A3-owning protocol/transport/evidence-capture defect **keylessly**.
3. Add regressions proving schema-valid provider output cannot enter an action-invalid state and proving failure paths preserve response/usage evidence.
4. Freeze a **new A3-only** experiment on the repaired assurance tree. Do not silently reuse this freeze.
5. Obtain separate explicit authorization before any paid A3 retry.
6. After A3 is completed or reaches another preserved deterministic boundary, finish the #134 baseline and only then implement #125.

No further paid execution is authorized by this result document.