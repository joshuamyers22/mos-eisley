# Threat model: offline foundation

Owner: Josh Myers. Scope: initial recorded-review CLI, macOS/Linux.

Assets: user files, supplied private source, run integrity, verdict correctness.
Untrusted inputs: brief content, cassette JSON, citation text, restored artifacts.
Trusted components: installed code and dependencies, CLI arguments, parent/output
directories, OS user, recorded adapter. No credentials or external services exist.

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

Timeouts use cooperative asyncio cancellation; adapters must not block the event
loop. There is no untrusted plugin loading. Disk errors propagate; partially
written directories lack a valid manifest. Event summaries are written only after
review completion, so crash-time partial transcripts are not promised.

Before live providers: explicit provider/data policy, conservative token/cost
limits, bounded response reading, redacted request logs and capability conformance.
Before executing code: a tested OS boundary including host reads/sockets, process
resources and cleanup. Before publishing: authenticated IPC and stale-head checks.
