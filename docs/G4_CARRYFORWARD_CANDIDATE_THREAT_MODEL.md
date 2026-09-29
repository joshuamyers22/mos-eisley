# G4 carry-forward candidate threat model

## Scope and ownership

- System: offline candidate run on the real child's integrated G4 revision.
- Owner and signer: Joshua Myers; controller code and isolated runner are trusted.
- In scope: exact lineage, one-use authority, current Git, offline test execution.
- Out of scope: final suites, provider use, acceptance and formal independent review.

## Assets and boundaries

The frozen reviewer package, creator and child signatures, historical receipts,
signed integration, exact source binding and candidate observation are integrity
assets. The creator's private key remains outside the controller. A renewed
same-roster policy is a signer roster and time window; it grants no candidate
execution until the separate exact approval is signed. The host, Git executable,
Docker daemon, local clock, pinned image and private same-UID claim store remain
trusted as in the original G4 candidate gate.

## Abuse cases and controls

| Abuse case | Control | Residual risk |
|---|---|---|
| Reuse expired task or policy | Separate signature domain and current renewed-policy window; full historical replay | Local clock is not a trusted timestamp |
| Substitute an integrated commit or source byte | Signed integration replay, new binding and current Git reconstruction before and after execution | Trusted Git, filesystem and same-UID host |
| Substitute tests or image | Exact request, frozen package and pinned image with count verification | Image-to-lock correspondence remains unproven |
| Replay an approval or race dispatches | Exclusive mode-0600 claim in one persistent mode-0700 store | Changing stores bypasses the local replay guard |
| Run after a failed claim | No automatic retry; another exact signature is required | Crash can spend authority without a receipt |
| Treat pass as final acceptance | Receipt has acceptance false; final suites and review stay separate | Single-operator self-review risk remains |

## Decision and evidence

Use the existing integration's renewed policy only while its window is current.
Stop on any lineage, byte, claim, image, count or worktree mismatch. Run focused
signature/replay checks and the repository quality gate before a production test.
Keep all run artifacts outside Git and request Joshua's signature only after
read-only preflight passes.
