# Production-Quality GitHub Repository Standard

This document defines the default build, packaging, container, automation, and
repository layout for projects stored locally and published to GitHub. Apply it
to new repositories from the beginning and use the acceptance checklist when
upgrading existing repositories.

## 1. Canonical local organization

Store every GitHub-backed repository under `~/Projects`, using the GitHub
repository name as the local directory name:

```text
~/Projects/
├── PRODUCTION_REPOSITORY_STANDARD.md
├── project-one/
│   └── .git/
├── project-two/
│   └── .git/
└── project-three/
    └── .git/
```

Rules:

- One Git repository per project directory.
- The local directory name matches the GitHub repository name.
- Do not keep active repositories in `Downloads`, `Documents`, or synchronized
  cloud-storage folders.
- Do not nest a Git repository inside another project unless it is an explicit
  submodule with documented ownership and update procedures.
- Keep generated data, caches, virtual environments, credentials, and local
  databases outside Git or covered by `.gitignore`.

## 2. Required repository structure

Use the following baseline, omitting only items that genuinely do not apply:

```text
project-name/
├── .git/
├── .github/
│   ├── dependabot.yml
│   └── workflows/
│       ├── ci.yml
│       └── release.yml          # if artifacts are published
├── .dockerignore
├── .env.example                 # applications using configuration
├── .gitignore
├── .python-version              # or equivalent runtime-version file
├── CHANGELOG.md                 # published packages/services
├── CONTRIBUTING.md
├── Dockerfile                   # required for deployable apps and CLIs
├── LICENSE                      # when distribution terms are established
├── Makefile
├── README.md
├── REPRODUCIBILITY.md
├── SECURITY.md
├── pyproject.toml               # language-equivalent manifest is acceptable
├── requirements.runtime.txt     # deployable Python projects
├── src/
│   └── package_name/
├── tests/
└── uv.lock                      # language-equivalent lockfile is acceptable
```

Equivalent lockfiles include `package-lock.json`, `pnpm-lock.yaml`, `Cargo.lock`,
`go.sum`, `Gemfile.lock`, and `renv.lock`. Commit exactly one authoritative
lockfile for each package manager used by the project.

## 3. Project metadata and dependency policy

The project manifest must define:

- Package or application name and version.
- Short description and README.
- Supported runtime range.
- Runtime dependencies.
- Separate development, test, documentation, and optional feature dependencies.
- Console entry points for supported CLIs.
- Build backend and package discovery rules.
- Repository, issue tracker, and changelog URLs for published packages.

Dependency rules:

- Commit a resolver-generated lockfile; never hand-edit it.
- Local and CI installs use frozen mode and fail if the lock is stale.
- Update dependencies deliberately in a dedicated change.
- Commit the manifest and regenerated lockfile together.
- Deployable projects export hash-pinned runtime-only dependencies from the
  authoritative lockfile.
- Never install directly from a moving Git branch in production. Pin Git
  dependencies to an immutable commit SHA.
- Remove unused and duplicate dependency files or clearly document which file is
  authoritative.

Python baseline:

```sh
uv lock
uv sync --frozen --all-extras
uv run pytest
uv build
```

Runtime export for an application:

```sh
uv export --frozen --no-dev --no-emit-project \
  --output-file requirements.runtime.txt
```

CI must regenerate that export and fail on a diff so it cannot drift from
`uv.lock`.

Quantitative Python baseline:

- Polars is the default dataframe/query engine. A pandas dependency or conversion
  requires a documented interoperability need and a narrow owned adapter.
- Statsmodels is the default statistical, econometric, time-series, and
  regression engine. Statistical work must specify sample construction,
  intercept, missing/non-finite handling, covariance or standard errors,
  diagnostics, leakage controls, and validation evidence.
- Consequential statistical work must complete
  `templates/STATISTICAL_ANALYSIS_PLAN.md` and link the approved specification
  from its result or model artifact.
- Commit and install the locked Polars, Statsmodels, NumPy, SciPy, and transitive
  versions. Re-run numeric regression tests and benchmarks during upgrades.

