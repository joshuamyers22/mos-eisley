# Threat model: G3 public-case execution view

## Scope and ownership

- System/version: four [bounded SWE-rebench V2 candidate views](G3_SWE_REBENCH_EXECUTION_VIEW_AUDIT.md), built from pinned base commits on 2026-09-28.
- Owner and accountable reviewer: Joshua Myers. This agent prepared the audit; Joshua has not accepted a source, label, or cohort.
- Trigger: the first task-visible repository and executable-oracle boundary for the G3 single-human study direction in [ADR-0010](adr/0010-g3-single-human-oracle-study.md).
- In scope: public archive and GitHub tree ingestion, issue packet projection, filtered base workspace, pinned image, offline test controls, and parser. Out of scope: model/provider execution, production data and outcomes, sampling/custodian/label stores, statistical grouping, arm assignment, and launch approval.

## Assets, actors and boundaries

| Asset | Integrity or confidentiality need | Owner |
|---|---|---|
| Pinned public base tree and issue packet | Exact task provenance; exclude future repair and evaluator material from task view | Source owner and Joshua |
| Operator gold/test diffs, expected IDs and raw logs | Must never enter the model view or a sampling artifact | Joshua |
| Host credentials, filesystem and network | Must not be reachable from public-case code or a future model tool | Workspace owner |
| Oracle result and parser | Fail closed on missing, ambiguous or altered evidence | Joshua |
| Study labels, assignments and outcomes | No access or authority from this public source audit | Study custodian/owner |

The public dataset, upstream repositories and registry images are third-party
inputs. Their statements and code are untrusted. The model, if later dispatched,
can edit its task workspace and invoke permitted tools but must have no host
Docker socket, network, operator diffs/logs, future Git history, or private
study material. The workspace builder and oracle runner are operator-side
components with separate temporary paths.

## Abuse cases, controls and residual risk

| Abuse case | Impact | Control and observed evidence | Residual risk |
|---|---|---|---|
| Substituted archive or forged recursive Git tree | Wrong base or hidden answer enters task view | Exact dataset hash, commit and root-tree IDs; recomputed Git directory and blob hashes; archive file set and mode verification. A mutated tree SHA was rejected. | GitHub and the dataset host are trusted for publication identity; hashes are not publisher signatures. |
| Path traversal, symlink, submodule or extra file | Read/write outside view or hidden payload | Verifier rejects links, submodules, Git metadata, unsafe paths, extra files and symlinked output paths. The four authentic views passed. | A new archive mode or tool version needs a new audit. |
| Repair, generated tests or oracle leaks through source tree | Contaminated model result | Two-key issue packets; no operator artifact mount; exact added-line and future-PR-URL screens; authenticated base blobs. Policy-bot had zero 20–300-character added-line overlaps. | Semantic hints, historical public issue edits and model pretraining exposure cannot be ruled out by literal scans. |
| Image embeds future Git refs or answer artifacts | Model can bypass packet boundary | Original project directory is overmounted with verified workspace. Mounted paths lack `.git`; policy-bot mounted image had no found `.git`, `gold.diff`, `test.diff` or `expected.json` path. Pin registry digest and deny Docker socket. | Image filesystem/path search is a bounded observation, not exhaustive proof against answer content or a hostile image. A clean, purpose-built runtime would reduce this risk. |
| Public code or issue text issues commands or exfiltrates data | Host/network compromise | Issue text is task data, not harness authority; controls ran with no network, read-only root, 2 CPUs, 2 GiB, 256 PIDs, dropped capabilities and no-new-privileges. No host credential mount. | Future model dispatcher must enforce the same boundary and review any new tool. |
| Vendored or credential-like source material enters view | Rights breach or secret exposure | Policy-bot vendor tree and PEM-bearing example config, and revive encrypted deploy key, are excluded by exact view rules. Filtered views passed limited PEM/token/key-pattern checks. | Pattern scans cannot prove no secrets; repository and asset rights need Joshua's review. |
| Live service or toolchain drift changes oracle meaning | False pass/fail or irreproducibility | Whole-suite base/gold/wrong controls, pinned image digest and observed Go version. Osv-scanner and revive failed under the exact isolated setup and are not qualified. | Another runtime or revised oracle is a new protocol version and needs fresh controls. |
| Duplicate, missing, malformed or selectively reported test events | False positive oracle result | Independent JSON parser checks all terminal occurrences of expected names, package/test duplicates, other failures and exit code. Missing pass, conflicting duplicate and malformed-line mutations were rejected for policy-bot. | Parser cannot prove tests fully capture the issue; human review remains necessary. |
| Replay of public controls as eligible study evidence | Invalid statistical or production claim | Frame and audit explicitly grant no enrollment, probability, group, label, split, holdout or production-outcome authority; raw logs stay outside Git and sampling artifacts. | Source/method approval and the single-human verifier amendment remain open. |

## Decisions and recovery

Only policy-bot passes this **bounded preproduction execution-view** audit;
carapace, osv-scanner and revive fail their declared oracle controls. No risk
acceptance or study-source approval is implied. Joshua must review the source
rights, image/runtime exposure, oracle meaning and statistical method before
any admission. A changed image, mount, task packet, source commit, patch,
parser, or test command invalidates this exact qualification and requires a
new version and controls. If a later run exposes an operator artifact, host
secret, future history or network path, stop dispatch, quarantine the run,
preserve safe hashes for investigation, and do not count it as evaluation
evidence.
