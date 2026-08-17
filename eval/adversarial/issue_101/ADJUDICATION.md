# Issue #101 frozen mathematical adjudication

Frozen against public Thorn revision `79dc8b5986b0242240fcc2e5ab0de7437a08a9ff`
(post-PR #123 / issue #10).

## Defective baseline

File: `baseline.tex`

SHA-256: `cea3e0ea215fb7c6cb3d7823ad747f251605e41f823b26bd18529a8d0d7bbf45`

The load-bearing defect is a false promotion from pointwise decay to uniform
decay on the non-compact half-open interval `I=[0,1)`. The proof constructs
an open cover from point-dependent indices and then asserts that boundedness
of `I` supplies a finite subcover. Boundedness alone does not imply
compactness; `[0,1)` is not compact.

The theorem is false independently of Thorn. Fix `epsilon=1/2`. For every
integer `N>=1`, choose

```text
x_N = (3/4)^(1/N).
```

Then `0 < x_N < 1`, so `x_N` lies in `I`, but

```text
a_N(x_N) = x_N^N = 3/4 > 1/2.
```

Hence no single `N` can make `x^n < 1/2` for every `x in I` and every
`n>=N`. Equivalently, `sup_{0<=x<1} x^n = 1` for every `n`.

The pointwise lemma is correct. The failure occurs only when its
point-dependent witnesses are uniformized over a domain which accumulates at
the missing endpoint `1`.

## Matched clean control

File: `clean_control.tex`

SHA-256: `d5beef31dad9fe8478a2d819f498ce7bfafaab23f2f4dfa9d017e43eb160429f`

The control fixes a number `0<rho<1` and replaces the domain by the compact
interval `I_rho=[0,rho]`. The pointwise lemma remains true and the same
neighbourhood-cover argument now has a legitimate finite-subcover step.
Consequently the maximum of the finitely many local indices is a valid
uniform index. Directly, `x^n <= rho^n -> 0` uniformly on `I_rho`.

The control changes the mathematical premise that failed in the baseline; it
is not tuned against a Thorn/model outcome.

## Frozen invariant for adaptive variants

Every defective adversarial variant must continue to claim uniform
attenuation all the way up to `1` while excluding the endpoint itself.
Presentation, notation, lemma decomposition, references, and source
organization may change, but no variant may add a fixed margin `rho<1`,
compactness of the actual domain, or any other premise that makes the
uniform claim true.

The independent counterexample above must remain a counterexample to every
preserved defective variant.