## 4. Configuration and secrets

Applications must follow twelve-factor configuration practices:

- Read configuration from environment variables or explicitly mounted files.
- Commit `.env.example` with safe placeholders and documentation for every key.
- Never commit `.env`, API keys, passwords, private keys, tokens, cookies, or
  production connection strings.
- Validate configuration at startup and report missing keys clearly.
- Use least-privilege service accounts and read-only database roles where
  practical.
- Keep development defaults local-only and visibly unsuitable for production.
- Rotate any credential immediately if it enters Git history.

Recommended `.gitignore` entries:

```gitignore
.env
.env.*
!.env.example
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
htmlcov/
build/
dist/
*.egg-info/
*.db
*.sqlite
.DS_Store
```

Adjust exclusions for intentionally versioned fixtures and example data.

## 5. Latency-sensitive C++ standard

A C++ repository with latency-sensitive paths should add this baseline:

```text
project-name/
├── CMakeLists.txt
├── CMakePresets.json
├── cmake/
├── include/project_name/
├── src/
├── tests/
├── benchmarks/
└── LATENCY_BUDGET.md
```

Required policy:

- Declare the supported C++ standard, compilers, standard libraries, target
  architectures, ABI policy, and platform extensions. Isolate non-standard
  facilities behind owned interfaces.
- Use a checked-in CMake preset or equivalent build contract. Pin toolchain and
  dependency versions; do not rely on a developer's ambient package state.
- Compile first-party code with strict warnings. Run static analysis and reject
  unjustified suppressions, undefined behavior, unsafe ownership, and lifetime
  errors.
- Use RAII and explicit ownership. Raw pointers and references are non-owning;
  dynamic ownership uses scoped handles. Custom lifetime machinery requires an
  ADR and focused tests.
- Provide separate developer, Address/UndefinedBehavior Sanitizer, Thread
  Sanitizer, release, and benchmark profiles where the platform supports them.
- Define each critical path in `LATENCY_BUDGET.md`: measurement boundary,
  percentile and jitter targets, throughput, clock, workload, hardware, stage
  budgets, queues, overload response, replay evidence, and regression policy.
- Keep critical-path work and storage bounded. Any allocation, blocking call,
  lock, syscall, page fault, logging, batch, or retry in the path must be known
  and measured.
- Start with standard facilities. Custom allocators, containers, SIMD, affinity,
  NUMA placement, huge pages, and lock-free algorithms need before/after
  distributions, correctness tests, exhaustion behavior, and a simpler fallback.
- Benchmark release-equivalent artifacts on controlled, production-like hardware.
  Shared CI may execute benchmarks and retain results but must not enforce noisy
  microbenchmark thresholds.
- For market-data or execution systems, preserve typed numeric units, sequence
  and gap handling, stale-state behavior, pre-trade controls, audit identity, and
  deterministic replay. Performance changes may not bypass these controls.
- Binary protocol boundaries must validate size, version, type, declared length,
  flags, byte order, and enumerated values before domain processing. They require
  malformed/truncated conformance tests, bounded replay, corpus provenance and
  digests, and fuzz evidence before handling untrusted production traffic.

Apply `docs/LATENCY_SENSITIVE_CPP_GUIDE.md` for design and review detail. The
`cpp-low-latency` archetype is the executable minimum; it must be specialized to
the real protocol, hardware, clocks, replay corpus, and risk boundary.

## 6. Docker standard

Docker is required for deployable services, scheduled jobs, and operational
CLIs. It is optional for pure libraries when a locked runtime and CI matrix
already provide reproducibility.

Every production image must:

- Use a specific runtime version and pin the base image by digest.
- Use a multi-stage build.
- Install only locked, hash-verified runtime dependencies.
- Exclude compilers, tests, caches, credentials, and development tools from the
  final image.
- Run as a dedicated non-root user with a fixed UID/GID where practical.
- Set deterministic runtime environment variables.
- Define an entry point or command.
- Declare persistent volumes and exposed ports when applicable.
- Include a health check for long-running network services.
- Build and pass a smoke test in CI.
- Use `.dockerignore` to keep the build context small and safe.

