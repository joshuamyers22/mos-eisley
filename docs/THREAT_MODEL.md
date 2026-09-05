# Threat model: OpenAI provider preview

Owner: Josh Myers. Scope: recorded workflows plus explicit `openai-run`, macOS/Linux.

Assets: user files, supplied private source, API key, run integrity and verdicts.
Untrusted inputs: brief and prompt content, OpenAI responses, cassette JSON,
citation text and restored artifacts.
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
