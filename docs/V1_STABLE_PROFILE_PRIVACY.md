# Frozen v1 profile and privacy qualification

Status: R16-02 active; **stable qualification is not yet complete**. Owner: Joshua
Myers. Baseline: published rc.16, source
`14eb79d52950f340aba159815222e04e6ea864e3`, epoch 2. Metadata SHA256
`1882d3db109ebc3b6f0d5c84de8dec0eecde96a47da5f72ad444d133b30ea3bc`.
Controller source, host identity and evidence hashes are recorded separately.

## Advertised contract

This freezes the intended stable contract, not a claim that all rows already pass.
Plan §§16–17 and §27.1 remain authoritative. Unsupported/native Windows work is
deferred to v0.1.1; actual Windows-hosted WSL2 remains a v1 requirement. Planned
targets must not be described as qualified before their gates pass.

| Boundary | Stable profile | Required evidence |
| --- | --- | --- |
| Operating systems | macOS arm64/x86_64; Linux arm64/x86_64; Windows-hosted WSL2 using Linux x86_64 on private Linux filesystem | Actual host/architecture, signed installation, owner isolation, native auth and applicable contained workflow; WSL Windows build, distribution, kernel, filesystem and WSL version |
| Storage | Local snapshot and SQLite; private owner-only directories/files | Same-owner read/write/list/resume/delete/concurrency and cross-owner refusal, including references and lifecycle operations |
| Default authentication | Recorded, no provider credentials or inference | New conversation, cold resume, memory controls, recovery without network or ambient private history |
| Subscription authentication | Owner's native Codex/Claude sign-in; admitted client version only; explicit immutable per-case grants | Client-owned sign-in, refusal/expiry/cancel/rotation and exact workflow; never transplant credentials to CI |
| API authentication | Explicit owner credential and current spend policy/ledger, bounded calls and data-transfer consent | Auth/rotation/refusal and exact API tool profiles; subscription success does not prove API authentication |
| Memory | Explicit curated user and project memory; on/off and refresh; fresh conversation has fresh history | Selected memory only, owner/workspace binding, disabled/changed memory refusal, no ambient transcript ingestion |
| Tools | Tool-free conversation; explicitly authorized read-only repository inspection; Docker-contained authoring/review/integration; direct review remains its own workflow | Scope/refusal, actual containment, creator approval and new tests; inspection unavailable on subscription route must remain unavailable |
| Privacy | Trusted OS identity, private storage and model/cache/reference scopes; no unintended analytics/storage egress | Two actual non-root users per store; positive and adversarial controls; outbound observation with explicit scope |

This is not automatic routing, an evaluation/study enrollment, remote storage, a
multi-user shared server, hostile-root protection, native Windows support, or a
latency/reliability/billing guarantee. Sampling metadata grants no authority. No
sampling registry, custodian map, labels, outcomes or private selection stores are
read or repaired by this work.

Client admission is exact: Codex 0.161.0, 0.162.1 or 0.163.0; Claude 2.1.283.
The reused rc.14 profile specifically uses Codex 0.163.0/Claude 2.1.283, 120-second
native calls and at most 8,192 reported output tokens, without operator correction
or automatic harness retries. Grants still bind client bytes, auth context,
role/model/effort, owner, workspace/session, invocation counts, expiry and output
limits; native subscription billing/retry exposure is never represented as a
precise USD cap. This does not change the CLI's lower default deadline.
API generation remains its separate reviewed model registry and current spend
policy/ledger; its transport admits at most 60 seconds. Tool-free means zero tool
calls. Explicit API `/inspect` admits only `repo_list`, `repo_search`, `repo_read`
in the selected workspace (five iterations/six calls maximum); subscription
inspection stays unavailable. Curated memory is bounded by the existing combined
32-KiB content ceiling plus active input budgets. No price, default, tool or
admitted-client policy is changed by the qualification freeze.

OS evidence is version-bound: the native campaign uses macOS 15 images and
Ubuntu 22.04 images; the WSL2 campaign uses Windows Server 2025 build 26100 with
Ubuntu 24.04. Reports bind actual kernel/architecture. These are concrete
qualification baselines, not a claim covering every distro, OS major version or
future upgrade. Stable advertising must retain its exact reviewed version/build
matrix; a different OS boundary needs case-specific evidence. WSL private Linux
filesystem admission and general platform gates remain as specified in §27.1.
API repository inspection is the explicit OpenAI route. Credential attachment
and other unadmitted MCP/tool profiles stay behind their existing separate gates;
this work does not activate them to satisfy an unrelated matrix row.

