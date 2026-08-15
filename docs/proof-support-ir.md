# Proof-claim and support IR

Thorn's proof-support IR is a conservative, zero-inference representation of mathematical moves and the support relationships that are **explicitly visible** in a manuscript.

It sits above the source-preserving LaTeX frontend and beside the result-dependency and symbol/scope layers:

```text
LaTeX frontend facts
        |
        v
+---------------- mathematical IR ----------------+
| result dependency graph                          |
| symbol / definition / scope IR                   |
| proof claims + explicit support edges            |
+--------------------------------------------------+
        |
        +--> thorn check
        `--> later distilled thorn review
```

The purpose of this layer is not to prove implications. It is to make the author's visible argument structure addressable, source-located, queryable, and suitable for later selective semantic review.

## Claims

A `Claim` records a proof-local mathematical move with exact source provenance. The initial extractor distinguishes only two source forms:

- `prose` — a sentence-sized prose claim;
- `display` — displayed mathematics.

This distinction is presentation metadata, not mathematical status. A prose assertion and a display can both be load-bearing proof content.

Every claim retains its raw LaTeX and exact byte/line/column span. Claim identifiers are local to their containing theorem-like result.

## Explicit support edges

A `SupportEdge` records that the manuscript visibly presents some source as support for a claim. The initial support kinds are:

- `result_reference` — a theorem-like result reference presented with a local support cue such as `by`, `from`, `using`, `apply`, or `invoke`;
- `equation_reference` — an explicit `\eqref` presented with such a support cue;
- `definition` — an explicit `by definition` justification;
- `named_property` — an explicit named reason such as `by compactness` or `by continuity`;
- `prior_claim` — an explicit conclusion cue such as `Therefore`, `Hence`, or `Thus` consuming the immediately preceding recovered claim;
- `explicit_reason` — a mechanically clear `Since ..., ...` reason clause.

A plain `\ref` to a non-result object is not guessed to be proof support: it may denote a section, figure, table, equation, or something else. Likewise, a bare reference mentioned for exposition does not become a support edge merely because it occurs inside a proof.

Each edge records exact source provenance, whether the extraction is explicit, and an extraction confidence. The initial mechanically recognized edges use confidence `1.0`; this field leaves room for later conservative extractors without conflating extraction confidence with mathematical validity.

An edge means **the author presented this as support**. It does not mean Thorn has established that the implication is mathematically valid.

For example,

```latex
By compactness, pass to a convergent subsequence.
```

produces a named-property support edge. Whether compactness really applies in the ambient space is semantic-review territory.

## Load-bearing prose and "sneaky prose"

A prose assertion becomes structurally interesting when a later recovered claim explicitly consumes it.

```latex
The limit clearly has full rank.
Therefore the limit is admissible.
```

The initial IR records:

```text
P1  "The limit clearly has full rank."
      |
      |  therefore
      v
P2  "the limit is admissible"
```

`P1` is load-bearing because it has an outgoing `prior_claim` edge. If no explicit support enters `P1`, it appears in `unsupported_load_bearing_claim_ids()`.

Crucially, **`clearly` is not treated as support and is not itself an error**. The structural observation is that a claim is consumed downstream without a mechanically identified incoming support edge.

This query is deliberately **not yet a `thorn check` diagnostic**. A missing explicit edge can correspond to a real gap, a routine elementary step, a conventional background fact, or a limitation of the extractor. Turning it into a user-facing warning requires stronger evidence and matrix-tested false-positive control.

## Qualifiers and trailing binders

Issue #18 showed that source order is not a reliable mathematical binding rule. Ordinary prose permits forms such as:

```latex
\[
  m \le f(x) \le M
\]
for every $x\in X$.
```

The proof-support IR therefore attaches a conservatively recognized trailing binder to the display as a `ClaimQualifier` rather than interpreting the preceding `x` as an erroneous use-before-declaration.

Each recovered binding occurrence gets its own `BoundName.identifier`. Two occurrences both spelled `x` remain distinct binding events unless a later layer has evidence that they denote the same object.

## Graph queries

`ProofSupportGraph` provides:

- claims for a result;
- incoming support edges for a claim;
- outgoing edges from a claim;
- downstream recovered claim IDs;
- load-bearing claim IDs;
- structurally unsupported load-bearing claim IDs.

These queries expose proof structure without asserting semantic correctness.

The result-dependency graph remains separate. Together the two layers can show, for example, that an unsupported load-bearing prose claim occurs inside a lemma and that a later theorem explicitly depends on that lemma.

## Conservative extraction boundary

The first extractor intentionally recognizes only mechanically strong cues. It does **not** attempt general natural-language proof parsing, coreference resolution, semantic type inference, or reconstruction of omitted mathematical steps.

In particular:

- `clearly` and `obviously` are not support edges;
- two equal symbol spellings are not automatically the same binding;
- prose may be represented without being classified as load-bearing;
- bare/expository references are not automatically support;
- a support edge may be mathematically invalid even though it is structurally explicit;
- absence of a support edge is not by itself a correctness finding.

This preserves the principle established by the full #18 matrix audit:

> **The IR may record suspicious facts more aggressively than `thorn check` is allowed to report them.**

## Public support-IR matrix

`eval/support-expectations.json` specifies public structural expectations for selected synthetic cases. The initial set covers:

- load-bearing sneaky prose with no explicit incoming support and a downstream theorem dependency;
- clean repeated trailing binders;
- clean explicit theorem/equation/definition/named-property support;
- clean non-load-bearing expository prose.

These cases are check-only so they strengthen zero-inference coverage without increasing the paid semantic-review population. `tests/test_support_matrix.py` makes the expectation manifest a default keyless CI gate.

## Next step

Issue #20 can consume this IR to build smaller semantic-review packets. Rather than repeatedly asking a model to rediscover document structure from raw LaTeX, Thorn can present the relevant result, symbols, dependencies, claims, explicit support, and structurally suspicious edges directly.
