# Blinded evaluation execution adversarial review

Date: 2026-09-05. Scope: blinded batch export, request-bound recorded execution,
route-blind grading packets, adjudicator provenance and observation compilation.
Reviewer: implementing assistant self-review; no live provider, human adjudicator
or independent security/statistical review was used.

Disposition: suitable for offline fixture rehearsal and evaluation-pipeline tests.
It is not a sandbox, a live sweep runner or evidence sufficient to promote routing.

## Findings and corrections

| Impact | Finding | Correction / evidence |
|---|---|---|
| High | Passing dataset cases to a backend would expose expected findings and split labels | Project a dedicated execution request containing only an opaque sample ID, route and brief; the execution CLI accepts no dataset or mapping |
| High | Hashing readable assignment keys would permit case-ID guessing | Derive sample IDs with HMAC-SHA256 and a fresh 256-bit nonce; retain only the nonce digest |
| High | A fixture could be attached to the wrong prompt or omit difficult rows | Bind every exchange to canonical request hash and require exact batch coverage |
| High | Showing raw results to graders exposes model/backend identity and invites preference bias | Generate a separate grading packet without route, candidate, case ID, split or mapping fields |
| High | Judgments could be reused after outputs or labels change | Bind adjudication to the grading packet and verify the complete content-addressed artifact chain before compiling observations |
| High | Grading could accept an incomplete or incorrectly assigned plan, including missing or unknown cases | Share complete dataset/matrix validation across export, grading and scoring; reject before following private case references |
| Medium | A detection judgment could claim success from an empty critique, or more false positives than emitted findings | Reject both contradictions during compilation and cover them with regression tests |
| Medium | Provider failures might disappear because they have no grade | Require raw results for every request; compile failures without a content judgment and preserve them as error observations |
| Medium | Reviewer name alone is weak provenance | Record adjudicator ID, human/fixture method, rubric digest and UTC completion time in the adjudication digest |
| Low | Predictable output paths could overwrite prior evidence | Continue exclusive mode-0600 artifact creation and reject existing targets |

## Remaining issues and potential changes

- Isolation is structural only. A future live adapter must execute in a process with
  no access to the dataset, mapping, environment credentials beyond its provider,
  or unrelated filesystem content.
- Provenance fields are self-asserted, not authenticated. Add signatures or a
  trusted append-only attestation service before routing promotion matters.
- Candidate-generated prose can reveal its own identity even though controller
  metadata is removed. Consider deterministic identity redaction and measure its
  effect before relying on grader blinding.
- A grader can recognize repeated briefs across candidates and repetitions. A
  grading UI should randomize presentation, prevent side-by-side comparison, and
  record per-item timing without revealing group membership.
- The current artifact compiler verifies integrity and exact coverage but not
  inter-rater agreement, rubric calibration or adjudicator conflicts. Add duplicate
  blinded ratings and a resolution protocol. Judgments still summarize detections
  and false-positive counts rather than mapping every emitted finding to a label;
  add per-finding attribution before using human grades for routing promotion.
- Recorded latency and micro-dollar cost are fixture claims. Live executors need
  measured monotonic timing, provider usage evidence and a versioned price snapshot.
- Holdout access, clustered confidence intervals, multiple comparisons, statistical
  power, prompt-profile features, OOD detection and policy promotion remain open.

Next review trigger: an isolated live OpenAI evaluation adapter or the statistical
design and adjudicator-agreement protocol, whichever is implemented first.
