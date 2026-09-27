# G4 final suites after signed correction integration

The carry-forward final-suite route runs the protected creator inventory and
frozen reviewer package on the integrated Git commit. It replays the signed
correction integration, renewed same-roster policy, new implementation binding,
and passing carry-forward candidate before accepting a creator-signed approval.
It uses the existing final-suite approval and receipt schema with a distinct
`g4-q2-real-child-final-` suite ID, and a separate private one-use claim store.

The approval binds the renewed policy, historical authenticated provenance,
passing carry-forward candidate receipt, integrated revision, both packages,
new source binding, two distinct execution requests, immutable image, and a
window of at most 24 hours within the renewed policy. The historic creator
package must still match the signed child assignment and base/source Git blobs.
Every protected file must also match the integrated Git blob and clean checkout.
Both exact isolated jobs are built before claim consumption. After both runs,
the full carry-forward chain and jobs are replayed. The final reviewer test ID
digests must match the passing candidate run.

The claim is spent before either offline container execution. A crash or
infrastructure failure requires a new admitted candidate and separately signed
approval; the same candidate receipt cannot be reused. The receipt grants no
provider, Git write, independent review, or acceptance authority. See the
[original final-suite design](G4_FINAL_WHOLE_SUITES.md) for the shared worker
and receipt contracts.
