# Security Policy

Security owner: Josh Myers (`joshuamyers22`). Report vulnerabilities privately to
the owner through an existing private channel. Do not include actual secrets or
private source in public issues. This pre-release foundation has no production
support SLA; a response commitment is required before deployment.

The current CLI executes no input-supplied commands and makes no network requests.
It is not an OS sandbox. Input and artifact parent directories must be controlled
by the user; other processes with the same OS identity remain outside the threat
model. See `docs/THREAT_MODEL.md` for scoped guarantees and remaining risks.