Python application template:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12.11-slim-bookworm@sha256:REPLACE_WITH_VERIFIED_DIGEST AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
COPY pyproject.toml README.md requirements.runtime.txt ./
COPY src ./src

RUN python -m pip wheel --require-hashes --wheel-dir /wheels \
      --requirement requirements.runtime.txt \
    && python -m pip wheel --no-deps --wheel-dir /wheels .

FROM python:3.12.11-slim-bookworm@sha256:REPLACE_WITH_VERIFIED_DIGEST AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --create-home app

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

USER 10001:10001
ENTRYPOINT ["project-command"]
CMD ["--help"]
```

Never copy `.env` into an image. Supply secrets at runtime through the deployment
platform's secret manager.

## 7. Standard developer commands

Every repository should expose a small, predictable command surface. A Makefile
is the default portable interface:

```makefile
.PHONY: sync lint type test build container check

sync:
	uv sync --frozen --all-extras

lint:
	uv run ruff check .
	uv run ruff format --check .

type:
	uv run mypy src

test:
	uv run pytest --cov --cov-report=term-missing

build:
	uv build

container:
	docker build --tag project-name:local .
	docker run --rm project-name:local --help

check: lint type test build
```

Only include gates configured and passing in the repository. Do not add a fake
type, format, or coverage gate that is immediately ignored. Tighten standards
incrementally and keep `make check` green.

## 8. Testing requirements

At minimum, a production-quality project must have:

- Unit tests for core behavior and error paths.
- Regression tests for every corrected defect.
- Deterministic tests with explicit seeds and controlled clocks.
- No live network dependency in the default unit suite.
- Integration tests for database, queue, storage, or third-party boundaries.
- Smoke tests for built packages and containers.
- A documented approach to fixtures and test data.
- Coverage reporting with a realistic enforced floor for maintained code.

Tests involving external services must be clearly marked and isolated. CI should
provide disposable service containers rather than depending on shared production
infrastructure.

## 9. Continuous integration

CI runs on pushes to the default branch and on pull requests. It must use
read-only permissions unless a job explicitly requires more.

Required gates:

1. Check out the repository.
2. Install the declared runtime.
3. Install dependencies from the frozen lockfile.
4. Verify generated runtime dependency exports are current.
5. Run lint and formatting checks.
6. Run static type checks when configured.
7. Run unit tests and enforce the coverage policy.
8. Build distributions or application artifacts.
9. Build and smoke-test the production image when Docker applies.
10. Upload artifacts only after all verification succeeds.

Example Python job:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@PINNED_COMMIT_SHA
      - uses: astral-sh/setup-uv@PINNED_COMMIT_SHA
        with:
          enable-cache: true
      - run: uv sync --frozen --all-extras
      - run: make check

  container:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@PINNED_COMMIT_SHA
      - run: docker build --tag project:${{ github.sha }} .
      - run: docker run --rm project:${{ github.sha }} --help
```

Pin third-party actions to full commit SHAs. Dependabot or Renovate should submit
reviewable updates for actions, dependencies, and container bases.

## 10. Release and deployment

Releases must be repeatable from a clean checkout:

- Use semantic versioning unless the domain requires another documented scheme.
- Maintain a changelog for user-visible changes.
- Tag the exact reviewed commit.
- Verify the tag matches package metadata.
- Build artifacts in CI rather than uploading local build output.
- Publish using short-lived identity federation or trusted publishing, not
  long-lived repository secrets.
- Generate provenance, checksums, and an SBOM for externally distributed or
  high-risk artifacts.
- Deploy immutable image digests, never mutable tags such as `latest`.
- Document rollback and migration procedures before production deployment.
- Keep database migrations append-only and test them from an empty database.

## 11. Documentation and governance

`README.md` must explain:

- What the project does and its current maturity.
- Supported environments.
- Frozen installation instructions.
- The shortest working example.
- Configuration and required external services.
- Test and quality commands.
- Container build/run commands when applicable.
- Known limitations and operational assumptions.

