# WSL2 preflight threat model

- Scope: read-only preparation command and operator qualification runbook, §27.1.
- Owner: Josh Myers; dated 2026-10-03; revisit for runtime admission integration.
- Assets: private storage/credential contents, correct platform provenance,
  existing workspace state and runtime authority.
- Inputs: explicit directory paths and local kernel, distro and mount metadata.
  No subprocesses, network, Windows interop, environment enumeration or file-content
  inspection in the diagnostic.

| Abuse/failure | Control and evidence | Residual limit |
|---|---|---|
| WSL environment variables on ordinary Linux | Ignore environment markers; classify kernel/system metadata; negative tests | Kernel strings can be customized or forged; host-side evidence is still required |
| DrvFS via aliases or nested mounts | Resolve paths, use component-aware longest mount, reject all non-ext4 candidates and read-only mounts; fixture tests | Mount changes and pathname races remain possible; diagnostic is not runtime enforcement |
| Public or foreign private directories | Require owner UID and mode without group/other bits; real temporary-directory tests | Ancestor ACLs, full content safety and same-user interference require runtime suites |
| Malformed or oversized proc metadata | Fixed read bounds, strict mount parser, unknown/unavailable rejects | Local compromised OS is outside this diagnostic's trust boundary |
| Credentials in evidence | Read directory stat only; select distro fields; no environment/content dumps; canary test | Explicit paths are private metadata; retain reports privately |
| Preflight treated as sandbox or release approval | JSON always denies qualification and execution authority; runbook requires real installed artifact and containment checks | Accountable owner must review host and artifact correspondence |
| Verification executes paid workflows | Existing synthetic package tests; container checks run offline; no live-provider commands | Operators must keep real credentials out of qualification fixtures |

Preparation cannot certify secure storage, Linux containment, keyring availability,
physical Windows-host provenance or release readiness. All remain separate gates.
