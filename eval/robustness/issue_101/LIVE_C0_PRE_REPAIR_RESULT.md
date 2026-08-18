# Issue #101 C0 pre-repair live witness

This note preserves the useful outcome of the first inspectable live execution of the frozen issue #101 robustness experiment before the source-rescue repair in #128.

It is **not** a semantic adjudication of C0. The run stopped at a deterministic Thorn protocol boundary after the initial model response.

## Frozen request

- Case: `C0` (`clean_control.tex`)
- Assurance revision: `79dc8b5986b0242240fcc2e5ab0de7437a08a9ff`
- Model alias: `gpt-5.6`
- Protocol: `thorn-proof-review/2`
- Representation: `thorn-proof/1`
- Initial proof packet fingerprint: `9558939e5cfdfdf64151c46329b58b17242bfc2e5dd8bf581f3313c716979d0d`
- Initial provider-request fingerprint: `875811944da1e0157b800135bb6a84f488961837168f04c0ae70f5deeef226d1`
- Source-selection schema: closed world, at most 8 advertised handles

The inspectable execution was GitHub Actions run `32087406505`, job `95562855296`. Its preserved artifact was named `issue-101-live-32087406505` (artifact ID `9307193406`, digest `sha256:91eef2b7cd874f8b4460a04ae05188297bc3cca59d18071244684f0cae06191a`).

## Initial model response

The provider returned a schema-valid `need_source` response. It selected exactly two advertised handles:

```text
T0
P3
```

The carried review state was:

- `RV1` (question): asks for the exact definition of the response profiles and “uniformly attenuating,” and whether the theorem reduces to proving uniform decay on the interval.
- `RV2` (concern): asks whether the proof quantifies the tolerance before choosing point-dependent thresholds/neighbourhoods and then legitimately obtains one uniform threshold using compactness and the bound below 1.

Both review items motivated the two-handle source request. The response contained no final findings because it requested the one permitted source-rescue turn.

Provider usage for this accepted initial response was:

- requests: 1
- input tokens: 2,448
- output tokens: 390
- total tokens: 2,838

There was no hidden provider retry in this recorded exchange.

## Thorn protocol failure

After accepting the valid two-handle model selection, Thorn automatically expanded the requested source through unresolved prerequisite context. That deterministic expansion produced 18 handles. `build_rescue_turn()` then applied the same eight-handle limit to the expanded set and rejected Thorn's own enrichment:

```text
source rescue requests at most 8 addresses, got 18
```

Therefore the run stopped **before the rescue model turn**. This witness is a source-rescue protocol failure, not a model source-selection error and not a semantic-review miss.

Issue #128 owns the repair. The intended invariant is that all valid model-selected handles remain mandatory while automatic prerequisite enrichment uses only the remaining source budget, preferring nearby unresolved prerequisites and never expanding a valid request beyond the configured bound.

## Experiment disposition

Do not retry, tune, or reinterpret this C0 response as part of the old frozen experiment. Preserve it as the pre-repair boundary witness.

Any semantic run after #128 changes production source-rescue behavior and therefore belongs to a newly frozen experiment with its own assurance tree, replay contract, request accounting, and explicit live-run authorization.
