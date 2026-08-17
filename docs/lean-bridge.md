# Thorn's Lean bridge

> **Status:** product/design thesis under empirical evaluation in issue #115.
>
> This document describes the intended role of Lean in Thorn. It is deliberately broader than [`lean-handoff.md`](lean-handoff.md), which documents the currently implemented backend and supported subset.

Thorn's goal is not automatic arbitrary-LaTeX-to-Lean translation.

The opportunity worth testing is narrower and, if it works, more useful to ordinary mathematicians:

> **Recover mathematically meaningful commitments from ordinary human-written proofs, identify local proof operations that Thorn understands precisely enough to formalise without guessing, replay those exact operations independently in Lean, and turn the result into source-linked evidence about the argument the author actually wrote.**

The manuscript remains ordinary LaTeX. Canonical Proof IR remains the semantic centre. Lean is a downstream checker of mechanically justified fragments, not a second interpreter of the paper and not a language the author is expected to learn in order to use Thorn.

Issue #77 established the first real proof of life for this path. Issue #115 is now testing whether the idea is genuinely useful on ordinary proofs, with an explicit `GO`, `NARROW`, or `STOP` outcome. The design below should therefore be read as a hypothesis and a set of guardrails, not as a commitment to a broad Lean roadmap.

## The nearby project Thorn should not become

There is an obvious but undesirable trajectory:

```text
ordinary LaTeX
    -> increasingly heroic translation
    -> more formal annotations needed
    -> more author restructuring needed
    -> generated Lean needs manual attention
    -> the author is effectively writing Lean indirectly
```

That path may eventually formalise more mathematics, but it would undermine one of Thorn's central product goals: useful proof-quality assistance for people who write and read mathematics in ordinary mathematical language.

Thorn should not measure Lean progress by how close it gets to forcing every paper through a complete formalisation pipeline. If meaningful checking requires authors to write Lean-flavoured LaTeX, add declarations solely for elaboration, debug generated proof scripts, or reorganise natural proofs around tactic-friendly structure, that is evidence against the automatic bridge rather than a reason to push those requirements onto the user.

Complete theorem-level formal verification may occasionally emerge when every relevant part of a proof happens to be mechanically recoverable. That would be a welcome limiting case, not the normal workflow or product promise.

## The product thesis: local formal replay

The important formalisation unit need not be the whole theorem. It can be a mechanically closed local proof operation inside a theorem whose surrounding mathematics remains informal.

Conceptually:

```text
ordinary human-written LaTeX
        |
        v
canonical source-linked Proof IR / recovered proof argument
        |
        v
identify a mechanically closed local proof operation
        |
        v
independent Lean replay of that exact operation
        |
        v
source-linked human-facing evidence

  ✓ formal replay accepted
  ! formal replay conflict
  ○ blocked by missing formalisation context
  — unsupported / inappropriate to formalise
```

A sophisticated proof may have a structure like:

```text
deep informal argument
    -> apply a previous theorem at a particular parameter
    -> rewrite using an established equality
    -> specialize another result
    -> choose a constructed witness
    -> deep informal argument
```

Lean may be unable, or it may be inappropriate, to formalise either deep informal region automatically. That does not imply that the connecting operations are worthless to check.

Those transitions are common locations for real proof defects:

- a theorem is applied without one of its preconditions;
- a quantified result is specialized at the wrong object;
- a local assumption leaks outside its scope;
- an equality is rewritten in a way not justified by the recovered term structure;
- cancellation silently needs a nonzero or algebraic side condition;
- a cited result yields a weaker conclusion than the next proof state claims;
- a witness is named without the property needed for the existential claim.

If Thorn has already recovered one of those operations precisely enough to replay it, Lean can provide evidence about that local commitment even when most of the surrounding theorem is not formalised.

Potentially useful operation families include theorem/result application, specialization and instantiation, implication elimination, equality rewriting and substitution, exact witness introduction, and scope-sensitive use of assumptions. This is **not** a roadmap list. Issue #115 should determine which operation families occur naturally and often enough to justify implementation.

## The success metric is actionable intelligence, not formalisation coverage

"Percentage of the paper formalised" is not a useful North Star for this work. In an ordinary research paper there is rarely a principled denominator, and a small number of high-value checks can matter more than broad shallow translation.

The better question is:

