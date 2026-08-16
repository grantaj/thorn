# Source-addressable proof-skeleton compression

Issue #49 asks whether Thorn can reduce the **initial** mathematical context sent to a
semantic model by roughly an order of magnitude without turning the Math IR into a hard
information bottleneck.

This is a keyless representation experiment. It does not change production `thorn review`
and does not authorize live model calls.

## Why this differs from compact IR

PR #48 measured the current compact semantic projection at 7,937 characters versus 11,943
characters for raw theorem packets over its frozen 16-case challenge set: 33.5% smaller.
That is useful engineering evidence, but not enough compression by itself to justify forcing a
strong model to live inside a potentially lossy parser interpretation.

The source-addressable skeleton is deliberately more aggressive:

```text
LaTeX
  -> rich source-preserving Thorn Math IR
  -> tiny proof skeleton
       -> formula fragments + compact atoms + graph topology
       -> source addresses for omitted prose

Thorn-side source map
  address -> exact extracted text + provenance
```

The initial renderer never includes the source map. A later semantic protocol may allow the
model to request selected addresses, but source fetching is intentionally out of scope for this
tranche.

## Skeleton notation

Local addresses are deterministic within one result:

- `T0` — theorem/result statement;
- `H1`, `H2`, ... — explicit statement hypotheses;
- `L1`, `L2`, ... — proof-local constraints;
- `D1`, `D2`, ... — definitions;
- `R1`, `R2`, ... — directly referenced results;
- `C1`, `C2`, ... — proof claims in source order;
- `Q1`, `Q2`, ... — claim qualifiers;
- `E1`, `E2`, ... — candidate support edges.

Formula fragments are retained when they can be extracted mechanically from the source. A
`~` payload means the node is intentionally withheld from the initial packet and should be
considered source-on-demand content, not absent information.

Support-edge codes are intentionally terse:

- `r` result reference;
- `q` equation reference;
- `d` definition;
- `p` named property;
- `c` prior claim;
- `x` explicit reason.

`?` marks an ambiguous candidate edge and `!` an unresolved one. Confident edges have no
status suffix. These markers reproduce Thorn IR state; they do not assert mathematical truth.

An illustrative packet can therefore look like:

```text
T0:a,x,y|a\ne 0|ax=ay|x=y
H1:a\ne0
C1:a(x-y)=0
C2:a\ne0|x-y=0|x=y
E1:C1>C2:c
```

while the local source map still retains the original theorem sentence, complete claim prose,
source spans and exact support wording.

## Keyless public-corpus measurement

Run the normal local linguistic path with:

```bash
OPENAI_API_KEY="" python scripts/measure_skeleton_compression.py \
  --output /tmp/skeleton-compression.json
```

The script compares, for every public evaluation fixture:

1. the existing raw `TheoremUnit` packet;
2. the current compact semantic IR rendering;
3. the new initial proof skeleton.

It reports exact character and UTF-8 byte sizes, aggregate and median compression ratios,
source-address counts, withheld-node counts and the number of public cases reaching at least
10x raw-to-skeleton compression. It constructs no semantic provider and makes zero live
requests.

`--structural-only` exists only as a degraded/debug path. The CI measurement installs
`en_core_web_sm` and runs the normal spaCy-enriched Thorn IR path with `OPENAI_API_KEY=""`.

## Interpreting the public corpus

The 56 public fixtures are deliberately small unit-test-like manuscripts. They are useful for
correctness, determinism and regression coverage, but they are a hostile benchmark for a 10x
compression ratio because theorem statements and short formulas form a large irreducible
fraction of many packets.

Therefore:

- public-corpus compression is a lower-bound / sanity measurement;
- failure of tiny fixtures to reach 10x is not by itself a negative result;
- substantial real-paper proofs are the intended scale test.

The design target is **median >=10x initial-context reduction on substantial real-paper
results**, not 10x on every synthetic three-line proof.

## Private real-paper extension

Do not copy private or corpus-specific papers into this repository. `thorn-private` or another
private harness can import the public library seam:

```python
from thorn.proof_skeleton import build_proof_skeleton
```

Build the normal result-level `SemanticReviewRequest`, then compare
`ProofSkeleton.render_initial()` with the corresponding raw and compact packets. The returned
`ProofSkeleton.sources` remains available locally for exact source recovery and future
source-on-demand experiments.

## Gate before paid evaluation

Do not spend on the frozen #47 A/B/C run merely to compare a 33.5% representation saving.
First determine whether this more aggressive skeleton makes order-of-magnitude initial
compression plausible on realistic proofs.

If it does, the next paid experiment should compare raw review against a two-stage protocol:

```text
skeleton
  -> OK / finding
  -> or NEED_SOURCE(addresses)
       -> exact requested raw snippets
       -> final review
```

That experiment should count the **total** tokens across both stages. The skeleton only wins if
source recovery remains selective enough that the end-to-end workload is materially smaller
without losing mathematical decisions.
