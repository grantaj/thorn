# Issue #134 A3 post-#137 live attempt: provider-schema rejection

## Status

The separately authorized A3-only continuation was attempted once on 2026-08-19
(Australia/Adelaide date) and stopped before model generation because the provider
rejected Thorn's JSON Schema. No retry was made.

This is **not** an A3 mathematical-review result. It is a deterministic
provider-schema/transport failure.

## Frozen input

- Assurance revision: `93cba5eec02af0c83bdcc3ea4eb54dd79efb1704`
- `src/thorn` tree: `08c1ef7c0d61020424a597be344f0bb08ce10f58`
- A3 request fingerprint: `44e1ffa1fb17219c106af28f8e7535e70788c1f7a02b5e762bf381e3637cfb28`
- Model alias: `gpt-5.6`
- Representation: `thorn-proof/1`
- Protocol: `thorn-proof-review/2`
- Provider retries: zero
- Maximum provider requests: two
- Maximum input tokens: 40,000
- Maximum output tokens: 4,096/request, 8,192 aggregate

The keyless preflight reconstructed the exact frozen request successfully before the
live attempt.

## Provider rejection

GitHub Actions run `32194156640` sent the frozen initial A3 request once. OpenAI
returned HTTP 400 before a structured response was produced:

```text
Invalid schema for response_format 'ProofReviewModelResponse':
In context=('anyOf', '0'), 'additionalProperties' is required to be supplied
and to be false.
```

The recording layer preserved the rejected exchange. It contains:

- no provider response payload;
- `requests = 0` in Thorn's completed-response accounting;
- zero recorded input/output/total tokens;
- rejection type `BadRequestError`;
- no replay, because there is no accepted provider response to replay.

The provider therefore rejected the request at schema validation, before Thorn had
any model output to adjudicate.

## Earliest failure boundary

**Boundary 6: review protocol / provider schema construction.**

The post-#137 canonical response schema added `anyOf` action-state branches as
constraint fragments. The provider-visible strict-schema conversion closes objects
that explicitly declare `type: object`, but those `anyOf` fragments had
`properties` without their own object declaration. OpenAI Structured Outputs rejects
such branches.

Issue #143 tracks the repair.

## Scientific interpretation

A1 and A2 remain the preserved measurements from the original pre-#125 run. This A3
attempt provides no evidence about model reasoning on the mathematical defect. In
particular, it neither passes nor fails the robustness case.

The authorization for this attempt is consumed. A further A3 provider call requires:

1. a keyless repair for #143;
2. a new A3-only freeze because the provider-visible response schema and therefore
   request identity change;
3. merge/green verification of that freeze;
4. a fresh official pricing check; and
5. a new explicit paid-run authorization.

A1/A2 must not be resampled, and #125 should remain unimplemented until this pre-#125
A3 measurement is complete.
