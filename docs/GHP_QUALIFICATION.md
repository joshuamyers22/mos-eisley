# GHP qualification record

Date: 2026-09-23. Outcome: **no-go at G1**.

This is a compact qualification record for the candidate reviewed in
[ADR 0005](adr/0005-ghp-github-publication-boundary.md). It contains no credential,
request body, repository content or unrestricted tool log.

## Identity and build inputs

| Item | Qualified value |
|---|---|
| Upstream | `https://github.com/goodtune/ghp` |
| Commit | `338498fc3e60e7c04f428371e20fb6d5ce82c451` |
| Commit time/subject | `2026-09-20T19:12:55+10:00`; `fix(deps): update module github.com/goodtune/dotvault to v0.35.0 (#254)` |
| Source-tree digest | `650efdf71f533d1bd528cddda6e2221b2f0534619b0a3e6263ef8ab741ae9164` |
| License | MIT; `LICENSE` SHA-256 `ca375ed4fdb93c9fdb44a49caeed3cccdb6473d5296c66ddc9105371a13b0d19` |
| Go manifest | `go.mod` SHA-256 `36362549d555b6c35b6b80e65e35d3949f812f2ed5506ce7894edf9a2be10263` |
| Go checksums | `go.sum` SHA-256 `807f0ea014d58d0414a54ecf0f295b683babef20cfbfa47d13da828e9ca96c6c` |
| Declared modules | 32 direct and 126 indirect requirements; no `replace` directives |
| Test/build image | `golang:1.26.0@sha256:fb612b7831d53a89cbc0aaa7855b69ad7b0caf603715860cf538df854d047b84` |
| Runtime base | `gcr.io/distroless/static-debian12@sha256:afa5c872c891853ca7fcf1f12c3edb23f7eeef36189728842dd51042ff57f7ab` |
| Reproducible binary | SHA-256 `0d0ed566792867832cf68f91d3569de8babbcb49ecf98d4a138b4fa3802097ab`; 32,571,554 bytes; Linux arm64 static executable |
| Local qualification image | manifest `sha256:1acaf84191b21a9cfd5ae18e00a7feba5ab58e2a121b0e1e6adb4e3775b476cc` |

The commit contains an embedded GitHub PGP signature, but the qualification host
did not have `gpg`; its signature was not independently verified. The source commit
and all hashes above were independently read from the checkout.

## Checks executed

| Check | Result |
|---|---|
| `go test ./...` in the exact Go image | Unit packages passed. PostgreSQL/Vault packages initially failed because the container had no nested Docker provider. |
| PostgreSQL and Vault integration tests with an explicit Docker socket | Passed. |
| `go test -race ./...` with PostgreSQL and Vault testcontainers | Passed for every package; no race reported. |
| Two clean `CGO_ENABLED=0`, `-trimpath`, `-buildvcs=false` builds | Byte-identical at the binary hash above. |
| Distroless installed-artifact smoke test | Passed: `ghp version 338498fc3e60`. |
| `govulncheck` v1.8.0 against `./...` | Failed: 27 reachable findings. |
| Docker Scout image scan | Not completed: the installed scanner required a Docker account login. No clean image-scan claim is made. |
| SBOM/license inventory | Module and license inventory recorded above; no qualified CycloneDX/SPDX SBOM was produced. |
| Browser E2E | Not run after the blocking G1 findings; Node/Playwright were absent on the host. |
| Fuzz suite | No Go fuzz targets were present in the reviewed source. |

The race and integration results show that the candidate is testable; they do not
override policy findings or the vulnerability gate.

## Blocking findings

### B1 — Empty agent-token restrictions create an open-scoped token

`internal/token/token.go:88-89` documents both repositories and scopes as optional.
`Create` accepts empty values and serializes them as JSON `null` at lines 144-206.
`internal/server/api.go:216-225` likewise treats an empty scope as open-scoped and
passes an empty repository list for agent tokens at lines 283-310. There is no
configuration field that makes either dimension mandatory.

Impact: an omitted field or a broad administration session can create a token with
the full repository and permission authority of the backing App installation. This
directly violates security invariant 2.

### B2 — Stock policy cannot express the publisher's route allowlist

`internal/proxy/proxy.go:306-325` forwards unrecognized REST endpoints and relies
on the backing GitHub credential. The permission rules are category-wide. For
example, `pull_requests:write` covers creating/patching PRs, merge, requested
reviewers, reviews and comments; it cannot mean only `POST .../reviews`.

The reviewed rule set also omits `PATCH .../check-runs/{id}`, causing that required
publisher operation to follow the unrecognized-endpoint path. The server always
registers `/api/graphql` (`internal/server/server.go:417-419`) and has no deny
setting. Codeload with no redirect is transparent passthrough rather than disabled.

Impact: deployment configuration cannot prove default-deny behavior for exact
publisher methods/routes, GraphQL or codeload. This violates invariants 5 and 6 and
the G3 gate.

### B3 — Audit delivery cannot fail closed

`proxy.AuditLogWriter.WriteAuditEntry` has no return value. The server writer calls
OpenTelemetry `Emit` without receiving a delivery result
(`internal/server/auditlog.go:31-56`). Proxy audit is invoked after the upstream
request and its status are already known (`internal/proxy/proxy.go:1038-1070`).

Impact: exporter backpressure, outage or dropped telemetry cannot prevent or roll
back a GitHub write. The record is useful telemetry, not an authoritative
transaction journal. This violates security invariant 8.

### B4 — The exact baseline has reachable known vulnerabilities

Official `govulncheck` v1.8.0 reported 27 reachable vulnerabilities:

- `GO-2026-6354` and `GO-2026-6355` in `golang.org/x/crypto@v0.55.0`, fixed in
  v0.56.0; and
- 25 standard-library findings in Go 1.26.0, with fixes spanning Go 1.26.1 through
  1.26.6.

The traces include TLS, X.509, HTTP, URL parsing, template escaping and SSH paths.
The exact source lock still selects the vulnerable `x/crypto` version. Rebuilding
unchanged source with a newer compiler would not resolve that module finding and
would no longer match the exact toolchain recorded by this qualification.

Impact: G1's no-unresolved-high-impact exit gate is not met.

## Additional gaps

- The publisher would need a broad `ghpr_` administrator session to create agent
  tokens; stock GHP has no repository/route-constrained machine issuer identity.
- Revocation can remain effective in another instance's in-memory cache for up to
  30 seconds (`tokenCacheTTL`), so “immediate” multi-instance revocation is not
  demonstrated.
- The upstream Dockerfile uses mutable `python:3.14`, `golang:1.27` and distroless
  tags, installs unpinned `uv`, and builds docs via `uvx`. The release workflows use
  mutable Action tags and `goreleaser` version `latest`. Those inputs do not meet
  Mos Eisley's immutable supply-chain policy.
- REST request/response body caps and an explicit route-level rate/concurrency
  profile are not configurable for the proxy path required by this project.

## Gate result and cleanup state

G0's alternatives analysis selects the simpler direct short-lived GitHub App
publisher as the next design candidate. G1 is closed as a no-go because four
blockers and additional supply-chain gaps remain. Per the project plan, G2-G6 were
not started.

No credential, GitHub App, DNS record, TLS certificate, remote issue, deployment,
publisher implementation or repository publication was created during
qualification. Temporary qualification containers exited; the local source clone,
binary and image are non-production evidence only and convey no authority.
