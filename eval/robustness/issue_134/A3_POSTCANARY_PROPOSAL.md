# Issue #134 A3 post-canary scientific freeze

This is the new A3-only pre-#125 scientific freeze prepared after the provider/replay reliability tranche and a successful live provider-readiness canary.

## Scientific case

- Case: `A3` — result applicability
- Source: `eval/robustness/issue_101/variant_result_applicability.tex`
- Source SHA-256: `f53d7c5eed1f0145406c3c4dda50680a852b14c2c4cd3705c17940ec5f27f403`
- Target: `thm:uniform-decay`
- Ground-truth question: does semantic review detect that the finite-cover/compactness principle is applied to bounded but noncompact `[0,1)`?
- A1 and A2 are preserved from the earlier accepted measurements and must not be resampled.
- Issue #125 remains blocked until this pre-#125 A3 observation is preserved and adjudicated.

## Qualified provider boundary

- Model: `gpt-5.6`
- Representation: `thorn-proof/1`
- Protocol: `thorn-proof-review/2`
- Prompt: `proof_language_reviewer_v2`
- Production `src/thorn` tree: `9143b4063cd42269370fd365e315473655989583`
- Provider adapter SHA-256: `8207a7400d2a88042572033ff84abf36ce94548558bf912b0c42d1b90b4c1e08`
- Provider runtime lock SHA-256: `3752103f04c419832dcc75d1124cc6d3fc39c2a13989e07ed6adafc9ce83dbc3`
- Python: `3.11.16`
- OpenAI SDK: `3.3.0`
- Pydantic: `2.13.4`
- Provider retries: `0`

Successful readiness evidence:

- Readiness run: `32232914558`
- Readiness evidence SHA-256: `a1de222ac38133c05d638a9329c5652949380bea88497f1749c03b4862f20767`
- Readiness initial profile: `896ce0be6cf47684114d35950cc744caa954883bd89b1833bc68c3cddf0df0b1`
- Readiness rescue profile: `fb3441a94ec6780ce7ec977498407ec76bd6d0e31948f7d22983c6ad75da8d55`
- Readiness result: two completed provider responses, zero retries, exact keyless replay verified.

## A3 request identity

- Frozen repository revision: `884415531f0b0ddc28e5f7fa528b001b6285e72b`
- Frozen A3 initial execution fingerprint: `996dbae0c3d2b86f33c00b099612c0be9e9792556b7d3a35667fdff9b803ccbf`
- Generic runner SHA-256: `6992939c6ba05b18e667f0916c7655a7aa5d483f4324ed93e1aa98f3ced1cec6`
- Manifest: `a3_postcanary_manifest.json`
- Keyless freeze run: `32245136957`
- Keyless freeze artifact: `9362287889`
- Freeze artifact digest: `sha256:fd0f71d24c873c0af8a724c29eef75a8140e3cce943e01add1f6f1fa90ecd93e`
- Generic runner preflight result: `preflight-ready`

## Hard live bounds

- Cases: `1`
- Provider attempts: at most `2` (initial plus at most one bounded rescue)
- Aggregate input-token cap: `40,000`
- Output cap per request: `4,096`
- Aggregate output-token cap: `8,192`
- Source rescue: at most once; production source-address cap remains `8`
- Implicit provider retries: `0`

At GPT-5.6 Sol standard pricing checked on 2026-08-19 ($5/M input, $30/M output), these hard token caps imply a conservative maximum of USD `$0.44576` before any cached-input discount. This is a budget ceiling, not an expected cost.

## Stop conditions

Stop without adapting or resampling if any of the following occurs:

1. current `src/thorn`, provider adapter, runtime lock, runner, source hash, target, model, representation, protocol, prompt, or initial execution fingerprint differs from this freeze;
2. the successful readiness evidence is stale, incompatible, or cannot be verified exactly;
3. the next provider request would exceed a frozen provider-attempt/input/output bound;
4. more than one rescue turn would be required;
5. accepted provider evidence cannot be replayed exactly keylessly;
6. A1/A2 would be resampled or issue #125 would need to be changed.

## Authorization boundary

The manifest deliberately has `paid_execution_authorized: false`. Scientific authorization is external to the manifest and must be explicit after this freeze is checked in and reviewed. A scientific authorization applies only to this exact A3 freeze and does not authorize A1/A2 resampling, #125 work, retries, or adaptive reruns.
