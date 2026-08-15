# Recorded and replayed semantic evaluation

Thorn's semantic regression suite can record successful provider exchanges once and replay the exact same model responses later with **zero live API calls**. This is intended to make evaluator, scoring, reporting, and other plumbing work cheap without pretending that an old model answer evaluates a changed semantic input.

## Record a live run

Recording is explicit and still requires the normal API key:

```bash
export OPENAI_API_KEY=...
thorn-eval eval/cases \
  --model gpt-5.6 \
  --review-context ir \
  --case-filter missing_nonzero_hypothesis \
  --record-dir .thorn/eval-recordings
```

`--record-dir` wraps the normal live evaluation provider. Each successful attack, semantic-review, or defender response is written as one JSON recording. Failed or unstructured provider responses are not recorded.

Recordings include:

- the model identifier;
- the exact system prompt text;
- the exact rendered user payload;
- the expected structured-output JSON schema;
- the structured provider response;
- the input/output/total token usage observed on that live exchange.

## Replay without an API key

Use the same semantic inputs and point `thorn-eval` at the recording directory:

```bash
OPENAI_API_KEY="" thorn-eval eval/cases \
  --model gpt-5.6 \
  --review-context ir \
  --case-filter missing_nonzero_hypothesis \
  --replay-dir .thorn/eval-recordings
```

Replay does not construct the OpenAI provider or require `OPENAI_API_KEY`.

The summary distinguishes logical provider work from billable work:

- `requests` / per-case `semantic_request_count`: logical provider exchanges exercised by the evaluation;
- `live_requests` / `live_request_count`: actual live provider calls in this run;
- `replay_hits` / `replay_hit_count`: logical exchanges satisfied from recordings;
- `input_tokens`, `output_tokens`, `total_tokens`: tokens consumed by the current run, therefore zero for pure replay.

Historical token usage remains in each recording so later cost-reporting work can analyse what the original live run consumed without making replay look billable.

## Exact fingerprints and stale recordings

Every recording filename is the SHA-256 fingerprint of Thorn's canonical provider request envelope. The fingerprint includes all model-facing semantic inputs:

```text
provider adapter contract
+ model
+ request kind
+ full system prompt
+ rendered theorem/IR payload
+ structured-output schema
```

A material change therefore produces a different fingerprint. If the current request has no exact recording, replay fails loudly instead of silently falling back to a live call or accepting an obsolete answer.

This is especially important for Math IR development. If IR selection or rendering changes, the old IR recording is **not evidence about the new IR** and replay must miss. By contrast, changes to evaluator scoring, output formatting, diagnostics plumbing, or other code downstream of the unchanged provider request can reuse the recording safely and cheaply.

The same rule applies to raw and targeted review. A changed prompt, model, theorem packet, targeted `SemanticReviewItem`, or response schema requires a fresh explicit live recording before that semantic configuration can be replayed.

## Budget-safety contract

Replay is fail-closed:

1. it never falls back from a replay miss to a live provider;
2. it does not require or inspect an API key;
3. changing model-facing input invalidates the exact fingerprint;
4. ordinary CI remains keyless and does not create live recordings;
5. live recording remains an explicit/manual operation.

This first record/replay tranche deliberately does not choose pricing, cache-discount policy, cheaper models, or full-regression tiers. Those are separate parts of issue #13 and can build on the exact exchange format here.
