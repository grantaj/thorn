# Material assumption gap evaluation family

Issue #98 distinguishes an unstated premise from a material assumption gap by **counterfactual materiality**:

1. identify the premise consumed by the proof edge or theorem-scope judgement;
2. ask whether plausible alternatives would change proof validity, theorem meaning, or claimed scope;
3. if not, stop: the omitted background is not review-relevant merely because a formal system would require it;
4. if yes, ask whether authoritative source context adequately determines the intended premise;
5. only an unresolved, load-bearing, materially consequential choice is a material assumption gap.

These fixtures are semantic-review cases. Their metadata is ground truth for evaluation and is not passed to the model.

| Pair | Load-bearing premise / consuming edge | Clean disposition | Defect disposition | Counterfactual alternatives | Pipeline diagnostic |
| --- | --- | --- | --- | --- | --- |
| Euclidean geometry | The proof's Pythagorean step needs Euclidean flat geometry for the side-length identity. | The theorem places the right triangle in the Euclidean plane. No foundational axiom spelling is needed. | The theorem claims the same identity for a geodesic right triangle on an arbitrary complete Riemannian surface. | Curved surfaces change the right-triangle side-length relation, so validity changes. | The theorem scope and proof step remain distinct canonical/proof-obligation objects; exact theorem/proof source is represented or reachable at `thorn-proof/1`. No canonical IR change is needed. |
| Domain-sensitive algebra | From `(x-1)(x+1)=0`, the proof concludes one factor is zero. | `x` is explicitly real; the relevant zero-product property is contextually settled. | `x` ranges over an arbitrary ring, where zero divisors and nontrivial involutions are possible. | Integral domains versus rings with zero divisors give materially different validity. | Domain/scope wording survives in the theorem source and proof edge remains visible. The remaining decision is semantic review, not deterministic theorem proving. |
| Foundational-looking arithmetic | Cancellation of the common factor `2`. | Ordinary integers are specified; deeper foundational presentations do not change this local judgement. | The theorem explicitly uses arithmetic in `Z/4Z`, where cancellation by `2` fails. | Standard integers versus modular arithmetic change validity even though the surface operation is elementary. | The packet preserves the source-level arithmetic interpretation without teaching Thorn a cultural definition of “integer”. |
| Dimension-sensitive functional analysis | Compactness of a bounded closed ball is used to extract a convergent subsequence. | Finite dimensionality is part of theorem scope. | The theorem claims arbitrary normed real vector spaces. | Infinite-dimensional spaces admit bounded sequences without convergent subsequences. | The finite/arbitrary scope distinction survives through canonical source/proof obligations and `thorn-proof/1`; no special compactness dictionary is introduced. |

## Boundary classification

Tracing these pairs through the current pipeline found no source/extraction, symbol/type/scope, canonical Proof-IR, proof-edge, `thorn-proof/1`, source-reachability, or Lean-lowering defect that requires a new semantic representation.

The earliest general gap is the **review-policy/model boundary**. The existing reviewer contract correctly says that parser uncertainty is not a mathematical defect, but it did not state when an *unstated mathematical premise* itself should count as a review concern. Issue #98 therefore adds one general rule: use counterfactual materiality, do not demand formalisation-only background, and do not silently choose among materially different plausible interpretations.

Lean remains a partial formalisation handoff. A typeclass or elaboration requirement can create a Lean formalisation obligation without becoming a Thorn paper finding. Conversely, Lean must not select a stronger ambient structure merely to make a theorem compile.