## rc.14 evidence reuse review

[The rc.14 review](RC14_QUALIFICATION_REVIEW.md) records actual macOS ARM native
Codex 0.163.0 and Claude 2.1.283 subscription runs, both storage backends, no memory
and tool-free chat/cold resume, then coding through model review, creator approval,
integration and fresh tests. The bounded native profile was 120 seconds, 8,192
reported output tokens, zero correction/retry/repair. Each store had 14 dispatches,
13 completions and a separately retained planned uncertain cancellation. The first
snapshot harness assertion failure and separately authorized fresh SQLite run are
preserved; these are not 28 successful calls.

Through rc.16 the only runtime source changes are setup diagnostics and bounded
public update inventory. The subscription adapters, coding contracts and Docker
runtime requirements are unchanged. Existing signed rc.16 install/offline receipts
and source equivalence support **contract reuse**, without relabeling an rc.14
execution as an rc.16 execution. No old grants, uncertain calls or ledgers are
renewed or retried.

Reusable: the exact macOS ARM, admitted-client, both-store no-memory subscription
workflow and unchanged contract assertions. Missing: macOS Intel/Linux/actual
WSL2 native-auth and applicable containment boundaries, enabled memory, API
inspection, direct review, and real-principal privacy/lifecycle/outbound cases.
The four signed distribution targets and the narrow Git-review WSL2 run are not a
substitute for these missing live boundaries. Cross-architecture unchanged model
semantics can be reviewed once; host sign-in, client launching, process ownership,
filesystem and Docker isolation cannot be inferred from ARM macOS.

At the initial rc.16 assessment, all 418 runtime Python files, project/lock,
runtime export and Dockerfile matched frozen rc.16. The rc.14→rc.16 runtime diff
is exactly `app_release.py` (bounded preview inventory) and `app_update_cli.py`
(setup platform/Python diagnostics). That comparison supports only the historical
reuse rationale, not a new host/auth/latency result.

The subsequent [private replay correction](REPLAY_OWNER_ADMISSION_WORK_NOTE.md)
prepares rc.17: `run/store.py` changes and `run/private_replay.py` is added (419
runtime Python files); project/lock version identity changes, while runtime
dependency pins/export and Dockerfile remain unchanged. Source tests and unsigned
two-real-UID development checks pass within their named scopes. New-candidate CI,
owner review, protected signing and affected signed qualification remain required.
Published rc.16 evidence is not silently rebound to this changed runtime.

## Provider-free real-user campaign

`profile-privacy.yml` stages the enrolled public rc.16 wheel and matching signed
native archive/bootstrap on disposable hosted runners. It creates two real
non-login OS users. Root provisions/tears down only; product processes run under
actual distinct UIDs, no supplementary groups, isolated HOME/config/cache/temp,
private synthetic roots and no inherited provider credentials. The installed
wheel exercises APIs; signed native commands independently exercise the public
CLI. Local account provisioning is refused by the controller.

The qualified campaign covers both stores, both access directions, fresh-process
resume, same-owner locks in separate processes, fresh-history isolation, memory
on/off, forged owner save refusal, same-owner deletion and foreign list/load/
delete/memory/reference refusal. A re-owned synthetic copy preserves the original
embedded owner identity and challenges application guards separately from kernel
permissions. Foreign attempts must leave fixtures unchanged and disclose no
canary. No administrator tamper-resistance is implied.

The OpenAI SDK request boundary uses an in-process mock transport: selected user
and project memory appears only when enabled; unrelated synthetic user/session/
project/credential canaries stay absent. Empty and contaminated controls must be
rejected. This is serialized-request observation with **zero external provider
connections**, not whole-host packet capture, native subscription egress evidence
or a default-enabled updater claim. Only bounded, content-free receipts persist.

