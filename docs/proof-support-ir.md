# Proof-claim and support IR

Thorn's proof-support IR is a conservative, zero-inference representation of mathematical moves and support relationships that are **explicitly visible** in a manuscript.

It sits above the source-preserving LaTeX frontend beside the result-dependency and symbol/scope layers:

```text
LaTeX frontend facts
        |
        v
+---------------- Thorn Math IR -------------------+
| result dependency graph                          |
| symbol / definition / scope IR                   |
| proof claims + explicit support edges            |
+--------------------------------------------------+
        |
        +--> thorn analyze
        +--> thorn ir
        `--> distilled thorn review
```

The purpose of this layer is not to prove implications. It makes the author's visible argument structure addressable, source-located, queryable, and suitable for selective semantic review.

## Claims

A `Claim` records a proof-local mathematical move with exact source provenance. The initial extractor distinguishes prose and display source forms. This is presentation metadata, not mathematical status: either can be load-bearing proof content.

Every claim retains raw LaTeX and exact source location. Claim identifiers are local to their containing theorem-like result.

## Explicit support edges

A `SupportEdge` records that the manuscript visibly presents some source as support for a claim. Initial support kinds include result references, equation references, explicit definition use, named properties such as compactness or continuity, prior-claim conclusion cues, and mechanically clear explicit reason clauses.

A bare reference is not guessed to be proof support merely because it occurs inside a proof. Each edge records provenance, explicitness, and extraction confidence.

An edge means **the author presented this as support**. It does not mean Thorn established that the implication is mathematically valid. For example, `By compactness, pass to a convergent subsequence` can produce a named-property edge even when compactness is inapplicable in the ambient setting. That validity question belongs to semantic review.

## Load-bearing prose

A prose assertion becomes structurally interesting when a later recovered claim explicitly consumes it. Thorn can therefore identify load-bearing claims and query which of them lack a mechanically identified incoming support edge.

Crucially, words such as `clearly` or `obviously` are not treated as support and are not themselves errors. Nor is a structurally unsupported load-bearing claim automatically an `analyze` diagnostic: it may be a genuine gap, a routine fact, a conventional background result, or an extraction limitation.

That distinction is central:

> **The IR may record suspicious facts more aggressively than deterministic analysis is allowed to report them.**

## Qualifiers and trailing binders

Ordinary prose permits forms such as:

```latex
\[
  m \le f(x) \le M
\]
for every $x\in X$.
```

The support IR can attach a conservatively recognized trailing binder as a `ClaimQualifier` rather than treating the preceding `x` as an erroneous use-before-declaration. Separate binding occurrences remain separate unless later evidence identifies them.

## Graph queries

`ProofSupportGraph` exposes claims for a result, incoming/outgoing support edges, downstream claims, load-bearing claims, and structurally unsupported load-bearing claims.

The result-dependency graph remains separate. Together they can show, for example, that an unsupported load-bearing prose claim occurs inside a lemma and that a later theorem explicitly depends on that lemma—without asserting that the lemma is mathematically wrong.

## Conservative extraction boundary

The extractor intentionally recognizes only mechanically strong cues. It does not attempt general natural-language proof parsing, coreference resolution, semantic type inference, or reconstruction of omitted mathematical steps.

In particular:

- `clearly` and `obviously` are not support edges;
- equal symbol spellings are not automatically the same binding;
- prose may be represented without being classified as load-bearing;
- bare/expository references are not automatically support;
- a support edge may be mathematically invalid even when structurally explicit;
- absence of a support edge is not by itself a correctness finding.

## Public support-IR matrix

`eval/support-expectations.json` specifies structural IR expectations for selected synthetic cases. These cover load-bearing prose, trailing binders, explicit theorem/equation/definition/property support, and non-load-bearing exposition.

These fixtures can strengthen deterministic IR coverage without increasing paid semantic-review runs. `tests/test_support_matrix.py` keeps that expectation manifest in keyless CI.

## Semantic-review consumer

Issue #20 consumes this IR to build smaller review packets. Rather than asking a model to rediscover project structure from raw LaTeX, Thorn can present the relevant result, symbols, dependencies, claims, explicit support, uncertainty evidence, and source spans directly.

The raw theorem-unit review path remains an A/B baseline while IR-assisted review is measured. The architectural direction is for semantic review to consume the Thorn-owned representation.
