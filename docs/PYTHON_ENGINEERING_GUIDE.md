# Python Engineering Guide

This is the template's operational baseline for production Python. It is an
original synthesis, not a substitute for the books in `source_material/converted`.
Use those page-addressable extracts to investigate a topic, then verify behavior
against the supported Python version and primary library documentation.

## Design defaults

- Model domain concepts with small immutable values where practical. Reject
  invalid states at construction or at the system boundary.
- Keep policy pure and push files, clocks, randomness, databases, processes, and
  networks behind narrow injected collaborators.
- Prefer functions and composition. Introduce classes for identity, lifecycle,
  stateful invariants, or genuine polymorphism—not merely to group functions.
- Accept protocols and return concrete values. Do not mirror every implementation
  with an interface.
- Keep import-time work inert: no network calls, configuration discovery, thread
  creation, or database connection before the composition root runs.
- Use exceptions for failures, not routine branches. Catch only where recovery,
  translation, cleanup, or added context is possible.

## Data model and Python semantics

- Choose containers by operation: list for ordered iteration, tuple for fixed
  records, set for membership, dict for keyed lookup, deque for both-ended queues,
  heapq for priority access.
- Understand aliasing before copying. A shallow copy duplicates the outer
  container, not nested mutable objects.
- Never use a mutable default argument. Use `None` or a `default_factory`.
- Implement the smallest useful data-model surface (`__repr__`, equality,
  ordering, hashing, iteration, context management). Preserve the contracts:
  equal hashable objects must share a hash, and hashes require effective
  immutability.
- Prefer iterators/generators for pipelines that need bounded memory. Document
  whether an iterable is single-pass and whether evaluation can fail late.
- Treat descriptors, metaclasses, decorators, and dynamic attribute hooks as
  framework tools. Prefer an explicit function or class until the abstraction
  removes repeated policy and remains debuggable.

## Types and APIs

- Type all public boundaries and important internal policy. Run the configured
  checker in strict-enough mode that annotations are evidence, not decoration.
- Use `Protocol` for structural contracts, `TypedDict` for shaped mappings at
  boundaries, and dataclasses for owned records. Avoid `Any` except at a dynamic
  boundary; narrow it immediately.
- Return one stable shape. Use explicit result types when partial success is part
  of the domain; raise specific exceptions for exceptional failure.
- Avoid boolean parameters that obscure intent. Prefer named operations, enums,
  or a cohesive options object.
- Version serialized and public API contracts. Do not expose ORM, transport, or
  third-party objects as domain contracts.

## Algorithms and resource use

- State expected input size and dominant operation before optimizing. Complexity
  mistakes usually dominate interpreter-level micro-optimizations.
- Measure wall time and allocations with representative data. Warm caches,
  separate setup from measurement, repeat runs, and retain the benchmark.
- Reduce algorithmic work and data movement first; then choose built-ins,
  vectorized/native libraries, processes, or compiled extensions based on the
  measured bottleneck.
- Threads suit blocking I/O; processes or native code suit CPU-bound work.
  Confirm the concurrency behavior of the actual interpreter and extension
  libraries. Set deadlines, cancellation behavior, and bounded queues.
- Stream large inputs, cap caches, close resources with context managers, and
  make ownership of temporary files and external handles explicit.

## Quantitative dataframe and statistical defaults

The companion `QUANT_STATISTICAL_LEARNING_POINT_OF_VIEW.md` is deliberately
opinionated but non-deterministic. Use its preferences to expose assumptions and
review questions. A documented, evidence-backed departure is a valid outcome.

- Use Polars for tabular ingestion, joins, filtering, aggregation, windowing, and
  feature pipelines. Prefer expressions and lazy execution when they reduce
  materialization; inspect the optimized plan and benchmark representative data.
- Disable or override schema inference at trust boundaries when inference could
  alter identifiers, timestamps, decimals, categorical values, or null semantics.
  Validate schema and units before analysis.
- Treat pandas as interoperability, not the project data model. Isolate any
  required conversion behind an adapter, document dtype/index/null and memory
  consequences, and return to Polars or domain values immediately.
- Use Statsmodels for statistical inference, econometrics, regression, and time
  series. Keep the Polars-to-model boundary narrow and explicit; a NumPy design
  matrix is appropriate when it makes ordering and intercept handling visible.
- Fail on missing or non-finite modeling values unless the approved method
  specifies imputation or deletion. State the estimand, sample construction,
  intercept, weights, covariance/standard-error estimator, clustering, lags,
  diagnostics, multiple-testing policy, and out-of-sample validation.
- Do not treat a fitted coefficient, in-sample metric, or default p-value as
  production evidence. Test leakage, stability, residual assumptions, sensitivity,
  and economic significance, and retain code/data/environment identity.
- Emit a versioned machine-readable evidence artifact that binds results and
  uncertainty to the ordered design matrix, sample declaration, input and plan
  hashes, code revision, evaluation time, and locked library versions. Make
  serialization deterministic and cover representative outputs with numerical
  drift tests.
- Reject random train/test splits for ordered financial data unless the estimand
  genuinely makes order irrelevant. Record feature and target availability,
  purge labels unknown at each test boundary, prevent overlapping evaluation
  windows, refit baselines within each fold, and retain individual out-of-sample
  predictions for review.
