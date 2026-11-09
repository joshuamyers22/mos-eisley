# Private recorded replay owner admission

Status: implemented; combined/CI gates and accountable owner review pending. Owner: Joshua Myers; operator: Codex.
Started 2026-11-07. User authorizes closing the legacy replay owner gap, PR #374
review, a new protected signed candidate and affected privacy qualification, then
only freshly authorized missing live boundaries. No earlier live packet is renewed.

Selected guidance: AGENTS, Python engineering, agentic/adversarial verification,
threat-model and work-note templates. Plan §17.2 requires owner admission for
replay; README describes these as private run files. Existing CLI documentation
provides no portable foreign-owner verification contract. Decision for this fix:
`mos replay`, `load_run` and skill provenance loading remain private-state readers.
Do not add a bypass flag or implicitly import/claim another owner's records.
Portable verification/import, if needed later, needs its own explicit design and
ownership/provenance contract. Ordinary bounded input readers remain unchanged.

Objective: refuse readable foreign-owner recorded run roots and artifacts before
content decoding; preserve same-owner replay, manifest/digest/schema/semantic
verification and read-only behavior. In scope: legacy recorded-review run bundle
loading, descriptor-relative bounded private reads and regression coverage. Agent
run readers, index writers and other R16-02 composition remain separate gates.
No recorded run, sampling/evaluation store, credential or real provider output is
read for this change; only built-in synthetic fixtures.

Threat model: an untrusted local UID supplies a readable foreign run, substituted
artifact, hardlink/symlink or changing directory entry. Resolve real/effective UID
from OS, require matching context, private owner-held directory and single-link
regular files; open root/children with no-follow, use relative held descriptors,
check metadata/entry stability and finite byte limits, close every descriptor.
Administrative/malicious same-owner mutation is outside confidentiality protection;
no encryption, physical erasure or immutable snapshot guarantee is claimed.
Non-POSIX readers fail closed before candidate I/O; v1 native Windows stays gated.

Blocking rubric: positive same-owner replay and skill/guidance provenance pass;
foreign root/file, unsafe permissions, special files, links and substitutions
refuse without content decode, disclosure or writes; bytes/limits/hash checks stay
strict; focused tests, full combined gate and affected real-user signed checks
pass. Retain all first failures, including the prior full local gate failure in
R16_02_PRIVACY_QUALIFICATION.md. Runtime changes require a new candidate; published
rc.16 and historical evidence stay unchanged.

Budget: six active hours implementation/review, one combined gate (up to four
hours), one evidence-driven correction per distinct failing boundary. No provider
calls during repair/CI. Accountable security review and protected-environment
approval are required before merge/signing as applicable; no admin bypass.
Stop dependent live work on unexplained required failure or missing current
case-specific authority/host access. Approval is never inferred from elapsed time.


Implementation review: `run.store._load_run_bundle` holds one admitted directory
through manifest and all artifact reads and decoding, retaining all hash/schema/
brief/result checks. New `run.private_replay` checks real/effective identity,
directory and opened artifact metadata, final-component no-follow, single-link
files, byte limits and descriptor/name metadata stability. Child paths are relative
to the held directory, so replacing the named root cannot redirect reads. Read-only
0500/0400 same-owner fixtures remain usable. No automatic chmod/chown/import of
user input; arbitrary ancestors are not asserted to be symlink-free. The trusted OS
UID boundary does not resist a malicious owner/admin making an explicit copy.

Focused source checks: nine new private replay tests, five existing replay guards,
six store/CLI, nineteen skill, fifteen guidance and twenty-five task-state tests
pass. Strict types pass for the affected runtime/tests/controller. Initial lint and
type checks caught formatting, a late-bound fixture inode, deprecated Iterator
annotation and a TestCase.run fixture-name collision; corrected without a product
admission exception. Forty-five distribution tests, including newly enrolled actual
published rc.16 predecessor identity, pass. Wheel smoke now retains the private
replay, existing replay-guard and store/CLI modules as installed-artifact tests.

Candidate preparation: bump only project metadata/lock identity to rc.17; runtime
dependencies remain frozen. Add a required four-target signed replay job after
protected preparation; each host installs the exact signed archive under two real
non-root users, checks both directions and cleans accounts/roots. Existing
installation/both-store/downgrade checks remain, and actual immutable rc.16 upgrade
is explicitly enrolled. Publication also depends on the new replay job. Its
content-free reports are separate workflow artifacts; do not relabel the existing
public qualification inventory or claim these jobs have executed before signing.
No signing key custody, protected environment or publication authority is changed.

First development carrier check stopped at the owner-positive demo with
JSONDecodeError. A bounded synthetic-only diagnostic identified ModuleNotFoundError
for openai: the base Python lacks the worker image's dependency environment.
Using `/app/.venv/bin/python` reached successful owner replay and both foreign root
refusals, then fixture setup raised PermissionError while changing a file's mode
after relinquishing ownership under reduced root capabilities. Set all fixture
modes before chown instead; no runtime admission guard was relaxed. Original
reports/diagnostic/cleanup remain under `.work/replay-fix-*`; no first failure is
reclassified or counted as a complete two-user pass. These are unsigned development
checks on an isolated Linux carrier, never signed actual-target qualification.

Earlier PR head 403e7fc has all fourteen required checks passing, including source
and package. This does not erase its failed local combined gate or qualify the
new replay fix. Historical rc.16 live-memory proposal 78a136c9 remains an unapproved
proposal for source 14eb79d; it cannot authorize the new runtime. Prepare a fresh
packet only after the applicable new candidate gates pass. User-provided date
metadata is not authorization, host access or a renewed grant.


Completed development carrier result: exact unsigned rc.17 wheel SHA256
`8f00e030f614bba0d1a2140a598fe124bd873aa9c30a44b0494ae85246f3c869`,
existing real UIDs 10001 and 65534. In both directions, owner replay and fresh
process replay pass; original private roots, readable owner-preserved foreign
roots and mixed-owner artifacts refuse. Fixture bytes remain unchanged, no
credentials are mounted and the network-disabled container is absent after
cleanup. Report SHA256 `c55fab569727f6795ecc73345aadd8d4a246fe3b62d0f560868db2182c568716`; cleanup SHA256 `a09879e439358890bd1b3bd88c6ee323ee8d7c98aa6b860c5b746413cd6d799a`.
This is development evidence, not signed/native-target qualification. Prior failed
attempts remain separate. Four controller admission guards pass; eighteen release
publication tests pass, including the mandatory replay-job dependency.

The combined gate runs against the staged non-Markdown input manifest under
`.work/replay-owner-fix-gate`; earlier `.work/gate-result.json` and its failed log
are not overwritten. Final outcomes and exact reviewed PR head are recorded in
[PR #374](https://github.com/joshuamyers22/mos-eisley/pull/374) before any merge or
tag. Protected release preparation/signing and four-target signed checks are
unexecuted at this record. Runtime dependency/export bytes remain unchanged apart
from the project version in its manifest/lock; no stable publication is requested.
