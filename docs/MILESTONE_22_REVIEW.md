# Milestone 22 adversarial review: prompt-only skills

## Disposition implemented

This milestone adopts only the low-authority portion of the reviewed skills,
SecretRef, and doctor proposal: standards-compatible prompt skills with optional
validated Mos Eisley metadata, immutable package snapshots, source-qualified digest
identity, explicit project activation, and exact recorded-run provenance.

It rejects or defers every executable or credential-bearing extension. Structural
validation never grants trust. Project packages do not shadow user packages.

## Adversarial findings addressed

- A name or version is mutable, so activation requires source, name, and complete
  package digest.
- Project-local content can be attacker-controlled, so it needs an invocation-local
  opt-in even when its digest is explicitly named.
- Progressive loading can create validation/use races, so activation and resources
  read an in-memory snapshot produced during discovery.
- YAML can hide resource-amplification and ambiguity, so aliases, anchors, explicit
  tags, and duplicate keys are rejected within byte limits.
- A prompt-package format can become a code loader accidentally, so scripts,
  executable bits, tool bundles, and `allowed-tools` fail closed.
- Provenance can drift away from actual requests, so recorded integration accepts a
  skill only when its body exactly matches the cassette-bound persona. Schema-2 run
  artifacts preserve and reverify both identities.

## Remaining limits

The complete package is held in memory to make later disclosure immutable; only
model-context loading is progressive. Package archives and signatures are absent,
so exact future reconstruction still depends on retaining the identified package.
Filesystem checks do not contain a malicious same-UID process or a compromised
ancestor directory. Skill quality is unevaluated, and skills grant no runtime,
model-selection, tool, credential, network, or configuration authority.

SecretRef, doctor, script execution, persistent trust, automatic discovery, and
persona promotion remain deferred behind their own threat models and tests.