> **Which mathematical commitments made by the manuscript can Thorn independently stress-test, and does the result give the human useful information about the argument they actually wrote?**

A useful Lean bridge should therefore optimise for:

- semantic fidelity to the author's presented proof operation;
- independent checking where the operation is mechanically fixed;
- exact source provenance;
- understandable blocked/conflict states;
- usefulness inside otherwise informal proofs;
- no requirement that the author interact with Lean to benefit.

It should not optimise for the largest possible generated `.lean` file.

## Assurance semantics

Lean adds a distinct assurance regime to Thorn. That regime is valuable only if its meaning remains narrow and explicit.

### Formal replay accepted

A replay should be described as formally accepted only when Thorn has mechanically fixed, without semantic guessing:

- the exact local premises/context supplied to the check;
- the exact target proposition;
- the exact recovered proof operation, or a proof term that faithfully represents that operation;
- the relevant symbol, domain and signature assumptions;
- the connection from all of those objects back to canonical Proof IR and source provenance.

Lean acceptance then means approximately:

> **Under the mechanically represented premises and interpretation, this recovered proof operation was accepted by the pinned Lean checking environment.**

It does not by itself mean:

- the whole theorem is formally proved;
- every surrounding informal proof step is valid;
- Thorn recovered the entire manuscript correctly;
- every relevant assumption has been represented;
- the paper is verified or certified.

If every relevant proof edge of a theorem were eventually recovered and independently accepted, stronger theorem-level claims might become justified. Thorn must derive such a state from explicit complete evidence rather than infer it from partial success or visual proximity.

### Formal replay conflict

A Lean failure is mathematically interesting only when the operation being checked was itself mechanically fixed strongly enough that the replay should close if the recovered operation is valid under the represented premises.

The initial user-facing interpretation should therefore be something like:

> **Formal replay conflict:** Thorn's recovered version of this proof transition did not close under the premises represented here.

It should not immediately become:

> The theorem is false.

A conflict can arise from several sources:

- a genuine mathematical problem in the manuscript;
- a materially missing premise;
- harmless formalisation context that Thorn has not supplied;
- an incorrect or incomplete Thorn recovery;
- a lowering/backend defect.

The rest of Thorn's evidence must distinguish those cases before the result is promoted into a stronger mathematical finding.

### Blocked by formalisation context

Lean often needs explicit type, structure, coercion or typeclass information that a competent human reader would infer harmlessly from the local mathematical setting.

That is normally a boundary of automatic formalisation, not a defect in the paper.

Issue #98 owns the important distinction between:

- context that must be made explicit for a formal system but is adequately determined for human mathematics; and
- a load-bearing assumption whose plausible alternatives materially change the proof and which the paper has not actually established.

Future Lean work must not convert elaboration requirements mechanically into human-facing paper findings. Conversely, Thorn must not silently choose a mathematically consequential structure merely because doing so makes generated Lean compile.

### Unsupported or inappropriate to formalise

Some proof steps are genuinely deep, heuristic, diagrammatic, analytic, context-heavy, or simply outside Thorn's mechanically recovered semantics.

That state is not itself a mathematical defect.

A key hypothesis under test in #115 is that unsupported surrounding mathematics need not erase useful local evidence. If an exact theorem application in the middle of an otherwise opaque argument is independently checkable, the architecture should eventually be able to preserve that local result rather than making whole-theorem support an all-or-nothing gate.

## Replay the author's operation, not merely the target theorem

There is a crucial difference between these two questions:

1. **Is the author's claimed proof transition valid under these premises?**
2. **Can Lean find any proof of this target from these premises?**

For Thorn's proof-quality role, the first question is usually more valuable.

Suppose a manuscript claims that a conclusion follows by specializing Lemma 3 and discharging a particular premise. If a powerful tactic or theorem search finds an unrelated route to the same conclusion, it may establish that the conclusion is true under the supplied context while completely failing to test the author's presented argument.

That distinction leads to several guardrails:

- exact local replay is high-value when Thorn has recovered the operation;
- alternate proof discovery must be labelled according to what it actually establishes;
- successful arbitrary proof search must not be used to launder a defect in the author's proof path;
- failure of arbitrary proof search is not evidence that the mathematical statement is false;
- generic tactic synthesis should not be used merely to increase apparent formalisation coverage.

