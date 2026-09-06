# Threat model: OpenAI provider preview

Owner: Josh Myers. Scope: recorded workflows plus explicit `openai-run`, macOS/Linux.

Assets: user files, supplied private source, API key, run integrity and verdicts.
Untrusted inputs: brief and prompt content, OpenAI responses, cassette JSON,
citation text, restored artifacts, and explicitly discovered skill packages.
Trusted components: installed code and dependencies, CLI arguments, parent/output
directories, OS user and official OpenAI SDK. OpenAI is the sole external service
in the live command.

| Abuse case | Implemented control | Remaining limit |
|---|---|---|
| Instructions in a diff invoke host commands | No execution or network tools | No live prompt-injection quality claim |
| Huge/non-file input blocks the process | Bounded reads, nofollow, nonblocking fstat | Ancestors and same-UID processes trusted |
| Critic fails and run accepts | Critic/provider quorum, separate error outcome | Labels in fixtures do not prove independence |
| Evidence references nonexistent text | Validate quote against named brief field | Truth and location semantics require evaluation |
| Judge invents or duplicates findings | Validate upheld IDs before verdict | Judge can still uphold a wrong claim |
| Repository config widens permissions | No implicit configuration discovery | Policy layering deferred |
| Run artifact changes | Fixed artifact set, schema and hashes, result replay | No signatures/authentication |
| Log leaks rejected values | Generic boundary errors | Artifacts intentionally retain user inputs |
| Index fails after saving | Index is optional, completed run remains usable | No automatic index rebuild command yet |
| Malformed model tool history is replayed | Role, alternation, call-ID and result-pair invariants | Canonical contracts are not vendor conformance |
| Model loops or stalls | Iteration/tool ceilings and asyncio provider/tool deadlines | Blocking adapter code can still block the event loop |
| Tool returns excessive output | Canonical result byte bound before another request | No disk spool or token-aware truncation yet |
| Agent adapter leaks exception content | Generic public failure with hashed journal boundary | Artifacts intentionally retain configured fixtures/responses |
| Partial agent run is mistaken for complete | Append-and-fsync journal; manifest written last | Partial runs are forensic inputs, not resumable runs |
| Prompt is sent unintentionally | Named file plus required `--allow-data-transfer` | Acknowledgement cannot classify confidentiality |
| API credential leaks into output | Key only from environment; generic errors; regression scan | Same-UID processes and inherited environments are trusted |
| Provider retains sensitive input | Responses request sets `store=false` | Organization policy and provider retention controls still apply |
| Provider response violates expected shape or size | Decoded HTTP body capped before SDK JSON construction; narrow schema validation; canonical response ceiling | Headers remain transport-owned; accepted body still buffers up to 1 MB; streaming disabled |
| Reasoning/tool state corrupts across turns | Preserve encrypted reasoning and native call IDs; pair results exactly | Credentialed conformance has not run |
| Model spend grows unexpectedly | Bounded requests, reviewed prices and transactional shared reservations | Participating local runs only; operator rates/provider caps trusted; not an invoice ceiling |
| Concurrent runs overdraw shared capacity | Atomic admission and conservative unresolved charges | Same ledger/local filesystem required; copied or rolled-back databases bypass accounting |
| Recorded evaluation worker reads host labels/secrets | No host mounts, blinded stdin job, no inherited API key, offline container probes | Reviewed image/daemon trusted; input content itself may leak labels |
| Isolated worker consumes resources or outlives attached client | Cgroup limits, bounded pipes, exact-ID removal and detached lease watchdog | Host/guardian death or daemon outage can still require orphan investigation |
| Worker substitutes or replays provider requests | Host snapshots exact request; expiring single-use grant; bounded private pipes and mandatory shared spend admission | CLI lifecycle is fixture-tested only; stolen grant permits its one approved call; no credentialed evidence yet |
| Host crashes across broker dispatch | Fsynced authorization/admission/outcome chain plus exact shared-ledger entry inventory; incomplete states never authorize retry or release | Operator must prove old process is dead; response may be lost while spend remains charged |
| Synthetic or partial broker output enters empirical scoring | Separate conformance artifact requires response/audit/assignment/settled-ledger agreement and has literal `promotion_eligible=false` | Credentialed conformance has not run; reviewed conversion to live result provenance is not implemented |
| Conformance request leaks private labels or expands authority | Payload is deterministically built from one blinded brief/route plus reviewed policy; strict schema, exact-request binding and explicit consent | Brief content leaves the host when the paid-capable command is separately authorized and run |
| Grader identity is substituted after review | Domain-separated Ed25519 signature binds exact adjudication, declared human ID, rubric and enrolled public key; receipt binds trusted policy and batch | Policy enrollment/key custody are operator-controlled; signatures do not prove physical identity, independence, timestamp accuracy or judgment quality |
| One grade or an unauthenticated tie-break silently becomes ground truth | Dual gate reverifies distinct grader keys, embeds both signed originals, recomputes agreement, and requires a domain-separated resolver signature over exact conflict coverage and both trust policies | Enrolled humans can collude or be wrong; resolver and policy administration remain trusted; only a dedicated non-promotable scorer accepts the lineage |
| Observation compilation discards authenticated grading lineage | Separate compiler reconstructs the full private execution chain, reverifies dual grading, and binds observations to both policies and the complete resolution digest | Source artifact retention is operator-controlled; legacy scoring rejects the distinct schema |
| A score is presented as authenticated after its source artifacts change | Dual scorer reverifies the full private and signed chain, requires exact split coverage, and carries every source digest into a reproducible report | Content hashes have no external notarization; inputs and trust-policy distribution remain operator-controlled |
| A statistically eligible route silently becomes active | Scoring and holdout deny promotion; the authenticated promotion still denies activation; a separate short-lived eligibility gate reverifies the full chain and three distinct activation signatures while retaining literal runtime/configuration denial | No runtime consumer, atomic installer, rollback, or traffic monitor exists |
| Lax freshness or cost ceilings are substituted around valid operational evidence | Activation policy is independently signed, its digest is bound into the readiness snapshot, and both signed artifacts are pinned into the derived receipt | Activation trust-policy distribution and policy-signing judgment remain trusted |
| Catalog, pricing, conformance, or drift claims are fabricated | Exact-route assertions and evidence digests require an enrolled operational signature and must pass every signed threshold | Mos Eisley does not fetch or validate the referenced evidence; one readiness signer attests all four categories |
| A persona-skill result is caused by another route change | Evaluation identity includes exact instructions and skill package identity; sealed arms may differ only by prompt asset | A package digest authenticates retained bytes, not authorship or safety |
| Skill comparison is selectively stopped or repeatedly tested on holdout | Fixed complete matrix and six-metric family are pre-registered; CLI atomically consumes a lineage-bound local claim before holdout scoring | The owning OS user can delete/bypass local claims or coordinate repeated studies elsewhere |
| A passing skill report silently changes runtime behavior | Reports deny promotion; signed receipts and archive bindings still literally deny installation, activation, and configuration mutation | Rollback, installation, revocation, and drift gates are not implemented |
| A skill grader promotes its own result | Promotion authority IDs and keys must be disjoint from every grader and resolver across calibration and holdout | Human collusion and authority-policy distribution remain external trust concerns |
| A stale or substituted skill promotion is accepted | The signature binds the authority policy, exact skill/prompt, seal, both reports, and a bounded UTC window; CLI authentication uses the host clock and recomputes both lineages | There is no trusted external clock or revocation anchor |
| A revoked policy reuses an older control message | Signed sequence floor plus a pinned append-only local anchor require exact latest-state equality and monotonically preserve revocations | Whole-anchor rollback/cloning or false bootstrap remains possible without an external monotonic witness |
| Operational approval silently substitutes a nearby model or effort | Snapshot must cover exactly selected routes and required fallbacks; route equality and literal `allow_model_substitution=false` reject replacement | A future runtime must preserve this exact-match check immediately before dispatch |
| Passing runtime preflight races a later emergency stop | Preflight is capped by a signed short lifetime and fixes dispatch/configuration authority to false | Future one-use dispatch must atomically recheck an external latest-state witness immediately before provider send |
| A project skill shadows a trusted user persona | No winner-by-path lookup; exact source-qualified digest plus explicit project activation | Invocation approval is not persistent trust or a quality signal |
| A skill changes after validation | Complete bounded package snapshot is used for activation/resources and committed by digest | Same-UID races and trusted ancestor replacement are not contained |
| A retained skill archive hides substituted instructions or a reserved script path | Canonical file records, package digest, bounded paths, and semantic reparse rebuild the exact descriptor and instruction digest; `scripts/` and authority booleans fail closed | Archives prove content identity, not authorship, safety, promotion currency, or install eligibility; there is no extraction path |
| Retained bytes are substituted beside a valid promotion receipt | Host-clock release binding reparses the archive, recomputes both authenticated evaluation lineages, requires exact `SkillIdentity` equality, and expires with the signed receipt | The binding has no external clock or revocation witness and grants no install or runtime authority |
| Skill metadata requests tools or executes code | `allowed-tools`, toolbundles, scripts, executable bits, symlinks, and special files fail closed | Prompt text can still influence model behavior; skills currently have no machine capabilities |
| A skill package exhausts parsing or context | YAML indirection is rejected; file/count/depth/package/body caps are enforced; discovery output omits bodies | Byte counts are not provider token counts; quality and cost need paired evaluation |

Timeouts use cooperative asyncio cancellation; adapters must not block the event
loop. There is no untrusted plugin loading. Disk errors propagate; partially
written directories lack a valid manifest. The original review pipeline writes an
event summary after completion. The fixture agent loop fsyncs hash/status boundary
events during execution, but its journal is not a standalone response transcript.

Before calling this production-ready: complete credentialed conformance, convert
validated broker artifacts into explicitly live evaluation provenance, then connect the live
adapter to critic/judge policy without weakening quorum failure behavior.
Before executing code: a tested OS boundary including host reads/sockets, process
resources and cleanup. Before publishing: authenticated IPC and stale-head checks.
