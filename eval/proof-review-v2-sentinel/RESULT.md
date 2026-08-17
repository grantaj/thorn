# Post-#90 proof-review v2 sentinel result

Status: **GREEN** under the scoring rule frozen before the successful semantic
run.

This result belongs only to the separately frozen
`post-90-v2-sentinel` experiment. It is not pooled with or described as a
continuation of the historical #83 `thorn-proof-review/1` paid condition.

## Frozen condition

- Thorn base: `c88572645bca494c79922ee8d4b8faae13be3a4b` (post-#95 main)
- model: `gpt-5.6-sol`
- prompt: `proof_language_reviewer_v2`
- protocol: `thorn-proof-review/2`
- prompt SHA-256: `6e69e97744b8667c06eb936aec931289050c1bbc691aa39c82780d8cecf05258`
- maximum live requests: 8
- maximum output tokens per request: 4096
- implicit SDK retries: 0
- two matched cases, six initial A/B/C requests
- successful-run response schema SHA-256 values:
  - no rescue: `51464a8eb4e7eabf14293e8c8a997cfeef34ab7251e2f41b9f41806e1eb7baa7`
  - rescue allowed: `d4dcd43f8f6b29e3212f67d674940cb906847bdf9643b860d27cfabb768de66f`

The clean and defect papers differ only by the word `unique` in the theorem
claim. Both use the same project-scope relation definition and the same proof.

## Pre-semantic transport repair

The first attempted live transport produced no semantic/model response. OpenAI
rejected the structured-output schema before inference because mechanically
empty `tuple[()]` response fields were emitted as JSON-Schema arrays without an
`items` declaration.

That exposed a general #88/#89 transport-contract defect rather than a
mathematical sentinel outcome. The repair changed only the existing dynamic
response-schema construction: an array constrained to be empty now retains its
real item type and `maxItems: 0`. The closed-world semantics are unchanged.

The mathematical fixtures, prompt, model, scoring contract, proof packets and
packet fingerprints were not changed. Because response schemas participate in
request fingerprinting, all six initial request contracts were regenerated and
refrozen after the repair. CI, Local NLP and Lean were green and the normal-spaCy
inventory reported `frozen_request_contract_verified=true`,
`provider_instantiated=false`, `provider_requests=0` and `live_requests=0`
before the second live attempt.

The rejected pre-semantic request is not scored as a sentinel outcome.

## Successful live result

| case | A — raw | B — Proof IR | C — Proof IR + rescue |
|---|---|---|---|
| defect: uniqueness claim | correct defect | correct defect | correct defect, no rescue needed |
| clean: existence claim | clean | clean | clean after one exact rescue |

### Defect case

All three arms identified the actual mathematical defect, not merely an open
Proof-IR obligation.

The Proof-IR-only arm, for example, reported that the project definition gives
`u^2=v^2+1`, while the theorem claims a unique real `u`, and supplied the
counterexample `v=0`, where both `u=1` and `u=-1` satisfy the relation.

The rescue-capable arm reached the same conclusion directly from its initial
packet and did not request source.

This satisfies the frozen defect rule: the review distinguished existence from
uniqueness and gave a concrete mathematical counterexample.

### Clean case

A and B returned no findings.

C initially requested exact source for `P1,P2,P3` while carrying two explicit
questions:

1. whether the chosen square-root witness is real and satisfies the defining
   equation;
2. whether the final existence claim actually discharges the theorem goal for
   arbitrary real `v`.

The existing deterministic prerequisite closure expanded the request to:

`D1,U1,P1,U2,P2,P3`.

After receiving that exact source, the final response dispositioned both carried
review items exactly once as `discharged` and returned no findings.

This is a direct live exercise of the combined post-#83 protocol:

- #87 project-level authoritative definition is reachable (`D1`);
- #88 source selection stays inside the advertised closed world;
- #86 prerequisite closure supplies the relevant represented context;
- #89 review state survives rescue and is explicitly discharged;
- #90 goal-versus-supported-conclusion review does not turn unresolved recovery
  into a clean-case defect.

## Frozen decision gate

The predeclared GREEN condition was:

- A and C both identify the defect correctly;
- A and C both keep the clean control free of mathematical findings;
- C has no source-selection or carried-state protocol failure;
- B is diagnostic rather than gating.

All conditions are met. B also succeeded on both cases, which is stronger than
the minimum gate.

## Usage and replay

Successful live run:

- arm runs: 6
- live/provider requests: 7
- input tokens: 11,752
- output tokens: 2,020
- total tokens: 13,772
- source-rescue turns: 1
- hidden SDK retries: 0

The seventh request is exactly the clean C rescue turn. The run remained below
the frozen eight-request ceiling.

Immediate keyless replay used all seven exact recordings and reproduced the six
semantic results, structured responses, source-rescue payloads and request
fingerprints with `live_requests=0`.

Raw provider recordings and full live/replay JSON remain attached to the
one-shot GitHub Actions run rather than being committed to the repository.

## Interpretation

This is intentionally a small transfer sentinel, not a broad quality estimate.
It provides positive evidence for the specific post-#83 hypothesis it was
frozen to test:

> after #87/#88/#89/#90, the current `thorn-proof/1` plus
> `thorn-proof-review/2` boundary can transfer to a new goal-strength case while
> preserving a matched clean neighbour, and bounded source rescue can refine
> uncertainty without manufacturing a defect.

The result does not by itself justify replacing raw-source review globally.
Broader production-path decisions should remain grounded in larger or real-paper
acceptance evidence rather than extrapolating from this two-case sentinel.
