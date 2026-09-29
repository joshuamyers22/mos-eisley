# G3 source audit: NIST Juliet C/C++ 1.3

**Date:** 2026-09-27

**Authority:** Joshua Myers authorized auditing Juliet as a candidate for the narrow single-human objective-oracle study in [ADR-0010](adr/0010-g3-single-human-oracle-study.md).

**Verdict:** **Conditional source candidate for a separately validated, narrow flaw-detection benchmark. Not yet an objective-oracle G3 case source or a sealable cohort.**

## Scope and checked evidence

This is a source-level audit, not an exhaustive per-case or oracle validation. I
read NIST's suite page, v1.3 release log and technical note, the linked v1.2
design guide, and the downloaded v1.3 archive. I did not run the cases, select a
sample, form independence groups, assign splits, inspect any project sampling or
label store, or create labels or study outcomes.

| Check | Observation | Consequence |
|---|---|---|
| Identity and rights | NIST lists suite #112, 64,099 C/C++ test cases, 118 CWEs, public-domain/CC0 terms, and SHA-256 `ada9d7e1c323d283446df3f55bdee0d00bda1fed786785fe98764d58688f38eb`. The downloaded 152,957,342-byte ZIP matched that digest. [N1] | Source bytes can be pinned; use rights appear suitable for a public benchmark. |
| Archive structure | Read-only ZIP listing found 106,316 entries, including 101,235 `.c`/`.cpp` source files. One inspected CWE190 case contains a target bad function and two good functions in one source file. | File count, case count and independent-task count are different. A whole file cannot automatically be labeled clean or defective. |
| Label leakage | In the inspected CWE190 case, function names and comments explicitly identify bad/good paths and the target weakness. The design guide describes this naming as part of static-tool scoring. [N2] | A model could score well by reading cues. Any blind transformation must preserve code behavior and be validated before use. |
| Oracle semantics | The guide says cases target one intended flaw but may contain unrelated flaws. The v1.3 note says many faults have no externally apparent failure. [N2, N3] | Suite annotations alone are not a validated executable oracle for all G3 outcomes. A build pass, crash, or sanitizer result cannot be assumed to settle every target label. |
| Known source defects | NIST documents thousands of memory leaks, remaining systematic issues, and many “good” variants that remove a problem with hardcoded values while changing behavior. [N3] | Source-specific exclusions and task-preserving controls are needed; Juliet good/bad variants are not automatically realistic repair pairs. |
| Related variants | The guide defines a case by CWE, functional variant, flow variant and language; many files come from templates. The archive has repeated functional stems across flow variants. [N2] | No case-level IID claim is justified. A source-family grouping rule must be reviewed from the complete eligible inventory before sampling. |
| Platform and task fit | The guide describes static-analysis-tool assessment and Windows-specific variants; the v1.3 note adds build options. [N2, N3] | The case frame is synthetic C/C++ flaw recognition, not ordinary Mos Eisley user tasks or a representative whole-session cost mix. The runnable subset needs a pinned toolchain/platform audit. |

The v1.2 guide is used only for the documented design lineage and is linked by
the v1.3 suite page. The v1.3 release and archive take precedence where details
changed. The inspected source example supports a leakage finding, not a claim
that every case has the same layout.

## Decision against the proposed G3 protocol

Juliet may support a **restricted benchmark claim** about detecting specified
C/C++ flaws in a validated subset, if exact inputs, labels and oracle behavior are
independently reproduced. It does **not currently support** the proposed clean /
defective whole-task study with 400 IID independent groups per class, exact
binomial thresholds, ordinary-task audit, or broader completion, harmful-action
and cost-saving claims. The proposed $200,000 cap and six arm IDs remain planning
values; this source audit supplies no price or implementation evidence.

The current [`LabelSource`/`SamplingFrame` schema](../src/mos_eisley/evaluation/context_study.py)
has no Juliet/oracle source category. Its policy seal requires a random
ordinary-task audit in both splits and two distinct enrolled signed graders.
Juliet cases must not be disguised as `ordinary_task`, `seeded_mutant`, or
`historical_bug`. A new source/label mode and its failure tests are needed under
ADR-0010. One human plus two keys remains one human.

## Required qualification before a preregistered cohort

1. Pin the exact archive, toolchain and build platform; enumerate an immutable
   eligible case inventory with documented exclusion reasons. Confirm source
   rights and any required redistribution handling for transformed task packets.
2. Specify a narrow task whose success and failure are mechanically observable.
   Independently reproduce the oracle on known-good, known-bad, deliberately
   mislabeled and ambiguous controls. Freeze thresholds and exclusions before
   evaluating the study arms. Cases without a decisive oracle remain ineligible.
3. Remove or neutralize answer cues from the **task view** under a reviewed,
   deterministic transformation. Check that the transformation preserves the
   target semantics and does not leak through filenames, symbols, comments,
   compiler output, or support files. Keep raw source and transformations in
   controlled evidence, outside sampling artifacts.
4. Define the unit of assignment and source-family grouping with a documented
   audit of related variants. Derive selection and label-observation probabilities
   from the actual prospective design; never infer them from the suite count.
   Recompute available groups, dependence, estimand, power and inference method.
5. Define the single-human oracle/grader trust model and amend the verifier so it
   records operator and implementation custody without claiming two independent
   humans. Preserve disagreements and undecidable cases. Have Joshua perform an
   outcome-blind, signed method/source review under ADR-0008 and ADR-0010.
6. Reprice the actual six-arm task, labels, oracle runs and all retries against an
   approved ceiling. Register the exact source inventory digest, transformation,
   protocol, scorer and budget externally **before** outcome-bearing assignment.

**Stop rule:** if the source cannot yield a sufficiently large, leakage-resistant
subset with independently reproduced objective outcomes and defensible groups,
use it only for calibration or a descriptive pilot. Keep broad G3 open.

## Sources

- **[N1]** [NIST SARD, Juliet C/C++ 1.3 test suite #112](https://samate.nist.gov/SARD/test-suites/112): identity, size, checksum, stated rights and disclaimer. Archive checksum was independently verified locally; no case was enrolled.
- **[N2]** [NSA Center for Assured Software, Juliet v1.2 C/C++ user guide, hosted by NIST](https://samate.nist.gov/SARD/downloads/documents/Juliet_Test_Suite_v1.2_for_C_Cpp_-_User_Guide.pdf): design purpose, case naming, template variants, intended target flaws, good/bad scoring and natural-code limitations. This is design background for v1.3, not a v1.3 case-by-case certificate.
- **[N3]** [NIST Technical Note 1995, Juliet 1.3 changes and known problems](https://samate.nist.gov/SARD/downloads/documents/Juliet_1.3_Changes_From_1.2.pdf): remaining systematic problems, absent evident failures, hardcoded-value pseudo-fixes and compilation changes.
- **[M1]** Mos Eisley [G3 context-study policy and label guide](G3_CONTEXT_STUDY.md), [project plan](mos-eisley-plan.md), and [ADR-0010](adr/0010-g3-single-human-oracle-study.md): current seal and approved narrow planning limit.
