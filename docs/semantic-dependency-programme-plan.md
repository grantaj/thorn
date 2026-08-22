# Semantic-dependency substrate programme record

This document began as the execution plan for #156-#162. The evaluation and
consolidation work has now been carried out. It is retained as a compact programme
record; the normative current architecture is
[`semantic-dependency-architecture.md`](semantic-dependency-architecture.md) and the
executable invariant boundary is
[`semantic-dependency-contract.md`](semantic-dependency-contract.md).

## Completed sequence

| Tranche | Outcome |
| --- | --- |
| #157 / PR #163 | ownership audit and target layering |
| #162 / PRs #164-#166 | backend-independent conformance, scope/order/provenance, explicit partiality |
| #167 / PR #168 | truncated declaration fail-closed guard |
| #158 / PR #173 | Tree-sitter LaTeX evaluation |
| #159 / PR #175 | workspace/tooling evaluation and normalized occurrence boundary |
| #160 / PR #176 | dependency-parser declaration evaluation; small hybrid recommendation |
| #161 Slice A / PR #177 | production workspace occurrence/order facts |
| #161 Slice B / PR #178 | normalized source regions and reversible linguistic projection |
| #161 Slice C / PR #179 | normalized non-authoritative prose declaration candidates |
| #161 Slice D / PR #180 | authority/scope/shadowing migration to normalized substrate |
| #161 Slice E / PR #181 | canonical semantic dependency closure/order consolidation |
| #161 Slice F / PR #182 | normal result-level review policy and shared selection mechanics |
| #161 Slice G | backend/default disposition and final documentation alignment |

## Final ownership outcome

The programme converged on the following separation:

```text
LatexFrontend
    -> normalized source facts / exact provenance
    -> ProjectWorkspaceFacts occurrence/order facts
    -> reversible LinguisticProjection
    -> LinguisticFrontend
    -> non-authoritative semantic candidates
    -> Thorn mathematical authority / scope / shadowing
    -> canonical semantic dependency identity + closure
    -> Symbol IR / canonical Proof IR
    -> reports / Lean / thorn-proof/1
```

Thorn continues to own mathematical authority, dependency identity/materiality, scope,
visibility/shadowing, ambiguity policy, transitive semantic closure, exact provenance,
canonical IR and assurance/review boundaries.

Generic parser/workspace/linguistic machinery supplies facts or candidates only.

## Evaluation dispositions

### Source/CST

Tree-sitter is the preferred source-structure backend based on #158 and subsequent
conformance. Regex remains the explicit compatibility default because the exact pinned
`tree-sitter-latex` grammar still requires checkout + parser generation + local build;
the normal `treesitter` extra cannot yet establish that exact grammar runtime by itself.
A default cutover therefore remains separate packaging work rather than being smuggled
into #161.

pylatexenc remains an independent conformance backend.

### Workspace

`ProjectWorkspaceFacts` is the production source of expanded occurrence/order facts.
TexLab remains an optional-backend candidate/development oracle. LaTeXML remains useful
expansion/reference evidence. Neither external tool owns mathematical scope or authority.

### Linguistic declarations

The #160 small hybrid is production candidate machinery behind `LinguisticFrontend`.
Candidates remain ambiguous/non-authoritative until Thorn's mathematical policy promotes
them. The old #125 phrase recognizer survives only as a frozen research benchmark.
Structural-only mode explicitly lacks prose-authority capability.

### Review selection

Normal review is result-level and unconditional for a requested result. The
uncertainty-triggered selector is retained only for explicit `thorn-eval`
diagnostic/evaluation use. Both projections consume the same canonical semantic state.

## Programme invariants

The completed programme preserves these rules for future work:

- parser/NLP native objects never become canonical mathematical state;
- valid but unsupported source/workspace structure may remain explicitly partial;
- malformed source may fail closed rather than being repaired heuristically;
- repeated inclusion preserves occurrence identity;
- candidate grammatical evidence is not mathematical authority;
- no semantic layer rescans raw LaTeX to compensate for a backend gap;
- no second semantic IR or parallel authority graph is introduced;
- `thorn-proof/1` and bounded source rescue project from canonical state;
- ordinary CI and architecture work remain keyless.

## Superseded machinery

The consolidation removed or retired the architectural need for:

- semantic-layer raw comment/verbatim masking;
- private semantic include-order reconstruction;
- the production five-family #125 phrase recognizer;
- bespoke production morphology for prose term matching;
- duplicate project-semantic closure implementations;
- selector-private mathematical materialization;
- ambiguity about whether normal review is trigger-gated.

The regex frontend still contains handwritten raw-source parsing because it is the
current compatibility backend. It is not the preferred long-term source substrate and
must not grow into a more complete TeX interpreter while packaging work is pending.

## Final validation gate

Every consolidation slice is required to preserve the keyless gates appropriate to its
boundary: full pytest, Ruff, mypy, Local NLP, Tree-sitter/frontend conformance, semantic
dependency contracts, and Lean handoff. Provider/model calls are outside this programme
and are not authorized by it.

After Slice G lands, #161 can close. Any later Tree-sitter packaging/default switch is a
separate bounded change that must re-run the same contracts rather than reopening the
semantic-dependency architecture.