It also covers actual same-owner transfer/migration/export with
stale-selection refusals, foreign preview/apply refusal, memory change pause and
explicit refresh/off, real owner-generated SQLite artifact/cursor challenges,
raw filesystem access challenges and operation-local cache teardown. Deletion
removes the selected logical session; synthetic migrated/exported copies remain
until fixture teardown. No physical erasure or backup-retention claim follows.
Neither an absent search API nor an invalid option is counted as a qualified
refusal; separate replay/index/notification and private model-selection surfaces
remain to be reconciled without opening any evaluation stores.
Remaining privacy composition includes those surfaces, cache integrations,
owner-scoped reset, credential rotation and full live/default outbound behavior.
The named passing campaign does not close R16-02.

Native recorded egress observations use positive loopback and quiet controls.
Linux `strace` follows descendant socket/connect calls without payloads. Apple
pktap captures only IP packet metadata attributed to the exec-stable direct PID
or effective PID; this is not arbitrary child-tool or whole-machine observation.
The selected recorded case has no tools or memory and explicitly disabled update
checks. Missing live/native-client/tool traffic and the default updater profile
remain separate; provider-free SDK serialization does not cover them.

## Evidence and client admission

The [qualification record](R16_02_PRIVACY_QUALIFICATION.md) binds passing evidence
on all four native targets plus actual Windows-hosted WSL2: two real OS users,
both stores, 190 receipt groups, 20 native recorded observations with positive/
negative controls, complete account/fixture cleanup and zero provider calls.
It preserves exact controller/run/report hashes and the narrower capture limits.

[Run 42333874296](https://github.com/joshuamyers22/mos-eisley/actions/runs/42333874296),
controller `d10e39ae0cd21e4686983f8920a7f735370c3312`, passed the initial 30 receipts
on each actual Mac: arm64 104.420 seconds, Intel 428.604 seconds; two actual UIDs
610/611, both accounts and fixture trees removed. Linux x86_64/arm64 stopped
before its first product case with a launcher `PermissionError`; actual UIDs
1002/1003 were provisioned and removed. uv's interpreter was staged under the
runner's temporary directory. The correction stages managed Python under the
public synthetic harness root instead. WSL2 proved actual Windows Server 2025
build 26100/distribution version 2, then failed setup because system Python was
selected and an optional managed-interpreter directory did not exist at chmod.
That directory is now created; the unused third setup account was removed from
the controller. These failures are preserved, not counted as passes or provider
failures. Expanded Mac qualification and affected Linux/WSL2 observer diagnosis
and qualification subsequently pass as recorded above; earlier failures remain.

Metadata-only local observation: installed Codex is **0.166.0**, outside rc.16's
admitted versions through 0.163.0; Claude remains 2.1.283. No inference or auth
cache read accompanied this version observation. Later preparation finds the
retained admitted Codex 0.163.0 binary and passes installed sign-in readiness for
it and Claude with the application's canonical native environment. The default
0.166.0 pointer remains unchanged. The exact six-call local memory proposal and
fake-client rehearsal are recorded separately; fresh authorization remains
pending. This makes no 0.166.0 compatibility claim and does not relabel readiness
as a new live qualification or historical grant renewal.

## Fresh authorization and stopping rule

No new provider call is authorized by this document. After provider-free required
gates pass, prepare only missing case packets: host and actual OS user, installed
candidate/client/model, authentication route, memory/tool/workflow boundary,
synthetic data/destinations, maximum dispatches, output/time/spend limits, native
retry/billing exposure, cancellation rule and evidence destination. Obtain fresh
owner authorization for those exact cases. Missing native sign-in must be
completed by the account owner in the client-owned flow on that host; no credential
copying or fabricated sign-in evidence.

An unexplained required failure stops dependent live calls. Preserve the first
failure, correct the controller only when evidence identifies a harness defect,
and cut a new signed candidate if a product fix is needed. Account teardown,
fixture cleanup and accountable security review are required. Stable publication
and the other R16 readiness rows remain separate decisions.


Additional blocker: legacy `mos replay` accepts an owner-preserved readable foreign
recorded run in a provider-free two-real-UID Linux carrier diagnostic, while the
original private directory refuses access. This separate path is not covered by
snapshot/SQLite conversation owner guards. Default private permissions were not
breached; application owner admission is absent for this supplied-input path.
Resolve private replay versus explicit portable verification in accountable review
and qualify the resulting candidate before claiming the full privacy contract.
The combined local gate also remains failed (one wheel fixture setup error); fresh
focused module/expiry-control tests pass but do not erase it. See the
[qualification record](R16_02_PRIVACY_QUALIFICATION.md#combined-gate-and-separate-replay-finding).