If model-assisted Lean generation is explored in the future, it should be treated as a separate capability over a mechanically fixed proposition and premise set. "A formal proof was found" and "the author's presented transition was formally replayed" are different assurance statements.

## Lean is also a stress test for Thorn

The formal boundary can provide value even before it finds a defect in a paper. It can expose places where Thorn itself has claimed more semantic precision than its evidence warrants.

The first #77 implementation already produced such an example. A source identifier `N` could not legitimately become Lean's natural-number type merely because conventional mathematical spelling made that interpretation tempting. Forcing the recovered structure through a formal backend exposed the confidence-laundering risk, and Thorn was changed so that an arbitrary `N` is not silently promoted to canonical `ℕ`.

That is an important second role for Lean:

> **Formalisation pressure is an independent test of whether canonical Proof IR really contains the precision Thorn thinks it contains.**

Future formal replay may reveal problems such as:

- a domain or type was never actually established;
- two source symbols were incorrectly identified;
- local scope was lost;
- a result application was over-promoted from a plausible match to a definite operation;
- a theorem precondition disappeared;
- a substitution has ambiguous replacement sites;
- load-bearing context exists in source but is not represented or mechanically reachable.

When this happens, the fix belongs at the earliest Thorn layer that lost or over-promoted the distinction. The Lean renderer must not compensate by guessing enough structure to make the code compile.

## Architectural invariants

### Canonical Proof IR remains the semantic centre

Lean is a consumer of canonical semantics. It must not become a second parser of LaTeX, a second interpretation of mathematical prose, or an independent semantic representation.

If the Lean backend needs information that canonical Proof IR does not establish, that is either:

- an explicit formalisation boundary;
- evidence of a genuine upstream representation/recovery gap; or
- evidence that the proposed check is not appropriate.

It is not permission for the backend to reinterpret source text privately.

### No confidence laundering

No formal term, theorem application, type, domain, structure, symbol signature or assumption may be emitted more confidently than the canonical evidence that supports it.

Ambiguity remains ambiguity. Missing prerequisites remain missing. Unsupported mathematics remains unsupported.

The fact that a choice is conventional, convenient or sufficient for Lean elaboration does not make it mechanically established.

### Formal results remain source-linked

Every replay result should stay attached to the existing canonical result, claim, proof edge, transformation and source identities that justify it.

A mathematician should be able to answer:

- what operation did Thorn think I performed here?
- which premises did the formal replay use?
- what target did it check?
- why was it accepted, blocked or conflicted?
- where is that operation in my LaTeX?

They should not need to inspect generated Lean to recover those answers.

### Local evidence should survive unsupported neighbours

If #115 supports the local-proof-island hypothesis, a mechanically closed operation should be independently checkable even when unrelated or surrounding proof regions are unsupported.

This is the main conceptual reason to consider evolving beyond #77's current result-oriented proof-of-life boundary. It should be done by deriving local check units from existing proof/transformation semantics, not by creating another Lean-specific semantic graph.

### Formalisation state remains distinct from other Thorn assurance regimes

Lean status is neither deterministic structural analysis nor LLM semantic review.

For example, the same proof region may simultaneously be:

- structurally well recovered;
- carrying an LLM review concern;
- formally replayed for one local operation;
- blocked from formal replay for another operation.

Reports and the proof visualiser should preserve those distinctions. Issue #111 owns formalisation-state presentation over the existing proof argument graph.

## The normal user experience should stay in LaTeX and Thorn

The intended user is a mathematician writing ordinary mathematics.

Generated Lean should be available as an inspectable engineering/audit artifact, but it should not be the primary interaction surface. A useful user-facing result is closer to:

```text
Lemma 4, proof step 3

Formal replay conflict

The recovered application of Proposition 2 requires P(a), but no
available local premise discharges P(a) at this point.

Source: paper.tex:184-187
```

than to:

```text
application type mismatch at generated.lean:42:17
```

The normal repair loop should be:

```text
read Thorn's source-linked result
    -> inspect/fix the mathematics or LaTeX
    -> rerun Thorn
```

not:

```text
open generated Lean
    -> debug elaboration
    -> copy formal annotations back into the paper
```

Issue #93 owns the eventual user-facing onboarding/CLI seam. It should expose only capabilities whose assurance boundary is settled and useful; it should not turn generated Lean into a mandatory workflow merely because a backend exists.

