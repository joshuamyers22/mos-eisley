# R16-02 provider-free qualification evidence

Disposition: the named two-real-user privacy campaign passes on the four native
targets and actual Windows-hosted WSL2. **R16-02 remains open** for its missing
stable OS/authentication/workflow and privacy composition boundaries. This does
not approve stable publication or substitute for accountable owner security
review. See the [frozen profile and reuse review](V1_STABLE_PROFILE_PRIVACY.md).

Runtime candidate: immutable public rc.16, source
`14eb79d52950f340aba159815222e04e6ea864e3`, epoch 2; enrolled metadata SHA256
`1882d3db109ebc3b6f0d5c84de8dec0eecde96a47da5f72ad444d133b30ea3bc`.
Installed wheel SHA256
`2fef66d8ca749243de89f76170830c7f054f1a15f86bb8d395575529d275a143`.
Each report binds its signed native archive, controller and actor independently.
The wheel API lane and signed native CLI lane remain distinguishable.

## Actual host results

| Host / architecture | Controller / run | Real non-root UIDs | Receipt groups / seconds | Report SHA256 |
| --- | --- | --- | --- | --- |
| macOS arm64 | `13b904c` / [42335310882](https://github.com/joshuamyers22/mos-eisley/actions/runs/42335310882) | 610, 611 | 38 / 169.968 | `2b791c61095c2d21c46588196c4b2762305e49f020dd208313b97c66ec8957d8` |
| macOS x86_64 | `13b904c` / same run | 610, 611 | 38 / 384.601 | `39888064a7e7f5e5caee951b8cc8cab8a862ac459eb211614a6694fd202beb4d` |
| Linux arm64 | `482c837` / [42336310688](https://github.com/joshuamyers22/mos-eisley/actions/runs/42336310688) | 1002, 1003 | 38 / 172.100 | `8aaccc82eda5160c4197bbe06e4ccfa7bde71c7ee5d4c5a1eaad3a1683a2bfb2` |
| Linux x86_64 | `482c837` / same run | 1002, 1003 | 38 / 195.134 | `5a0f0165f8f36fa5712b30c9f5df62d797f162fdf5177e884de4583a5eae9800` |
| Actual Windows-hosted WSL2, Linux x86_64 | `482c837` / same run | 1000, 1001 | 38 / 293.171 | `d3cd932c63e4ad4ce4a10741fdc3652e0e6c6e729f4ce5ade9c7be1ece614c4e` |

Windows provenance records Server 2025 build 26100, Ubuntu 24.04 distribution
version 2 and actual `6.18.54.1-microsoft-standard-WSL2` kernel. The inherited
Windows-host metadata field `candidate_commit` refers to its controller/source
bundle; the report's `candidate_source` is the signed application source above.
This is not full general WSL2 qualification, an ARM WSL2 result, or Windows-native
support. Mount/native-auth/Docker/OAuth/cancellation and other general platform
assertions still need their declared evidence.

All five reports assert both accounts removed and the synthetic fixture tree
removed. Root only provisions/observes/cleans; actual product processes execute
under the recorded real UIDs with cleared supplementary groups and private
HOME/config/cache/temp/workspaces. No accounts were created on the owner's Mac.

## Assertions and limits

Both snapshot and SQLite receive both access directions. Positive controls cover
new state, fresh-process context/resume, owner listing, selected memory, memory
change pause/refresh/off, forged owner save refusal, same-owner exclusion with a
separate held-writer process, valid SQLite transcript/artifact references, stale
selection refusal, transfer/migration/export and logical deletion. Operation-local
cache fill/reuse and teardown pass. This establishes nonblocking writer exclusion,
not concurrent-writer throughput or a shared multi-user service.

Foreign operations refuse list/load/write/delete/memory and supported lifecycle
previews/apply paths without persistent fixture mutation or canary disclosure.
Original private roots test kernel access; readable re-owned copies retain
embedded foreign identities to test application guards. Owner-generated SQLite
artifact/cursor tokens are challenged under the foreign principal. Invalid CLI
options cannot qualify a refusal. Exported/migrated copies are separate retained
objects until fixture teardown; logical deletion is not physical erasure.

Twenty native recorded checks (two users × two stores × five hosts) observe zero
IP activity under their stated profile, each with a detected loopback positive
control and quiet negative control. Linux observes descendant socket/connect
metadata. Apple pktap observes only packets attributed to the direct PID/effective
PID, with zero kernel drops; arbitrary child tools are outside that claim. No raw
pcap or application packet payload is retained. These checks explicitly disable
updates and select no memory/tools. They do not establish default updater,
subscription-client or enabled-tool egress behavior.

Each actor also observes two OpenAI SDK serialized requests through an in-process
mock transport: selected user/project memory on/off, distinct actual-UID memory
canaries and ambient session/project/credential exclusions. Empty and contaminated
controls are rejected. This is four serialized SDK cases per host, with no
external provider connection; it is not native subscription traffic observation.

Provider calls: **zero**. No native sign-in, grant, old ledger, real private history,
evaluation/selection store or sampling artifact was opened, renewed or created.
Receipt groups are engineering assertions, not independent evaluation samples or
eligibility evidence. Historical rc.14 grants, uncertainty and failures are intact.

## Failures and controller corrections

The [first campaign](https://github.com/joshuamyers22/mos-eisley/actions/runs/42333874296)
at `d10e39a` passed 30 initial groups on each Mac. Linux stopped before its first
product case because managed Python was staged beneath the runner's temporary
directory; WSL2 proved real host provenance, then failed chmod of an absent optional
managed-Python directory after selecting system Python. The shared interpreter
path/optional directory correction did not change product bytes. First reports
and logs remain retained; failures are not converted into passes.

Expanded `13b904c` passed both Macs. Linux/WSL2 passed snapshot owner/privacy and
signed native checks, then stopped at the first network observer command. The
`482c837` diagnostic reproduced exit 1 and permission refusal for reopening
root-owned `/dev/stderr` after dropping UID. All three diagnostic hashes are
`eb822c75b923783b3ac86704aeb4d265c1a82d1518c8eca9018396d957735607`.
Using strace's already inherited descriptor corrects that harness boundary;
positive/negative controls and both-store affected qualification then pass. Passing
Mac evidence was reused without relabeling it as a new controller execution.

A final review added stdlib-only asset enrollment **before dependency installation
or candidate import**, and deferred the controller's publisher-parser import until
wheel pins pass. All four retained public archives pass the new preinstall verifier;
malformed enrollment/path controls reject without executing controller or candidate
code. This later order guard is separately tested; it does not relabel earlier
remote executions as having run the later controller. One fixture initially used a
nonliteral AST expression and failed its expected-reason assertion; a literal
synthetic map corrects that test without weakening the guard.

## Remaining work and fresh authority

The [profile](V1_STABLE_PROFILE_PRIVACY.md) preserves the intended full v1 contract.
Remaining cases include native sign-in/auth rotation and applicable containment
on the missing OS hosts, enabled-memory native workflow, allowed API inspection,
independent direct review, and the remaining search/replay/index/notification,
model-selection/reset and live/default-egress privacy composition. No absent API,
historical image, source-only test or unavailable subscription tool is counted as
an installed live success. Separate R16-01 and R16-03–08 rows remain unchanged.

Owner-controlled target access is pending; no SSH host inventory is configured on
this operator host. Hosted CI stays provider-free. Before any live call, bind the
actual host, admitted client bytes/auth context, exact image, route/model/effort,
synthetic fixture/destinations, memory/tools, maximum calls, output/time/spend
limits, expiry and cancellation/cleanup rules, then obtain fresh exact-case owner
authorization. Combine missing boundaries in one canonical workflow where valid;
do not repeat rc.14's paid permutations without a distinct unproven boundary.

Current local Codex 0.166.0 is outside rc.16 admission through 0.163.0; Claude is
2.1.283. An isolated admitted Codex client or a separately reviewed candidate
compatibility change is required before fresh local calls. No automatic downgrade,
credential transplantation, API fallback or current-client compatibility claim
was made. Direct review also needs current profile/campaign/launch/custody and
spend approval; historical formal review is not transferable authority.

Further local preparation found the retained official Codex 0.163.0 binary without
changing the default 0.166.0 pointer. Signed installed rc.16's native executable
is `59251a50cfa57271355679ce5dc55054e2d71d6cdaee780a427654867ac595d3`.
Readiness passes for cached Codex 0.163.0
(`8813367285524ac798dd96d1b071aea30d58708c7226fd236cd275cf1cfdee31`)
and Claude 2.1.283
(`d8cb1e5c79684cc12a8bfc813e3a2073406921b6245744b3009be3ab5651d21e`)
using the application's exact native environment allowlist. A reduced preparation
environment first reported Claude signed out; the canonical context passes without
operator sign-in or credential edit/copy. Do not diagnose a signed-out account from that reduced
context. Native status is metadata-only, distinct from the provider-free campaigns.

A separate installed fake-client rehearsal passes a proposed six-call SQLite
memory journey: three calls/provider, selected synthetic memory, cold resume,
changed-memory refusal before dispatch, explicit refresh and off. Its first fake
client was correctly refused because it was inside the active project; a second
rehearsal exposed double-counting native and usage completion files. Both fixture
failures remain retained. Corrected rehearsal counts usage slots separately and
uses fake clients outside the project. These are fake-client scopes only, never
real provider authorization or reuse of historical grants.

Frozen local proposal SHA256:
`78a136c9c7c0c1c88efbd317e74ed4f9237858da2aa02dcc3be6bfb9a1975e16`.
It pins the private controller/client/environment/location/workspace/session
bindings, gpt-6-sol/medium and claude-sonnet-5/high, three calls each, 120 seconds per
native call, 16-KB input, 8-KB text, 8,192 reported output tokens, 20-minute campaign
and fresh one-hour per-case grants. No tools, operator retries, repairs or API
fallback. Native billing/retry exposure requires explicit acceptance. Fresh owner
authorization was requested for this exact packet after checks pass; pending
authorization is not approval. No real inference or live grant has been created.

Admission is per profile: this tool-free memory packet depends on the named
conversation/storage/memory and native-client gates. Unfinished direct-review,
inspection, replay/index/cache integration, selection/reset or other-platform
gates continue to block their affected profiles and stable approval. A scoped
memory authorization cannot waive those gates or admit another workflow.

## Combined gate and separate replay finding

The final permitted `make check` held all 908 non-Markdown inputs unchanged:
3,960 source tests passed (17 skipped), coverage 86%, lint/types/export/build
passed; the installed-wheel suite ran 2,919 tests with one setup error and 13
skips. Overall exit 2, 4,970.418 monotonic seconds; original log SHA256
`b3dc5ee325b007a653ec6ffa36623d7a34034ef9efd674407b80012381607f60`.
This is a **failed combined gate**, not a passing result.

The error was `test_result_pin_and_local_tampering_are_rejected` in
`ReviewObservationTests.asyncSetUp`: the observation differed from the selected
policy/roster. A substantial wall-clock advance occurred during this run. A fresh
installed-wheel run of the complete module plus an explicit observation-at-expiry
control passed all 20 tests, without source changes, in 19.029 test seconds.
Focused log SHA256
`6e4a1453b279d54704229e3fd9af201fac79b57f005b6aa31a7c8a9164655a83`.
Expiry is consistent with the failure, but the original exact timestamps/condition
were not retained, so its precise cause is unproven. No production window was
relaxed, old receipt repaired or original failure relabeled. Earlier controller
`482c837` passed all 14 required CI checks; that distinct run does not replace this
failed gate. Required checks on the final PR head and accountable review remain
necessary before merge or dependent affected live qualification.

A separate provider-free, two-real-UID diagnostic used the exact public Linux
arm64 executable inside an isolated, network-disabled Linux container. Existing
UIDs 10001 and 65534 were used; no Mac accounts or provider credentials were
created/mounted. Owner-generated built-in recorded demo replay succeeded (exit 0).
Foreign replay of its original private root refused (exit 2). A separately copied,
readable 0755/0644 run retained the first UID as filesystem owner; the second UID's
`mos replay` **succeeded (exit 0)**. Fixture bytes stayed unchanged. Executable SHA256
`47ac6ef24130508d978f2f76350825554e0a2d5b99559e56c143d2fa8b28b982`.
This diagnostic is not an actual-target campaign or proof of disclosure through
default private permissions. It demonstrates that legacy recorded replay does not
independently enforce the proposed private owner boundary for readable foreign
input. `run.store` describes private authoritative run directories, while CLI replay
currently verifies explicit supplied artifacts without owner admission.

Disposition: **block the full private-replay profile**. Resolve private-state
admission versus an explicitly separate portable-verification contract in an
accountable review; implement and test the resulting boundary in a new candidate
before claiming the broader owner-refusal guarantee. Do not silently exclude replay
from v1 or describe this result as a privacy pass. Snapshot/SQLite conversation
receipts above do not cover this separate legacy path.

Retained initial diagnostic failures: the first controller expected recorded demo
exit 0 instead of its documented revise verdict exit 1; the next attempted chmod
after chown under a deliberately reduced root capability set and raised
PermissionError. Setting modes before relinquishing ownership completed the
synthetic fixture. Neither failed attempt established a cross-owner conclusion.
All three containers were removed. No product source or published bytes changed.
The completed report and cleanup are retained privately under
`.work/replay-owner-probe-permissions`; content-free report SHA256
`4514f00852dc347602be2d1621184bd9f2291a29e2311d94eb4b50dc22d2c235`; cleanup SHA256 `24e68363892f1e8914103d2edb619d0b132b1e24ebc1fe01c7fefd35e30e7900`.