`REPRODUCIBILITY.md` must explain:

- Runtime and dependency pinning.
- How to reproduce tests, research results, builds, and images.
- How locks and generated dependency exports are updated.
- Required datasets, snapshots, seeds, timestamps, and configuration.
- Any platform-specific limitations.

Use `SECURITY.md` for supported versions and private vulnerability reporting.
Use `CONTRIBUTING.md` for environment setup, branches, checks, and pull-request
expectations. Do not select or change a software license without owner approval.

## 12. Observability and operational safety

Deployable applications should also provide:

- Structured logs written to standard output/error.
- Stable health and readiness checks.
- Explicit timeouts for network and database operations.
- Bounded retries with backoff for transient failures.
- Graceful shutdown and idempotent startup behavior.
- Metrics for latency, failures, throughput, and resource saturation.
- Correlation or request identifiers where multiple systems interact.
- Documented backup, restore, retention, and disaster-recovery procedures.
- No sensitive values in logs, exceptions, metrics, or generated artifacts.

## 13. Acceptance checklist

A repository is production-quality and reproducible when every applicable item
below is checked.

### Repository

- [ ] Stored at `~/Projects/<github-repository-name>`.
- [ ] GitHub `origin` is correct and the default branch is documented.
- [ ] Worktree contains no generated or secret files.
- [ ] README, contribution, security, and reproducibility guidance are current.
- [ ] Distribution license has been explicitly selected by the owner.

### Runtime and dependencies

- [ ] Runtime version is declared.
- [ ] Project metadata uses the language's current standard.
- [ ] Resolver-generated lockfile is committed.
- [ ] Frozen installation succeeds from a clean environment.
- [ ] Git dependencies use immutable commit SHAs.
- [ ] Runtime-only dependency export is hash-pinned and synchronized when needed.

### Quality

- [ ] Lint passes.
- [ ] Formatting policy passes or is intentionally not enforced.
- [ ] Static type checks pass when configured.
- [ ] Unit and integration tests pass.
- [ ] Coverage floor passes.
- [ ] Package or application artifact builds from a clean checkout.
- [ ] `make check` represents the complete local quality gate.

### Containers

- [ ] Docker is included for deployable applications and intentionally omitted
      for libraries where it adds no reproducibility value.
- [ ] Base image version and digest are pinned.
- [ ] Multi-stage build installs locked runtime dependencies only.
- [ ] Final image runs as non-root.
- [ ] Secrets and development files are excluded.
- [ ] Health check or CLI smoke command passes.
- [ ] CI builds and tests the image.

### Latency-sensitive systems

- [ ] A completed latency budget defines end-to-end and stage objectives.
- [ ] Production-like evidence includes percentile tails, jitter, saturation,
      warm-up, and overload behavior.
- [ ] Queues, batches, memory, retries, and in-flight work are bounded.
- [ ] Clock, timestamp, sequencing, stale-state, and replay semantics are tested.
- [ ] Sanitizer/race profiles and an optimized benchmark profile are reproducible.
- [ ] Each non-standard hot-path optimization has measured benefit, correctness
      evidence, an owner, and a fallback or rollback condition.

### Automation and operations

- [ ] CI runs on pull requests and default-branch pushes.
- [ ] CI permissions follow least privilege.
- [ ] Third-party actions are pinned and automatically updated.
- [ ] Dependency updates are automated but require review and green checks.
- [ ] Release artifacts are built and published by CI.
- [ ] Deployment uses immutable artifacts and has a rollback procedure.
- [ ] Logs, health checks, timeouts, retries, and monitoring are documented.

## 14. Definition of done

An upgrade is complete only when:

1. A clean clone can install dependencies in frozen mode.
2. The documented local quality command passes.
3. CI performs the same essential checks.
4. All declared artifacts build successfully.
5. Applicable container images build, run as non-root, and pass a smoke or
   health check.
6. No credentials or machine-specific absolute paths are committed.
7. The worktree contains only intentional source changes.
8. The final commit is attributable to the correct Git identity and is reviewed
   before it is pushed or released.
