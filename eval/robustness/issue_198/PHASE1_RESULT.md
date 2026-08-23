# Issue #198 — Phase 1 production qualification result

Status: **BLOCKED at the deterministic representation/context boundary**.

No provider was instantiated and no model/provider request was made. Phase 2 provider readiness and Phase 3 scientific live measurement were not run.

## Frozen production identity

- Thorn production revision: `dca454190eeb7fe5a8ebda93e71b6dea2be90820`
- frozen/current `src/thorn` tree: `7c4e24ecd2969f850eb8b4399ac77b6130ccbefb`
- default frontend: `tree-sitter`
- `tree-sitter==0.26.0`
- `tree-sitter-language-pack==1.14.3`
- language-pack release: `df3bcc39862da6972032d7537d49b782a50a25bb`
- packaged `latex-lsp/tree-sitter-latex`: `7e0ecdc02926c7b9b2e0c76003d4fe7b0944f957`
- `spacy==3.8.14`
- `en_core_web_sm==3.8.0`
- review representation: `thorn-proof/1`
- review protocol: `thorn-proof-review/2`
- prompt identity: `proof_language_reviewer_v2`

The qualification branch does not modify `src/thorn`; the preflight verified that its production source tree is byte-for-byte the frozen post-#183 tree.

## Frozen cases

| Case | Expected scientific class | Phase 1 |
| --- | --- | --- |
| A2 `variant_prose_uniformity.tex` / `thm:uniform-decay` | correct defect | **FAIL** |
| held-out `diagonal-regular` / `thm:main` | correct clean | PASS |
| C0 `clean_control.tex` / `thm:uniform-decay` | correct clean | PASS |

The case identities and source hashes were frozen in `qualification_manifest.json` before the production preflight was run.

## Earliest failing boundary

A2 fails before any model or provider boundary.

The real production Tree-sitter + spaCy extraction finds one prose definition candidate, with correct source provenance, but the candidate is ambiguous and its extracted term is malformed as `\\emph{stable` rather than an authoritative `stable` definition. Consequently the definition does not become a reachable `thorn-proof/1` semantic source.

The ambient observation-window convention (`Throughout, the observation window is ...`) is not emitted as a prose declaration candidate at all. It likewise cannot become a bounded semantic source.

The resulting A2 review packet advertises only `E1,P1,P2,R1,T0`; there is no definition (`D1`) or local/context (`L1`) handle carrying the two load-bearing facts. The preflight therefore reports:

- expected exactly one reachable semantic source containing `will be called \\emph{stable}`, got 0;
- expected exactly one reachable semantic source containing `Throughout, the observation window is`, got 0.

This is classified as **representation/context failure**, not model reasoning miss, source-rescue/protocol failure, or provider/transport failure. Bounded rescue cannot repair information that never enters the advertised source set.

## Positive controls

The independent held-out `diagonal-regular` case passes the same real production path: spaCy extracts the definition, it is reachable as `D1`, and bounded rescue returns the exact defining prose while it remains absent from the initial packet.

C0 also passes its frozen pruning/control checks. This narrows the failure to production semantic-context recovery for A2 rather than a general absence of Local NLP or a broken qualification harness.

## Evidence

GitHub Actions run `32609715643`, job `97120625132`, produced artifact `9485154049` (`issue-198-preflight-*`). The uploaded artifact ZIP SHA-256 reported by Actions is `e51781f0f2cb76a34c87bf90d092e888d961c596117f55167fc8413ccede4f1e`.

The preflight records:

- manifest/source hashes and frozen runtime/frontend identities;
- workspace occurrence/order and source provenance;
- prose-declaration inventory;
- exact `thorn-proof/1` packets and advertised source handles;
- bounded rescue evidence where available;
- protocol/schema request identity;
- provider execution/runtime fingerprints built keylessly;
- `provider_instantiated: false`, `provider_call_made: false`, and `paid_execution_authorized: false`.

## Disposition

Per #198's stop rule, do not proceed to Phase 2 or Phase 3 on this substrate. Repair the deterministic A2 semantic-context boundary first, then rerun the frozen Phase 1 qualification. Only after it passes should the separately authorization-gated live phases be considered.