## Anti-goals

Future Lean work should carry a substantial burden of proof if it moves Thorn toward any of the following:

- automatic whole-paper LaTeX-to-Lean translation as the product goal;
- requiring authors to write Lean-flavoured LaTeX;
- annotations whose main purpose is satisfying Lean elaboration rather than clarifying the mathematics;
- requiring users to inspect or edit generated Lean during normal paper writing;
- guessing ambient types or algebraic structures to maximize compilation success;
- arbitrary Mathlib theorem search used merely to make a target provable;
- generic tactic synthesis used as a substitute for recovering the author's proof operation;
- treating `sorry`, holes or explicit formalisation obligations as checked mathematics;
- presenting a checked fragment as certification of its surrounding theorem or paper;
- inventing formalisation coverage percentages without a mechanically meaningful semantic denominator;
- reshaping canonical Proof IR merely because a particular Lean encoding is convenient.

This does not forbid Mathlib, tactics, automation or richer formalisation forever. It means each addition must be justified by the mathematical information it returns to the human and by the fidelity of the connection to the manuscript.

## A decision rule for future Lean features

A proposed Lean feature should be able to answer this question clearly:

> **Does this let Thorn independently test a mathematically meaningful commitment already made in ordinary human-written mathematics, and return honest source-linked evidence about that commitment?**

Strong evidence for adding a feature includes:

- the operation occurs repeatedly in ordinary proofs;
- canonical Proof IR already represents it precisely, or a general upstream fidelity gap has been independently demonstrated;
- a valid/invalid paired case shows that formal replay distinguishes a real proof-quality issue;
- the check remains useful inside a larger unsupported proof;
- users do not need to change how they naturally write the mathematics;
- the resulting status can be explained without exposing Lean internals.

Weak evidence includes:

- the feature makes larger generated Lean files possible;
- a tactic can solve more benchmark goals;
- adding annotations would make elaboration easier;
- the target theorem can be proved by some unrelated formal route;
- the feature improves a formalisation percentage without a clear user-facing signal.

Issue #115 is the first systematic attempt to apply this decision rule to real proof material.

## Relationship to current work

This note sits between implementation documentation and the eventual technical trust paper.

- **#77 / [`lean-handoff.md`](lean-handoff.md)** — the implemented minimal Proof-IR-to-Lean proof of life and its exact supported subset.
- **#115** — the empirical `GO` / `NARROW` / `STOP` evaluation of whether local Lean replay is useful on ordinary proofs.
- **#98** — the distinction between harmless formalisation context and a materially missing mathematical assumption.
- **#93** — user-facing onboarding and CLI seams; should expose the settled capability without making Lean a prerequisite for authoring mathematics.
- **#111** — visualisation of formalisation/check state on the existing proof argument graph.
- **#100** — the eventual technical "How Thorn works" paper, which should incorporate the evaluated and settled version of this design.

This document should not be used to pre-authorize a speculative sequence of Lean syntax/features. Follow-up implementation issues should be driven by recurring high-value cases observed in #115.

## After issue #115

The note should remain useful regardless of the experimental outcome.

### If the result is `GO`

Update this document with the observed high-value operation families and the settled architecture for local check units/results. Preserve the guardrail that complete paper formalisation is not the default objective.

### If the result is `NARROW`

Record the deliberately bounded family where Lean provides useful independent evidence. Treat the boundary as a product feature, not as a temporary embarrassment to be expanded away without new evidence.

### If the result is `STOP` or `PIVOT`

Keep this document as the rationale for why Thorn deliberately chose not to grow into an automatic LaTeX-to-Lean system. A negative result from #115 is useful project knowledge and should not disappear from the repository simply because the implementation path stops.

## Summary

The intended opportunity is the space between ordinary mathematical prose and complete formalisation.

Thorn should use Lean where canonical Proof IR has already made a precise mathematical commitment available for independent checking. It should return that evidence in the language of the manuscript and its proof structure. It should remain explicit when formalisation is blocked, and it should refuse to guess merely to increase formal coverage.

If this works on ordinary proofs, Lean becomes a useful independent proof-quality instrument inside Thorn. If it only works after authors begin writing for Lean, the experiment should stop before Thorn turns into a less pleasant route to the same destination.