- Separate iteration and model selection from final assessment. Fit supervised
  filtering, preprocessing, feature selection, hyperparameters, calibration, and
  thresholds inside each training fold; review unsupervised future-distribution
  access against the actual point-in-time use case too.
- Use a domain heuristic and interpretable statistical baseline before adding
  complexity. Evaluate the candidate on net decision value, uncertainty,
  stability, costs, capacity, latency, and operating burden as well as model loss.
- For Parquet datasets, make schema order and dtypes, nullability, keys,
  partitions, sorting, invariants, and compatibility policy executable. Publish
  immutable versions through same-filesystem staging, retain a hashed manifest,
  and verify file set, hashes, schema, partitions, counts, and ordering before a
  lazy Polars scan. Do not describe unsigned checksums as publisher authenticity.

## Numerical arrays and statistical implementation

The supplied NumPy handout contributes array fundamentals; its 2014 syntax and
setup instructions are historical. See [the source review](NUMERICAL_SOURCE_REVIEW.md)
and [the Bayesian regression implementation guide](BAYESIAN_REGRESSION_IMPLEMENTATION.md),
which emphasizes BDA Chapters 14–17. These additions address correct
implementation without drawing conclusions about statistical applications to finance.

- At a dataframe-to-array boundary, declare shape, axis meaning, row identity,
  ordered columns, dtype, units, and missing/non-finite behavior. Assert the
  expected output shape too: an `(n, 1)` array combined with an `(n,)` array can
  broadcast to `(n, n)` even when elementwise pairing was intended.
- Make ownership explicit. Basic slicing commonly returns a view; advanced
  indexing returns a copy. A reshape can return either. Copy deliberately when
  mutation must be isolated, and account for conversion and allocation costs.
  See the official [copies and views guide](https://numpy.org/doc/stable/user/basics.copies.html).
- Bound vectorized intermediate arrays and benchmark representative sizes.
  Broadcasting avoids some input copies but does not eliminate the cost of a
  large result. See [NumPy broadcasting](https://numpy.org/doc/stable/user/basics.broadcasting.html).
- Use suitable linear solves and factorizations for regression rather than
  explicitly evaluating inverse-based textbook expressions. Check rank,
  conditioning, covariance assumptions, and absolute/relative error tolerances.
- Pass an owned random generator into stochastic calculations rather than
  resetting shared random state. Record the bit generator, seeds or state,
  parallel stream allocation, library versions, and execution settings. NumPy's
  `Generator` does not promise identical bit streams across versions; a fixed
  seed is not a cross-version reproducibility guarantee. See the official
  [Generator reference](https://numpy.org/doc/stable/reference/random/generator.html).
- Specify estimator conventions such as variance degrees of freedom, weight
  meaning, intercept treatment, parameterization, and residual scale. Keep a
  numerical calculation, statistical fit, and evidence artifact distinguishable.
- For Bayesian regression, retain likelihood and prior specifications, scaling,
  inference method, diagnostics, and parameter versus predictive uncertainty.
  The existing Statsmodels OLS example is not a Bayesian implementation.

## Reliability and concurrency

- Make timeouts finite and retries bounded, jittered, observable, and limited to
  operations safe to repeat. Idempotency belongs to the operation, not the loop.
- Assume tasks can be cancelled between awaits. Use structured concurrency,
  propagate cancellation, and shield only minimal consistency-critical cleanup.
- Protect shared mutable state or eliminate it. A thread-safe container does not
  make a multi-step business invariant atomic.
- Preserve exception chains with `raise ... from ...`; never swallow broad
  exceptions. Log once at the boundary that owns the failure response.
- Define overload behavior: concurrency limit, queue capacity, rejection policy,
  and shutdown drain deadline.

## Tests and delivery

- Test observable behavior and invariants. Use property-based tests for parsers,
  numeric boundaries, state machines, and round trips where example tests leave
  a large input space uncovered.
- Keep unit tests deterministic by injecting clock, randomness, and I/O. Add
  contract tests for ports and integration tests for real adapters.
- Test negative paths: malformed data, permissions, exhaustion, cancellation,
  timeouts, duplicate delivery, partial writes, and incompatible schema versions.
- Pin the runtime and dependencies; commit one resolver lock; install frozen in
  CI; build wheels/sdists; smoke-test the artifact in a clean environment.
- Use formatting, lint, typing, tests, security/dependency review, and packaging
  as one reproducible quality gate. Never report a skipped check as passing.

## Review questions

1. Which values can exist in an invalid state, and where are they validated?
2. Which imports perform I/O or depend on the developer machine?
3. Where can aliasing or mutation cross a boundary unexpectedly?
4. Which iterable may be consumed twice or materialized without a bound?
5. Which retry can duplicate an externally visible effect?
6. Which task, thread, process, file, or connection lacks an explicit owner?
7. Which optimization lacks a representative benchmark and regression threshold?
8. Which annotation hides uncertainty with `Any`, a cast, or suppression?
9. Where does a dataframe conversion change dtype, index, null, or memory semantics?
10. Which statistical default or sample choice is implicit in the reported result?
