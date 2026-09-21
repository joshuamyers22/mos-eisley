# Frozen role guidance

`mos guidance-context freeze|show` creates and inspects a local, immutable guidance
packet for a creator, coder, critic or judge. The packet contains explicitly selected
current rules, applicability, rationale, checks, approved override reasons and exact
source/snapshot hashes. It does not load a provider context or start a run.

## Select relevant guidance

Use the [role selection example](../templates/PROJECT_GUIDANCE_ROLE_EXAMPLE.json).
Choose a role and scope, explain the selection, and list the qualified references
that role needs. Every accepted requirement left out needs its own explicit scope
reason in `omitted_requirements`. Unknown references, omitted/conflict-excluded rules,
duplicate references and unexplained requirement omissions reject.

For creator and coding roles working on the same scope, reuse the same accepted
requirement references. Critic/judge packets contain the selected frozen requirements
and rubric without copying creator transcripts, private notes or surrounding source
documents. Relevance is explicitly reviewed; this command does not infer it from prose.

The current [combined assessment](PROJECT_GUIDANCE_PRECEDENCE.md) must be complete,
and the explicitly selected [owner policy](PROJECT_GUIDANCE_POLICY.md) must allow the
combined selection. Picking a smaller role subset cannot bypass a policy prohibition
or an unresolved conflict in the combined project view.

```sh
mos guidance-context freeze -C /path/to/project \
  --input /path/to/role-selection.json \
  --policy /path/to/private/policy.json \
  --expected-policy-sha256 REVIEWED_POLICY_HASH --json
```

This is a preview. Review the complete proposed packet and retained provenance,
then repeat with `--apply --expected-sha256 REVIEW_HASH`. Apply rechecks selection
bytes, policy identity/hash, current guidance file identities and the assessment
under the private guidance lock. Changed inputs require a fresh preview. No input
path is inferred from a template, role selection or source link.

## Context versus retained evidence

The receipt's `snapshot.context` is the bounded role packet. It contains only selected
effective rule text and metadata, explicit requirement-omission reasons, role/scope
and pinned policy/assessment hashes. For an overridden advisory rule it contains the
replacement and departure reason; the old default text is not copied into the packet.
Unselected source text and private policy prose remain outside that context.

The enclosing snapshot preserves selection JSON and policy JSON for local review and
reconstruction. It is evidence, not a provider payload. `context_materialized: true`
means a local role packet was constructed; `provider_context_loaded`, `history_loaded`
and `execution_authorized` remain false. No tool, budget, containment or permission
grant can be expressed by these schemas.

## Inspect a frozen packet

```sh
mos guidance-context show -C /path/to/project \
  --snapshot-sha256 SNAPSHOT_HASH --json
```

Inspection reconstructs the role projection from its retained selection/policy and
immutable combined-assessment basis, then checks exact equality. A new content hash
cannot make a forged rule projection valid. Missing/corrupt basis snapshots reject.
Original selection, policy and brief files need not still exist; inspection never
reopens paths retained in an artifact.

Project updates do not rewrite frozen packets. Historical output always has
`current_authority: false`; it does not establish that old guidance or policy is still
current. [Current admission checks](PROJECT_GUIDANCE_ROLE_ADMISSION.md) now provide
an exact current check and guarded local loader. Actual run integration must still
pin the packet to run provenance and preserve independent runtime authorization. These
packets are not automatically attached to terminal sessions or provider requests.

## Storage, limits and recovery

Packets use immutable `role-snapshot-SHA.json` files in the current user's private
guidance root. Reads/apply require the exact owner and project directory identity.
Existing private-file, single-link regular-file, symlink, lock and atomic-publication
protections apply. Trusted ancestors and the same OS user remain the filesystem
boundary. Previews change no stored files.

Selection JSON is bounded to 32 KiB raw/canonical bytes, with 1–64 included references
and up to 64 requirement omissions. The canonical role packet is bounded to 64 KiB;
the complete saved snapshot is bounded to 512 KiB. No silent truncation occurs.
Duplicate keys, unsupported roles, arbitrary authority/history fields and invalid
source identities reject. Text remains declarative; embedded instructions or links
do not cause file reads, execution or history loading.

A repeated reviewed freeze can reuse the same valid immutable packet. A failure after
publication may leave the packet saved; inspect its reported snapshot hash before
retrying. There is no mutable active-role pointer and no implicit refresh. Immutable
history retention/cleanup, project relocation and run/provider admission remain later
work. Reverting this additive slice leaves existing guidance, memory and sessions intact.
