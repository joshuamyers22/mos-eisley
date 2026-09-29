# One bounded live deadline-composition retest

## Scope and authority

- Revision: `b3357aac6862afb1f1b793e1f901d5eb71783779`
- Reviewed baseline: `e87ffa7f7439ea42b0a9f7073d54d5e2c91d4a55`
- Financial proposal: `a2ec3e4fde74095b167305cc6f4210c778ed4d8e799c31fbc7b10157d0a5fd60`
- Manifest: `3d6e6120bccb4536e458b201475df408ef51cfaae76835aed12108c8a0181add`
- Profile: one standalone attempt, three `gpt-5.6-luna` low-effort critics
  with threshold two and one conditional judge; schema-2 requests; native strict
  JSON Schema; 97 content-bound citation units per critic; `store: false`; empty
  tools; zero retries
- Deadlines: one-use claim at most 60 seconds; count and generation each at most
  60 seconds; derived role exchange at most 120 seconds; absolute exchange cap
  300 seconds; controller cap 360 seconds; guardian cap 305 seconds
- Runtime: OpenAI SDK `3.11.0`; Linux/arm64 production image
  `sha256:2adb3c8c39040fc01fc25d3800963c21dc08708bd9e3395ac248695533e92b6e`
- Ceiling: 83,664 micro-USD, exactly approved before sealing and dispatch
- Operator: Joshua Myers under ADR-0005 single-operator mode
- Verification method: pinned production-template survey
  `8879be48f3b760e65f6bed32f8740314fe92910d`,
  `docs/AGENTIC_VERIFICATION_GUIDE.md`, and
  `templates/AGENTIC_VERIFICATION_LOOP.md`
- Non-authority: no retry, qualification, production launch, routing activation,
  or release of historical held or uncertain spending

This was a wholly fresh standalone retest of the exact deadline-composition change.
It used a new private guidance store, role contexts, source clone, ledger, spending
policy, process key, manifest, and exact phase approvals. No historical seal, ledger,
key, reservation, provider result, or failed campaign was reused or changed.

## Outcome

All three critic token-count and generation exchanges returned provider responses.
The claim/exchange and cleanup/authority critics each produced a valid empty critique.
The operation/observation critic returned one finding, but its 151-byte quote did not
occur in the declared content-bound source unit, so the finding was retained only as
`invalid_evidence`; it was not repaired or retried. The intended two-of-three quorum
therefore remained satisfied, and the separately authorized judge completed with no
additional reservation.

The judge returned `accept`, upheld no findings, and concluded that the supplied
change preserved the one-use claim, separated the bounded exchange lifetime,
retained independent count/generation limits, admitted valid combined observation
intervals, and preserved bounded cleanup and spending behavior. The exact retained
result is
`00904170640878b8c6f49f90ea98874f99111c269a705ac60226d1043f0898aa`.

Joshua Myers signed the exact post-result observation. The retained signed-observation
hash is
`ad0409266d9d54c7791614b5cedb185073391043924293bd1afe968e16b3dcd2`.
The complete standalone replay bundle is
`ebf31e12147ab080eb93119cb95f347c9a0f4791f038f8bb8b60800df9c8fd61`.
Fresh post-process verification decoded that bundle, authenticated the signed
observation, reconstructed the retained result and checked every runtime exchange
and lifecycle path with `local_artifacts_verified=true`.

This is positive live evidence for V-007 and for quorum-tolerated critic failure
through judge, signed observation, disk retention and replay. It is not evidence
that every critic response will be valid, that the single-provider roster is
independent, or that the review profile is qualified for production launch.

## Accounting, retention, and cleanup

The four role receipts settled locally at 6,577, 6,899, 6,963 and 3,593 micro-USD,
for 24,032 micro-USD total. Dedicated ledger
`f87e8078c9370f99b73494e37ef4bc38fab81deaacf2865f6dc7a68dd97333ee`
reports five terminal entries, zero unresolved entries, 59,632 micro-USD available,
and is not blocked. This is local policy accounting, not provider invoice
reconciliation. The approved but unspent allowance is not reusable authority.

All four lifecycle results end in `removed` after one cleanup attempt. A filtered
Docker inventory found no remaining container derived from the pinned image. Private
campaign files retain mode 0600 under mode-0700 directories, and a bounded scan of
non-database artifacts found no API-key-shaped text or credential-variable name.

## G2 disposition

The attempt supplies the broad G2 live-path evidence named in the roadmap: one
frozen brief traversed credentialed critics and judge with preserved quorum, bounded
spend, runtime/cancellation controls, signed observation, complete evidence and exact
cleanup. The technical live path no longer lacks a successful end-to-end example.

It does not satisfy the stricter production-qualification rubric by itself. That
rubric requires three precommitted fixed campaign slots and launch-conformance
reconstruction; this artifact is one standalone attempt and cannot be substituted
into `CampaignEvidenceSubmission`. The earlier failed sealed campaigns remain
immutable and terminal. Q-001 therefore remains open, and G2 stays in progress for
formal qualification and a separate launch-admission decision. Any new live campaign
requires new owner direction, reviewed scope, budget, ledgers, seal and phase
authorizations.
