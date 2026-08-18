# Issue #101 post-#128 live result

This note preserves the useful outcome of the separately authorized semantic robustness experiment frozen in `manifest_post128.json` after the bounded source-rescue repair in #128.

The run did **not** complete the five-case batch. It stopped at a deterministic `thorn-proof-review/2` review-state/accounting boundary during B0. The mathematical output obtained before that boundary is preserved as evidence; it must not be retried or tuned as though it had not occurred.

## Frozen execution

- Freeze PR: #130
- Assurance revision: `18c509f2d6414062a4da5311010c5346afd5b786`
- Assurance `src/thorn` tree: `02d9afdd478ae1ac30692907567237536b60cc66`
- Model alias: `gpt-5.6`
- Representation: `thorn-proof/1`
- Protocol: `thorn-proof-review/2`
- Cases: C0, B0, A1, A2, A3
- Provider-request ceiling: 10
- Aggregate input-token guard: 100,000
- Output ceiling per request: 4,096
- SDK retries: 0

Execution provenance:

- workflow run: `32092755023`
- live job: `95578178347`
- temporary execution PR: #131, closed without merge
- artifact: `issue-101-post128-live-32092755023`
- artifact ID: `9308921468`
- artifact digest: `sha256:c48da8cca7b8a6d59c71f020b56eb092d754c41e05984e503a5328dcdae3751d`

The run made four provider requests before stopping:

| turn | input tokens | output tokens |
| --- | ---: | ---: |
| C0 initial | 2,448 | 662 |
| C0 rescue | 3,085 | 406 |
| B0 initial | 2,421 | 447 |
| B0 rescue | 3,078 | 1,546 |
| **total** | **11,032** | **3,061** |

There was no hidden provider retry.

## C0: clean control

C0 completed both protocol turns. The initial response requested exact source for the theorem/definition boundary and carried two review questions. After bounded source rescue, the final response returned **no mathematical findings**.

Both carried items were marked `unresolved` rather than being promoted into unsupported defects. In particular, the reviewer did not invent a mathematical error merely because the bounded source did not completely settle the prose meaning of “uniformly attenuating.”

Disposition: useful clean-control evidence. C0 was not falsely flagged.

## B0: known defect caught, result rejected by protocol accounting

The initial B0 response requested exact source for `T0`, `P2`, and `P3` and carried three review items:

1. whether uniform attenuation of `a_n(x)=x^n` on `[0,1)` is false because points can approach 1;
2. whether the finite-cover step incorrectly treats boundedness of `[0,1)` as sufficient for a finite subcover;
3. whether the final uniform conclusion depends on that invalid step.

The rescue response correctly confirmed all three concerns. Its two final mathematical findings were:

- **F1 — non-uniformity:** for `epsilon = 1/2`, every proposed uniform `N` fails by choosing `y` sufficiently close to 1; equivalently `sup_{y in [0,1)} y^n = 1` for every `n`.
- **F2 — invalid finite-subcover inference:** boundedness of `[0,1)` does not imply compactness, and therefore does not justify the finite-subcover step in `P2`.

This is the intended mathematical diagnosis of B0.

The response used finding ID `F1` in the dispositions of both RV1 and RV3, because those two carried concerns are facets of the same non-uniformity defect. It also supplied richer top-level `F1` and `F2` findings after shorter disposition-local versions.

Thorn rejected the response with:

```text
ProofReviewProtocolError: final response reuses finding identity across rescue accounting: F1, F2
```

The provider response itself is preserved in the workflow artifact's quarantined rejected-recording directory. Issue #132 owns this review-protocol/state-accounting repair.

## Interpretation

This run is **not** a mathematical review miss:

- the clean control remained clean;
- the baseline known-defect paper was recognized correctly and specifically;
- the first post-#128 source-rescue turn worked as intended;
- the stopping boundary was downstream, in deterministic consolidation of carried review state into final findings.

Do not modify B0 to accommodate the protocol. Repair the accounting layer and preserve this exact response shape as a regression.

## Next experiment boundary

Any live continuation after #132 changes production review-state behavior and is therefore a new experiment. Freeze the repaired assurance tree, prove the intended request/representation invariants keylessly, and obtain separate explicit authorization before making another paid/model call.
