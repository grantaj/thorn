# Proof-claim and support IR

Thorn's proof-support IR is a conservative, zero-inference **frontend evidence layer**. It records mathematical moves and support relationships that are explicitly or strongly visibly presented in a manuscript.

It is useful, but it is **not the canonical proof language**.

The current architecture is:

```text
LaTeX frontend facts
        |
        v
+---------------- rich Thorn Math IR ----------------+
| result dependency graph                            |
| symbol / definition / scope evidence               |
| proof claims + explicit/candidate support edges    |
| linguistic evidence + uncertainty                  |
+----------------------------------------------------+
        |
        +--> thorn analyze
        +--> thorn ir
        |
        `-> partial mathematical elaboration
                |
                v
        canonical typed Proof IR
          - propositions / obligations
          - local hypotheses and goals
          - typed proof-step edges
          - substitutions / instantiations / witnesses
          - explicit unknown rules and holes
                |
                `-> AI and other proof consumers
```

The purpose of the support layer is to make the author's visible argument structure addressable, source-located, queryable, and available as evidence for elaboration. Once Thorn can safely identify a stronger mathematical operation, that operation belongs in canonical Proof IR rather than being left permanently as a generic support annotation.

## Claims

A `Claim` records a proof-local mathematical move with exact source provenance. The extractor distinguishes prose and display source forms. This is presentation metadata, not mathematical status: either can be load-bearing proof content.

Every claim retains raw LaTeX and exact source location. Claim identifiers are local to their containing theorem-like result.

A claim is therefore a frontend observation. It may later elaborate to a hypothesis, goal, derived proposition, unresolved mathematical fragment, or irreducible opaque proof step.

## Explicit support edges

A `SupportEdge` records that the manuscript visibly presents some source as support for a claim. Initial support kinds include result references, equation references, explicit definition use, named properties such as compactness or continuity, prior-claim conclusion cues, and mechanically clear explicit reason clauses.

A bare reference is not guessed to be proof support merely because it occurs inside a proof. Each edge records provenance, explicitness, and extraction confidence.

An edge means **the author presented this as support**. It does not mean Thorn established that the implication is mathematically valid.

For example:

```text
By compactness, pass to a convergent subsequence.
```

can produce a named-property support edge even when compactness is inapplicable in the ambient setting.

Later elaboration may be able to turn a sufficiently understood edge into a typed proof operation such as result application, implication elimination, definition use, rewriting, instantiation, or witness introduction. If it cannot, the canonical Proof IR should retain an explicit unknown or unresolved inference rather than pretending the generic support edge is a complete semantic account.

## Load-bearing prose

A prose assertion becomes structurally interesting when a later recovered claim explicitly consumes it. Thorn can therefore identify load-bearing claims and query which of them lack a mechanically identified incoming support edge.

Crucially, words such as `clearly` or `obviously` are not treated as support and are not themselves errors. Nor is a structurally unsupported load-bearing claim automatically an `analyze` diagnostic: it may be a genuine gap, a routine fact, a conventional background result, or an extraction limitation.

That distinction remains central:

> **The frontend may preserve suspicious or unresolved evidence more aggressively than deterministic analysis is allowed to report it.**

In the Proof IR programme, unresolved load-bearing steps should increasingly become explicit proof obligations or unknown-rule edges rather than disappearing into prose sequencing.

## Qualifiers and trailing binders

Ordinary prose permits forms such as:

```latex
\[
  m \le f(x) \le M
\]
for every $x\in X$.
```

The support IR can attach a conservatively recognized trailing binder as a `ClaimQualifier` rather than treating the preceding `x` as an erroneous use-before-declaration. Separate binding occurrences remain separate unless later evidence identifies them.

Canonical binder identity and scope resolution belong to the Proof IR elaboration layer. The support extractor should provide evidence without guessing the final binding structure.

## Graph queries

`ProofSupportGraph` exposes claims for a result, incoming/outgoing support edges, downstream claims, load-bearing claims, and structurally unsupported load-bearing claims.

The result-dependency graph remains separate at this frontend layer. Together they can show, for example, that an unsupported load-bearing prose claim occurs inside a lemma and that a later theorem explicitly depends on that lemma—without asserting that the lemma is mathematically wrong.

These graphs are inputs to canonical proof slicing and elaboration. They should not grow into an untyped catch-all proof language as Thorn learns stronger semantics.

## Conservative extraction boundary

The extractor intentionally recognizes only mechanically strong cues. It does not attempt unrestricted natural-language theorem proving or silently manufacture omitted mathematical steps.

In particular:

- `clearly` and `obviously` are not support edges;
- equal symbol spellings are not automatically the same binding;
- prose may be represented without being classified as load-bearing;
- bare/expository references are not automatically support;
- a support edge may be mathematically invalid even when structurally explicit;
- absence of a support edge is not by itself a correctness finding;
- ambiguity is retained for later elaboration or semantic reasoning rather than forced to certainty.

## Relationship to canonical Proof IR

Issue #59 defines the current north star: compile ordinary mathematical writing into the strongest faithful computer proof IR Thorn can recover.

The support layer contributes evidence to that process, but canonical Proof IR should progressively replace narration-shaped concepts with mathematical structure:

```text
support evidence:  "By Theorem 4 ..."
        |
        v
Proof IR: apply_result(T4, ...)

support evidence:  "choose y with P(y)"
        |
        v
Proof IR: witness_intro(y, obligation=...)

support evidence:  "substituting x=a"
        |
        v
Proof IR: instantiate/substitute canonical AST nodes
```

If the stronger interpretation is not justified, keep an explicit unresolved operation and the exact source rather than guessing.

This is an anti-regression rule: **do not preserve generic claim/support vocabulary as the final semantics merely because it was convenient during extraction.**

## Public support-IR matrix

`eval/support-expectations.json` specifies structural frontend expectations for selected synthetic cases. These cover load-bearing prose, trailing binders, explicit theorem/equation/definition/property support, and non-load-bearing exposition.

These fixtures strengthen deterministic evidence recovery without implying that support-edge success is equivalent to proof understanding. Separate Proof IR tests should establish stronger canonical semantics and metamorphic equivalence as the elaborator grows.

## AI consumer

The earlier issue #20 work showed that AI review can consume structured Thorn-owned context rather than rediscovering project structure from raw LaTeX.

The architectural direction is now stronger: AI-facing review should increasingly be a deterministic **projection/delaboration of canonical Proof IR**, with bounded source-on-demand for unresolved wording. The proof-support graph remains useful evidence and debugging state, but it should not be the model-facing endpoint when Thorn has already recovered more precise proof semantics.
